import unittest
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np
import test_backtest
from ashare import Config
from ashare.engine import simulate
from ashare.report import summarize
from ashare.analytics import build_report
from ashare.research import run_research
from ashare import Strategy

class ReportTests(unittest.TestCase):
    def test_reconciliation_and_benchmark(self):
        data=test_backtest.BacktestTests().fixture(); cfg=Config(); r=simulate(data,cfg); summary=summarize(r,cfg)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            idx=pd.DatetimeIndex([data['close'].index[0]-pd.Timedelta(days=1)]).append(data['close'].index)
            pd.DataFrame({'date':idx,'close':np.arange(len(idx))+100}).to_csv(p/'b.csv',index=False)
            build_report(r,cfg,summary,p,data,p/'b.csv')
            a=pd.read_csv(p/'attribution.csv')
            np.testing.assert_allclose(a.holding_and_execution_pnl_before_costs-a.explicit_fees-a.slippage,a.net_pnl,atol=1e-8)
            self.assertTrue(a.cash_opportunity_cost_vs_benchmark.notna().all())
            monthly=pd.read_csv(p/'monthly_returns.csv')['return']
            self.assertAlmostEqual((1+monthly).prod()-1,summary['total_return'])
            self.assertTrue((p/'report.html').exists())

    def test_missing_benchmark_dates_rejected(self):
        data=test_backtest.BacktestTests().fixture();cfg=Config();r=simulate(data,cfg)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);pd.DataFrame({'date':['2024-01-01'],'close':[100]}).to_csv(p/'b.csv',index=False)
            with self.assertRaises(ValueError):build_report(r,cfg,summarize(r,cfg),p,data,p/'b.csv')

    def test_time_split_disjoint(self):
        class Cash(Strategy):
            def on_close(self,c):return {}
        data=test_backtest.BacktestTests().fixture()
        settings={'start':'2024-01-01','end':'2024-03-08','research':{'validation':'split','train_end':'2024-01-31','validation_end':'2024-02-20','cost_multipliers':[2]}}
        with tempfile.TemporaryDirectory() as tmp:
            run_research(data,Config(),Cash,settings,Path(tmp))
            v=pd.read_csv(Path(tmp)/'validation.csv')
            self.assertTrue(v.end.iloc[0]<v.start.iloc[1]<v.end.iloc[1]<v.start.iloc[2])
            self.assertTrue((v.total_return==0).all())
