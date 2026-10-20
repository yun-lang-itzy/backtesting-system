import unittest
import importlib.util
from pathlib import Path
import pandas as pd
import numpy as np
from ashare.strategy import Context

spec=importlib.util.spec_from_file_location('weekly',Path(__file__).parent/'strategies/momentum.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class WeeklyTests(unittest.TestCase):
    def fixture(self):
        dates=pd.bdate_range('2023-01-02',periods=131)
        codes=[f'{i:06d}.SZ' for i in range(1,31)]
        close=pd.DataFrame({c:10*np.exp(np.arange(131)*(.001+i*.0001)) for i,c in enumerate(codes)},index=dates)
        data={'close':close,'cumadj':close*0+1,'amt':close*0+1e8}
        return data
    def test_week_end_and_pre_rank_exclusion(self):
        data=self.fixture(); c=Context(data,129,1e6,1e6,{})
        self.assertTrue(c.is_week_end)
        c.security_status['000030.SZ']='*ST'
        w=module.UserStrategy().on_close(c)
        self.assertEqual(len(w),20)
        self.assertNotIn('000030.SZ',w)
        self.assertAlmostEqual(sum(w.values()),.95)
        self.assertIsNone(module.UserStrategy().on_close(Context(data,128,1e6,1e6,{})))
    def test_unknown_block(self):
        c=Context(self.fixture(),129,1e6,1e6,{})
        c.unknown_status_policy='block'
        self.assertEqual(module.UserStrategy().on_close(c),{})
    def test_holiday_short_week(self):
        data=self.fixture()
        dates=pd.to_datetime(['2024-02-08','2024-02-19'])
        data={k:v.iloc[:2].set_axis(dates) for k,v in data.items()}
        self.assertTrue(Context(data,0,1,1,{}).is_week_end)
