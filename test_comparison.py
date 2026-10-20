import unittest
import tempfile
from pathlib import Path
import pandas as pd
from ashare.comparison import EqualWeightStrategy,run_comparison
from ashare.strategy import Context
from ashare.config import Config
from ashare.engine import simulate
from ashare.universe import StatusFilter

class ComparisonTests(unittest.TestCase):
    def fixture(self):
        dates=pd.bdate_range('2023-01-02',periods=135)
        price=pd.DataFrame(10.,index=dates,columns=['000001.SZ','000002.SZ','000003.SZ'])
        return {k:price*(1 if k in ['open','close'] else 1.01 if k=='high' else .99 if k=='low' else .1 if k=='cumadj' else 10_000_000) for k in ['open','high','low','close','cumadj','amt','num_trades']}

    def test_weekly_status_before_equal_weights_and_no_trend_required(self):
        data=self.fixture();c=Context(data,124,1e6,1e6,{})
        self.assertTrue(c.is_week_end)
        c.security_status={'000001.SZ':'ST','000002.SZ':'NORMAL','000003.SZ':'UNKNOWN'}
        self.assertEqual(EqualWeightStrategy().on_close(c),{'000002.SZ':.475,'000003.SZ':.475})
        c.unknown_status_policy='block'
        self.assertEqual(EqualWeightStrategy().on_close(c),{'000002.SZ':.95})
        self.assertIsNone(EqualWeightStrategy().on_close(Context(data,123,1e6,1e6,{})))

    def test_independent_account_and_report(self):
        data=self.fixture();cfg=Config();strategy=EqualWeightStrategy()
        main=simulate(data,cfg,strategy)
        original=main['daily'].copy(deep=True)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);(out/'report.md').write_text('report')
            run_comparison(data,cfg,dict(start=str(data['close'].index[0]),end=str(data['close'].index[-1])),out,main,StatusFilter(None,'allow'))
            curve=pd.read_csv(out/'comparison.csv')
            self.assertTrue(curve.relative_nav.eq(1).all())
            trades=pd.read_csv(out/'equal_weight_trades.csv')
            self.assertGreater(len(trades),0)
            self.assertEqual(pd.Timestamp(trades.date.iloc[0]).weekday(),0)
            self.assertIn('周度等权',(out/'report.md').read_text())
        pd.testing.assert_frame_equal(original,main['daily'])
