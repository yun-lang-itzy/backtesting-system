from ashare import Strategy
import math


def positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class UserStrategy(Strategy):
    """周度中期动量；目标仓位等分top_n，每只不超过max_weight，余下留现金。"""
    def __init__(self, lookback=60, top_n=20, skip=5, trend_days=120,
                 investment=.95, min_adv=50_000_000, max_weight=.05, volatility_days=20):
        if not all(positive_int(x) for x in (lookback, top_n, trend_days)) or trend_days < 2:
            raise ValueError('窗口和top_n须为正整数，trend_days至少2')
        if not isinstance(skip,int) or isinstance(skip,bool) or skip < 0:
            raise ValueError('skip须为非负整数')
        if not all(math.isfinite(x) for x in (investment,min_adv)) or not 0 <= investment <= 1 or min_adv < 0:
            raise ValueError('investment须在0至1之间，min_adv非负')
        if not positive_int(volatility_days) or volatility_days < 2 or not math.isfinite(max_weight) or not 0 < max_weight <= 1:
            raise ValueError('volatility_days至少2，max_weight须在(0,1]')
        self.max_weight,self.volatility_days=max_weight,volatility_days
        self.lookback,self.top_n,self.skip,self.trend_days=lookback,top_n,skip,trend_days
        self.investment,self.min_adv=investment,min_adv

    def on_close(self, context):
        if not context.is_week_end:
            return None
        bars=max(120,self.trend_days,self.lookback+self.skip+1,self.volatility_days+1)
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
        if not eligible.any():
            return {}
        above=prices.iloc[-1].gt(prices.tail(self.trend_days).mean())
        exposure=self.investment
        if exposure<=0:
            return {}
        eligible &= above
        momentum=prices.iloc[-1-self.skip]/prices.iloc[-1-self.skip-self.lookback]-1
        eligible &= momentum.gt(0)
        volatility=prices.tail(self.volatility_days+1).pct_change(fill_method=None).iloc[1:].std()
        candidates=volatility[eligible].dropna()
        if candidates.empty:
            return {}
        eligible &= volatility.le(candidates.quantile(.8))
        ranked=momentum[eligible].dropna().sort_index().sort_values(ascending=False,kind='stable')
        return {symbol:min(exposure/self.top_n,self.max_weight) for symbol in ranked.head(self.top_n).index}
