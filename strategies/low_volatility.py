from ashare import Strategy
import math


def positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class UserStrategy(Strategy):
    """周度低波动：60日收益标准差最低的20只，各占95%/20；不足留现金。"""
    def __init__(self, lookback=60, top_n=20, investment=.95, min_adv=50_000_000, max_weight=.05):
        if not positive_int(lookback) or lookback < 2 or not positive_int(top_n):
            raise ValueError('lookback须为至少2的整数，top_n须为正整数')
        if not math.isfinite(investment) or not 0 <= investment <= 1 or not math.isfinite(min_adv) or min_adv < 0:
            raise ValueError('investment须在0至1之间，min_adv须为非负有限数')
        if not math.isfinite(max_weight) or not 0 < max_weight <= 1:
            raise ValueError('max_weight须在(0,1]')
        self.max_weight=max_weight
        self.lookback, self.top_n = lookback, top_n
        self.investment, self.min_adv = investment, min_adv

    def on_close(self, context):
        if not context.is_week_end:
            return None
        bars=max(120, self.lookback+1)
        prices=context.history('adjusted_close',bars)
        if len(prices)<bars:
            return None
        factors=context.history('cumadj',bars)
        amount=context.history('amt',20)
        eligible=prices.notna().all() & prices.gt(0).all() & factors.notna().all() & factors.gt(0).all()
        eligible &= factors.pct_change(fill_method=None).abs().iloc[1:].le(.30).all()
        eligible &= amount.gt(0).all() & amount.mean().ge(self.min_adv)
        for symbol in prices.columns:
            state=context.security_status.get(symbol,'UNKNOWN')
            if state in ('ST','*ST','EXCLUDE') or (state=='UNKNOWN' and context.unknown_status_policy=='block'):
                eligible.loc[symbol]=False
        volatility=prices.tail(self.lookback+1).pct_change(fill_method=None).iloc[1:].std()
        ranked=volatility[eligible].dropna().sort_index().sort_values(kind='stable')
        return {symbol:min(self.investment/self.top_n,self.max_weight) for symbol in ranked.head(self.top_n).index}
