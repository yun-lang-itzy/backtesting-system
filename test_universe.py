import unittest,tempfile
from pathlib import Path
import pandas as pd
from dataclasses import replace
import test_backtest
from ashare.universe import StatusFilter
from ashare import Strategy,Config
from ashare.engine import simulate

class StatusTests(unittest.TestCase):
    def make(self,text):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        p=Path(temp.name)/'s.csv';p.write_text(text);return p
    def test_unknown_and_known_date(self):
        p=self.make('symbol,start_date,end_date,status,known_date\n000001.SZ,2024-02-01,2024-02-05,*ST,2024-02-02\n')
        f=StatusFilter(p)
        self.assertEqual(f.at(pd.Timestamp('2024-02-01'),['000001.SZ']).iloc[0],'UNKNOWN')
        self.assertEqual(f.at(pd.Timestamp('2024-02-02'),['000001.SZ']).iloc[0],'*ST')
        self.assertEqual(f.at(pd.Timestamp('2024-02-06'),['000001.SZ']).iloc[0],'UNKNOWN')
    def test_overlap_rejected(self):
        p=self.make('symbol,start_date,end_date,status\n000001.SZ,2024-01-01,2024-02-01,ST\n000001.SZ,2024-02-01,2024-03-01,NORMAL\n')
        with self.assertRaises(ValueError):StatusFilter(p)
    def test_forced_retry_and_buy_cancel(self):
        class S(Strategy):
            def on_close(self,c):
                return {'000001.SZ':.5} if c.date==pd.Timestamp('2024-01-31') else None
        d=test_backtest.BacktestTests().fixture()
        p=self.make('symbol,start_date,end_date,status\n000001.SZ,2024-02-02,2024-02-02,ST\n')
        d['amt'].loc['2024-02-02']=0
        r=simulate(d,replace(Config(),participation=1),S(),status_filter=StatusFilter(p))
        self.assertEqual(list(r['trades'].side),['buy','sell'])
        self.assertEqual(r['trades'].iloc[-1].date,pd.Timestamp('2024-02-05'))
        self.assertIn('zero_amount',r['orders'].status.to_list())
        p2=self.make('symbol,start_date,end_date,status\n000001.SZ,2024-02-01,2024-02-02,*ST\n')
        r=simulate(d,Config(),S(),status_filter=StatusFilter(p2))
        self.assertTrue(r['trades'].empty)
        self.assertIn('status_excluded',r['orders'].status.to_list())
    def test_unknown_block(self):
        class S(Strategy):
            def on_close(self,c): return {'000001.SZ':.5}
        r=simulate(test_backtest.BacktestTests().fixture(),Config(),S(),status_filter=StatusFilter(unknown_policy='block'))
        self.assertTrue(r['trades'].empty)
        self.assertTrue((r['status_coverage'].unknown==1).all())
