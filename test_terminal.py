import unittest
from dataclasses import replace
from pathlib import Path
import tempfile
import test_backtest
from ashare import Strategy,Config
from ashare.engine import simulate
from ashare.contributions import security_report

class Buy(Strategy):
    def on_close(self,c): return {'000001.SZ':.5}

class TerminalTests(unittest.TestCase):
    def test_exit_and_blocked_settlement(self):
        data=test_backtest.BacktestTests().fixture()
        cfg=replace(Config(),participation=1)
        end=data['close'].index[-1]
        hold=simulate(data,cfg,Buy())
        self.assertGreater(hold['daily'].positions.iloc[-1],0)
        exit=simulate(data,replace(cfg,terminal_mode='liquidate'),Buy())
        self.assertEqual(exit['daily'].positions.iloc[-1],0)
        self.assertFalse(((exit['trades'].date==end)&(exit['trades'].side=='buy')).any())
        data['amt'].iloc[-1]=0
        blocked=simulate(data,replace(cfg,terminal_mode='liquidate'),Buy())
        self.assertGreater(blocked['daily'].positions.iloc[-1],0)
        settled=simulate(data,replace(cfg,terminal_mode='settle'),Buy())
        self.assertEqual(settled['daily'].positions.iloc[-1],0)
        self.assertGreater(settled['settlements'].notional.sum(),0)
        with tempfile.TemporaryDirectory() as d:security_report(settled,cfg,Path(d))
        for key in ['close','cumadj']:data[key].iloc[-1]=float('nan')
        stale=simulate(data,replace(cfg,terminal_mode='settle'),Buy())
        self.assertTrue(stale['settlements'].valuation_basis.eq('last_valid_adjusted_mark').all())
        self.assertTrue(stale['settlements'].stale_days.eq(1).all())
