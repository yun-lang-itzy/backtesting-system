import unittest
from pathlib import Path
from dataclasses import replace
import numpy as np
import pandas as pd
from ashare import Config,Strategy
from ashare.strategy import Context,validate_weights
from ashare.engine import simulate
from ashare.report import summarize
import test_backtest

class SystemTests(unittest.TestCase):
    def test_new_engine_matches_original(self):
        from backtest import simulate as old
        data=test_backtest.BacktestTests().fixture()
        a=old(data,Config()); b=simulate(data,Config())
        for name in a: pd.testing.assert_frame_equal(a[name],b[name])

    def test_history_no_future_or_mutation(self):
        d=test_backtest.BacktestTests().fixture(); c=Context(d,5,100,100,{})
        self.assertEqual(len(c.history('close',100)),6)
        frame=c.history('close'); frame.iloc[:]=999
        self.assertEqual(d['close'].iloc[5,0],10)

    def test_weight_validation(self):
        for weights in [{'000001.SZ':1.1},{'000001.SZ':float('nan')},{'bad':.2},{'000001.SZ':-.1},[]]:
            with self.assertRaises(ValueError): validate_weights(weights,['000001.SZ'])

    def test_none_hold_empty_liquidate(self):
        class TestStrategy(Strategy):
            def on_close(self,c):
                if c.date==pd.Timestamp('2024-02-01'): return {'000001.SZ':.5}
                if c.date==pd.Timestamp('2024-02-06'): return {}
                return None
        r=simulate(test_backtest.BacktestTests().fixture(),replace(Config(),participation=1),TestStrategy())
        self.assertEqual(list(r['trades'].side),['buy','sell'])
        self.assertEqual(list(r['trades'].date),[pd.Timestamp('2024-02-02'),pd.Timestamp('2024-02-07')])
        self.assertEqual(r['daily'].positions.iloc[-1],0)

    def test_cash_strategy_report(self):
        class Cash(Strategy):
            def on_close(self,c): return {}
        r=simulate(test_backtest.BacktestTests().fixture(),Config(),Cash())
        report=summarize(r,Config())
        self.assertEqual(report['total_return'],0)
        self.assertEqual(report['trades'],0)
        self.assertEqual(report['order_status'],{})

    def test_ui_load(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).with_name('app.py'))).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(any(x.label=='Python 策略代码' for x in app.text_area))
        self.assertTrue(any(x.label=='运行回测' for x in app.button))

if __name__=='__main__': unittest.main()
