import unittest
from pathlib import Path
import numpy as np
from ashare.strategy import Context
import test_weekly


def strategy(name, **kwargs):
    scope={}
    exec((Path(__file__).parent/'strategies'/name).read_text(),scope)
    return scope['UserStrategy'](**kwargs)

class TemplateTests(unittest.TestCase):
    def context(self):
        d=test_weekly.WeeklyTests().fixture()
        t=np.arange(len(d['close']))
        for i,c in enumerate(d['close']):
            d['close'][c]=10*np.exp(.002*t+(.001+i*.001)*np.sin(t))
        return Context(d,129,1e6,1e6,{})

    def test_low_vol_ranking_exclusion_and_shortfall(self):
        c=self.context();c.security_status['000001.SZ']='ST'
        w=strategy('low_volatility.py').on_close(c)
        self.assertEqual(list(w),[f'{i:06d}.SZ' for i in range(2,22)])
        self.assertAlmostEqual(sum(w.values()),.95)
        c.unknown_status_policy='block';c.security_status['000002.SZ']='NORMAL'
        self.assertEqual(strategy('low_volatility.py').on_close(c),{'000002.SZ':.0475})

    def test_dynamic_breadth_before_selection(self):
        c=self.context()
        for key in list(c._history['close'].columns)[15:]:
            c._history['close']=c._history['close'].copy()
            c._history['close'][key]=10*np.exp(-.002*np.arange(130))
        w=strategy('dynamic_momentum.py',top_n=1,max_weight=1.).on_close(c)
        self.assertEqual(len(w),1)
        self.assertAlmostEqual(sum(w.values()),.95*.5)
        for key in list(c._history['close'].columns)[15:]:c.security_status[key]='ST'
        self.assertAlmostEqual(sum(strategy('dynamic_momentum.py',top_n=1,max_weight=1.).on_close(c).values()),.95)
        c.unknown_status_policy='block'
        self.assertEqual(strategy('dynamic_momentum.py').on_close(c),{})

    def test_schedule_and_invalid_params(self):
        for name in ['low_volatility.py','dynamic_momentum.py']:
            c=self.context();c.is_week_end=False
            self.assertIsNone(strategy(name).on_close(c))
            with self.assertRaises(ValueError):strategy(name,top_n=0)
            with self.assertRaises(ValueError):strategy(name,min_adv=float('nan'))

    def test_ui_load_each_template(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).with_name('app.py'))).run()
        for label,name in [('低波动 · 周度调仓','low_volatility.py'),('趋势动量 · 动态仓位','dynamic_momentum.py')]:
            next(x for x in app.selectbox if x.label=='策略起点').select(label).run()
            next(x for x in app.button if x.label=='载入所选模板（替换编辑区）').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['source'],(Path(__file__).parent/'strategies'/name).read_text())

class ParameterTests(unittest.TestCase):
    def test_cap_and_count(self):
        c=TemplateTests().context()
        for name in ['momentum.py','low_volatility.py','dynamic_momentum.py']:
            w=strategy(name,top_n=50,max_weight=.01).on_close(c)
            self.assertTrue(w)
            self.assertLessEqual(max(w.values()),.01)
            self.assertLess(sum(w.values()),.95)
            self.assertEqual(strategy(name,min_adv=1e12).on_close(c),{})

    def test_ui_parameters_and_custom_code(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).with_name('app.py'))).run()
        next(x for x in app.selectbox if x.label=='持股数量').select(100).run()
        self.assertIn('100',app.json[-1].value)
        next(x for x in app.text_area if x.label=='Python 策略代码').set_value('class Custom: pass').run()
        self.assertFalse(any(x.label=='持股数量' for x in app.selectbox))
