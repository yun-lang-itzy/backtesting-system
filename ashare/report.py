from __future__ import annotations
import numpy as np
import pandas as pd
def summarize(result, config):
    d = result['daily']; eq = d.equity
    returns = eq/eq.shift().fillna(config.initial_cash)-1
    years = (pd.Timestamp(d.date.iloc[-1])-pd.Timestamp(d.date.iloc[0])).days/365.25
    dd = eq / eq.cummax().clip(lower=config.initial_cash)-1
    return dict(initial_cash=config.initial_cash, final_equity=float(eq.iloc[-1]),
        total_return=float(eq.iloc[-1]/config.initial_cash-1), cagr=float((eq.iloc[-1]/config.initial_cash)**(1/years)-1),
        annual_volatility=float(returns.std(ddof=1)*np.sqrt(252)),
        sharpe_rf_zero=float(returns.mean()/returns.std(ddof=1)*np.sqrt(252)) if returns.std()>0 else 0.,
        max_drawdown=float(dd.min()), fees=float(d.fees.sum()), slippage_cost=float(d.slippage_cost.sum()),
        trades=len(result['trades']), orders=len(result['orders']),
        order_status=result['orders'].status.value_counts().to_dict(),
        final_stale_value=float(d.stale_value.iloc[-1]),max_stale_value=float(d.stale_value.max()),
        average_cash_weight=float((d.cash/eq).mean()),
        annual_one_way_turnover=float((d.traded_notional/eq.shift().fillna(config.initial_cash)).sum()/years/2))
