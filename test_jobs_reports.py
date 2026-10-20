import unittest,tempfile,time,json
from pathlib import Path
from dataclasses import replace
import numpy as np
import test_backtest
from ashare.jobs import launch,cancel,read_state,PROCESSES
from ashare.contributions import security_report
from ashare import Config
from ashare.engine import simulate

class JobsReportsTests(unittest.TestCase):
    def test_cancel_stuck_strategy_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=launch({'start':'2024-01-01','end':'2024-02-01'},'while True: pass',tmp)
            self.addCleanup(lambda: cancel(job) if PROCESSES[job].poll() is None else None)
            deadline=time.time()+10
            while time.time()<deadline:
                state=read_state(job)
                if state.get('output'):break
                time.sleep(.05)
            self.assertIn('output',state)
            state=cancel(job)
            self.assertEqual(state['status'],'cancelled')
            self.assertIsNotNone(PROCESSES[job].poll())
            self.assertEqual(json.loads((Path(state['output'])/'status.json').read_text())['status'],'cancelled')
    def test_security_pnl_and_stale_holdings(self):
        data=test_backtest.BacktestTests().fixture()
        data['close'].iloc[-6:]=np.nan
        cfg=replace(Config(),top_n=1,participation=1)
        result=simulate(data,cfg)
        with tempfile.TemporaryDirectory() as tmp:
            c,r=security_report(result,cfg,Path(tmp))
            self.assertAlmostEqual(c.net_pnl.sum(),result['daily'].equity.iloc[-1]-cfg.initial_cash)
            self.assertEqual(r.stale_days.iloc[0],6)
            self.assertTrue(r.long_stale.iloc[0])
