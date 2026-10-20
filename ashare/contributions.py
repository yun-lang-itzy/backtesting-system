import numpy as np
import pandas as pd


def security_report(results,config,out,long_days=5):
    d=results['daily']; h=results['holdings']; t=results['trades']; orders=results['orders']
    symbols=sorted(set(h.symbol)|set(t.symbol))
    rows=[]; risks=[]
    dates=list(d.date); final=dates[-1]
    for symbol in symbols:
        trades=t[t.symbol==symbol]; history=h[h.symbol==symbol]
        last=history[history.date==final]
        value=float(last.value.sum())
        buys=float(trades.loc[trades.side=='buy','notional'].sum())
        sells=float(trades.loc[trades.side=='sell','notional'].sum())
        fees=float(trades.fee.sum()); slip=float(trades.slippage_cost.sum())
        net=value+sells-buys-fees
        rows.append(dict(symbol=symbol,buy_notional=buys,sell_notional=sells,final_market_value=value,fees=fees,slippage=slip,
                         net_pnl=net,gross_pnl_actual_path=net+fees+slip,contribution_to_initial_capital=net/config.initial_cash))
        if last.empty:continue
        sell_orders=orders[(orders.symbol==symbol)&(orders.side=='sell')].sort_values('date')
        # Track an unresolved sell episode; a full exit resets it. A later buy also resets it.
        unresolved=None; last_reason=''; attempts=0
        held=history.set_index('date')
        for dt in dates:
            if dt not in held.index:
                unresolved=None;attempts=0;continue
            if ((trades.date==dt)&(trades.side=='buy')).any():
                unresolved=None;attempts=0
            for order in sell_orders[sell_orders.date==dt].itertuples():
                if order.requested_units>order.filled_units+1e-10:
                    if unresolved is None:unresolved=dt
                    attempts+=1;last_reason=order.status
                elif order.filled_units>0:
                    unresolved=None;attempts=0
        stale=int(last.stale_days.max())
        elapsed=sum(dt>=unresolved for dt in dates) if unresolved is not None else 0
        if stale>0 or unresolved is not None:
            risks.append(dict(symbol=symbol,final_value=value,final_weight=float(last.weight.sum()),stale_days=stale,
                first_unresolved_sell=unresolved,sell_unresolved_observation_days=elapsed,failed_sell_attempts=attempts,
                last_sell_reason=last_reason,long_stale=stale>=long_days,long_unresolved_sell=elapsed>=long_days))
    contributions=pd.DataFrame(rows,columns=['symbol','buy_notional','sell_notional','final_market_value','fees','slippage','net_pnl','gross_pnl_actual_path','contribution_to_initial_capital'])
    contributions=contributions.sort_values('net_pnl',ascending=False)
    expected=float(d.equity.iloc[-1]-config.initial_cash)
    if not np.isclose(contributions.net_pnl.sum(),expected,atol=1e-5):raise ValueError('证券盈亏贡献与账户净损益不一致')
    contributions.to_csv(out/'security_contributions.csv',index=False)
    risk=pd.DataFrame(risks,columns=['symbol','final_value','final_weight','stale_days','first_unresolved_sell','sell_unresolved_observation_days','failed_sell_attempts','last_sell_reason','long_stale','long_unresolved_sell'])
    risk.to_csv(out/'unresolved_holdings.csv',index=False)
    return contributions,risk
