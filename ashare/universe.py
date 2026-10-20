"""Dated, point-in-time security status. Uncovered intervals stay UNKNOWN."""
import pandas as pd

class StatusFilter:
    def __init__(self,path=None,unknown_policy='allow'):
        if unknown_policy not in ('allow','block'): raise ValueError('未知状态处理必须是allow或block')
        self.unknown_policy=unknown_policy
        self.rows=pd.DataFrame(columns=['symbol','start_date','end_date','known_date','status'])
        if path:
            f=pd.read_csv(path,dtype={'symbol':str},keep_default_na=False)
            required={'symbol','start_date','end_date'}
            if not required.issubset(f): raise ValueError('清单必须包含symbol,start_date,end_date')
            if 'status' not in f:
                if 'reason' not in f: raise ValueError('清单须包含status或reason')
                f['status']=f.reason.str.strip().str.upper().map(lambda x:x if x in ('ST','*ST','NORMAL','UNKNOWN') else 'EXCLUDE')
            f['symbol']=f.symbol.str.strip(); f['status']=f.status.str.strip().str.upper()
            if not f.status.isin(['ST','*ST','NORMAL','UNKNOWN','EXCLUDE']).all(): raise ValueError('状态仅支持ST,*ST,NORMAL,UNKNOWN,EXCLUDE')
            for col in ['start_date','end_date']:
                f[col]=pd.to_datetime(f[col],errors='raise')
            if 'known_date' not in f: f['known_date']=f.start_date
            else: f['known_date']=pd.to_datetime(f.known_date,errors='raise')
            if f[['start_date','end_date','known_date']].isna().any().any() or (f.start_date>f.end_date).any(): raise ValueError('日期为空或起止倒置')
            for _,group in f.groupby('symbol'):
                g=group.sort_values('start_date')
                if (g.start_date.iloc[1:].to_numpy()<=g.end_date.iloc[:-1].to_numpy()).any(): raise ValueError('同证券状态区间不能重叠')
            self.rows=f

    def at(self,date,symbols):
        state=pd.Series('UNKNOWN',index=symbols,dtype=object)
        r=self.rows
        active=r[(r.start_date<=date)&(r.end_date>=date)&(r.known_date<=date)]
        active=active[active.symbol.isin(symbols)]
        state.loc[active.symbol]=active.status.to_numpy()
        return state

    def blocked(self,state):
        return state.isin(['ST','*ST','EXCLUDE']) | ((state=='UNKNOWN') & (self.unknown_policy=='block'))
