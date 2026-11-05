import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest
import test_backtest


class EvolutionTests(unittest.TestCase):
    def test_research_freeze_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for field, frame in test_backtest.BacktestTests().fixture().items():
                frame.rename_axis('date').reset_index().to_feather(root / (field + '.feather'))
            settings = dict(data=tmp, start='2024-02-05', end='2024-03-08', symbols=[],
                            engine={'entry_mode':'first_open'}, unknown_status_policy='allow')
            source = ('from ashare import Strategy\nclass UserStrategy(Strategy):\n'
                      ' def __init__(self, w): self.w=w\n'
                      ' def on_close(self,c): return {c.symbols[0]:self.w}')
            script = (
                'from pathlib import Path\nfrom ashare.evolution_ui import show_evolution\n'
                f'show_evolution(Path({tmp!r}), {settings!r}, {source!r}, {dict(w=.5)!r})')
            app = AppTest.from_string(script).run()

            def button(label):
                next(b for b in app.button if b.label==label).click().run()
                self.assertFalse(app.exception)
                self.assertFalse(app.error)

            button('发起演化')
            app.text_input[0].set_value('减少目标仓位对收益有何影响？')
            button('锁定口径并计算基线')
            next(t for t in app.text_input if t.label.startswith('候选值')).set_value('[0.4]')
            button('评估候选')
            app.radio[0].set_value('因子比较').run()
            next(m for m in app.multiselect if m.label=='比较因子').set_value(['成交额'])
            button('评估候选')
            self.assertIn('因子 RankIC', app.dataframe[0].value)
            next(m for m in app.multiselect if m.label=='锁定候选版本').set_value([1])
            next(t for t in app.text_input if t.label=='入选理由').set_value('比较降低仓位前后表现')
            app.run()
            button('冻结候选并结束研究')
            app = AppTest.from_string(script).run()
            button('运行独立验证')
            self.assertEqual(len(app.dataframe[-1].value), 2)
            self.assertFalse(any(b.label=='评估候选' for b in app.button))
