import unittest
from dataclasses import replace
import numpy as np
import pandas as pd
from backtest import Config, band, limits, rejection, signals, simulate

class BacktestTests(unittest.TestCase):
    def test_board_transition(self):
        self.assertEqual(band('300001.SZ','2020-08-21'),.1)
        self.assertEqual(band('300001.SZ','2020-08-24'),.2)
        self.assertEqual(band('688001.SH','2020-01-01'),.2)
        self.assertIsNone(band('999999.SH','2020-01-01'))

    def test_ex_right_reference_and_rounding(self):
        self.assertEqual(limits('000001.SZ','2024-01-01',10,1,2),(4.5,5.5))
        self.assertEqual(limits('000001.SZ','2024-01-01',10.05,1,1),(9.05,11.06))

    def check_order(self,side,o,h,l,c):
        return rejection(side,o,h,l,c,1e8,1,10,1,'000001.SZ','2024-01-01',Config())

    def test_directional_limits(self):
        self.assertEqual(self.check_order('buy',11,11,10,10.5),'estimated_limit_up')
        self.assertEqual(self.check_order('sell',11,11,10,10.5),'')
        self.assertEqual(self.check_order('sell',9,10,9,9.5),'estimated_limit_down')
        self.assertEqual(self.check_order('buy',9,10,9,9.5),'')
        self.assertEqual(self.check_order('sell',10,10,10,10),'one_price_bar')

    def fixture(self):
        dates=pd.bdate_range('2024-01-01','2024-03-08'); n=len(dates)
        close=pd.DataFrame(np.full((n,1),10.),index=dates,columns=['000001.SZ'])
        return dict(open=close.copy(),close=close.copy(),high=close+1,low=close-1,
                    amt=close*1e7,cumadj=close/10,num_trades=close*100)

    def test_signal_future_invariance(self):
        d=self.fixture(); before=signals(d,Config())[2]
        d['close'].iloc[30:]*=2
        after=signals(d,Config())[2]
        pd.testing.assert_frame_equal(before.iloc[:30],after.iloc[:30])

    def test_flat_asset_fees_cash_and_next_day(self):
        c=replace(Config(),top_n=1,participation=1,slippage_bps=0,fee_bps=3)
        r=simulate(self.fixture(),c)
        first=r['trades'].iloc[0]
        self.assertEqual(first.signal_date,pd.Timestamp('2024-01-31'))
        self.assertEqual(first.date,pd.Timestamp('2024-02-01'))
        self.assertTrue((r['daily'].cash>=-1e-6).all())
        self.assertAlmostEqual(r['daily'].equity.iloc[-1],c.initial_cash-r['daily'].fees.sum(),places=6)
        self.assertTrue((r['trades'].date>r['trades'].signal_date).all())

    def test_missing_holding_is_retained(self):
        d=self.fixture(); d['close'].iloc[-1]=np.nan
        r=simulate(d,replace(Config(),top_n=1,participation=1))
        self.assertGreater(r['daily'].iloc[-1].stale_value,0)
        self.assertEqual(r['daily'].iloc[-1].positions,1)

    def test_factor_jump_does_not_create_pnl(self):
        d=self.fixture()
        for k in ['open','high','low','close']: d[k].iloc[30:]/=2
        d['cumadj'].iloc[30:]*=2
        r=simulate(d,replace(Config(),top_n=1,participation=1,fee_bps=0,sell_extra_bps=0,slippage_bps=0))
        np.testing.assert_allclose(r['daily'].equity,1e6)

    def test_blocked_buy_stays_cash(self):
        d=self.fixture(); dt=pd.Timestamp('2024-02-01')
        d['open'].loc[dt]=11; d['high'].loc[dt]=11
        r=simulate(d,replace(Config(),top_n=1))
        row=r['daily'].set_index('date').loc[dt]
        self.assertEqual(row.cash,1e6)
        self.assertEqual(r['orders'].iloc[0].status,'estimated_limit_up')

if __name__=='__main__': unittest.main()
