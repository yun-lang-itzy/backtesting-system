"""Strategy callbacks receive only history ending at the current close."""
import math
from types import MappingProxyType

class Strategy:
    def on_close(self, context):
        """Return None (hold), {} (liquidate), or {symbol: target_weight}."""
        raise NotImplementedError

class Context:
    def __init__(self, data, index, cash, equity, positions):
        # No future rows retained in the public context or its internal data.
        self._history = {k:v.iloc[:index+1] for k,v in data.items()}
        self.date = data['close'].index[index]
        dates = data['close'].index
        self.is_month_end = index+1 < len(dates) and self.date.month != dates[index+1].month
        self.is_week_end = index+1 < len(dates) and self.date.to_period('W-FRI') != dates[index+1].to_period('W-FRI')
        self.security_status = {symbol:'UNKNOWN' for symbol in data['close'].columns}
        self.unknown_status_policy = 'allow'
        self.symbols = tuple(data['close'].columns)
        self.cash = float(cash)
        self.equity = float(equity)
        self.positions = MappingProxyType({k:float(v) for k,v in positions.items() if v>1e-12})

    def history(self, field, bars=20):
        if not isinstance(bars,int) or bars<1:
            raise ValueError('bars 必须为正整数')
        if field == 'adjusted_close':
            return (self._history['close'].tail(bars)*self._history['cumadj'].tail(bars)).copy()
        if field not in self._history: raise ValueError('未知字段: '+field)
        return self._history[field].tail(bars).copy()


def validate_weights(weights, symbols):
    if not isinstance(weights,dict): raise ValueError('策略必须返回 None 或权重字典')
    for symbol,value in weights.items():
        if symbol not in symbols: raise ValueError('股票池不存在: '+str(symbol))
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
            raise ValueError('权重必须为有限非负数')
    if sum(weights.values())>1+1e-9: raise ValueError('权重合计不能超过1')
