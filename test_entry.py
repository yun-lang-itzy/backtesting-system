import unittest
from dataclasses import replace
import pandas as pd
import test_backtest
from ashare import Strategy,Config
from ashare.engine import simulate
from ashare.report import summarize
class EntryTests(unittest.TestCase):
    def test_first_open_uses_previous_history(self):
        seen=[]
        class S(Strategy):
            def on_close(self,c):
                seen.append(c.history('close').index[-1])
                return {'000001.SZ':.5} if c.is_week_end else None
        data=test_backtest.BacktestTests().fixture()
        start=data['close'].index[25]
        r=simulate(data,replace(Config(),entry_mode='first_open',participation=1),S(),start=start)
        self.assertEqual(seen[0],data['close'].index[24])
        self.assertEqual(r['daily'].date.iloc[0],start)
        self.assertEqual(r['trades'].date.iloc[0],start)
        self.assertEqual(r['trades'].signal_date.iloc[0],seen[0])
        summary=summarize(r,Config())
        ret=r['daily'].equity/r['daily'].equity.shift().fillna(1e6)-1
        self.assertAlmostEqual(summary['annual_volatility'],ret.std()*252**.5)

    def test_empty_and_blocked_first_day_rejected(self):
        class Empty(Strategy):
            def on_close(self,c):return {}
        class Buy(Strategy):
            def on_close(self,c):return {'000001.SZ':.5}
        data=test_backtest.BacktestTests().fixture();start=data['close'].index[25]
        cfg=replace(Config(),entry_mode='first_open')
        with self.assertRaisesRegex(ValueError,'无合格'):
            simulate(data,cfg,Empty(),start=start)
        data['amt'].loc[start]=0
        with self.assertRaisesRegex(ValueError,'全部未成交'):
            simulate(data,cfg,Buy(),start=start)

    def test_runner_forces_first_open(self):
        from unittest.mock import patch
        import tempfile,json
        from pathlib import Path
        from ashare.runner import run
        data=test_backtest.BacktestTests().fixture()
        with tempfile.TemporaryDirectory() as tmp:
            with patch('ashare.runner.load_data',return_value=(data,{})),patch('ashare.runner.simulate',side_effect=RuntimeError('captured')) as mock:
                with self.assertRaisesRegex(RuntimeError,'captured'):
                    run(dict(data=tmp,start='2024-02-01',end='2024-03-01',engine={'entry_mode':'scheduled'}),'from ashare import Strategy\nclass UserStrategy(Strategy):\n def on_close(self,c): return {}',tmp)
            self.assertEqual(mock.call_args.args[1].entry_mode,'first_open')
            cfg=json.loads(next(Path(tmp).glob('*/config.json')).read_text())
            self.assertEqual(cfg['engine']['entry_mode'],'first_open')
