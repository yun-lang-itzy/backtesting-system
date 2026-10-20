from __future__ import annotations
import numpy as np
import pandas as pd
from .execution import limits, rejection
from .strategy import Context, validate_weights
def signals(data, config):
    adj = data['close'] * data['cumadj']
    valid = adj.notna() & (data['amt'] > 0)
    ratio = data['cumadj'] / data['cumadj'].shift(1) - 1
    clean = ratio.abs().le(config.max_factor_jump) | ratio.isna()
    eligible = (valid & clean).rolling(config.lookback + 1).sum().eq(config.lookback + 1)
    adv = data['amt'].rolling(config.lookback).mean()
    score = (adj / adj.shift(config.lookback) - 1).where(eligible & adv.ge(config.min_adv))
    return adj, adv, score


def simulate(data, config, strategy=None, start=None, end=None, status_filter=None, progress=None):
    if config.terminal_mode not in ('hold','liquidate','settle'): raise ValueError('未知结束方式')
    adj, adv, score = signals(data, config)
    dates, codes = adj.index, adj.columns
    arrays = {k:v.to_numpy() for k,v in data.items()}
    av, sc, prices = adv.to_numpy(), score.to_numpy(), adj.to_numpy()
    units = np.zeros(len(codes)); mark = np.zeros(len(codes)); age = np.zeros(len(codes), dtype=int)
    cash = config.initial_cash
    orders, trades, daily, holdings, selections = [], [], [], [], []
    pending = []
    status_log = []
    forced = set()
    settlements=[]
    selected_dates=dates[(dates>=pd.Timestamp(start if start is not None else dates[0])) & (dates<=pd.Timestamp(end if end is not None else dates[-1]))]
    terminal_date=selected_dates[-1] if len(selected_dates) else None
    if config.entry_mode not in ('scheduled','first_open'): raise ValueError('未知建仓方式')
    if config.entry_mode=='first_open' and len(selected_dates):
        first=dates.get_loc(selected_dates[0]); previous=first-1
        if previous<0 or strategy is None: raise ValueError('首日建仓需要前一交易日历史及策略')
        context=Context(data,previous,cash,cash,{})
        context.is_week_end=True  # Explicit one-off initialization, using only previous close history.
        context.security_status=status_filter.at(dates[previous],codes).to_dict() if status_filter else {c:'UNKNOWN' for c in codes}
        context.unknown_status_policy=status_filter.unknown_policy if status_filter else 'allow'
        weights=strategy.on_close(context)
        if weights is None: raise ValueError('历史不足或策略未返回首日建仓目标')
        validate_weights(weights,codes)
        excluded=status_filter.blocked(status_filter.at(dates[previous],codes)) if status_filter else pd.Series(False,index=codes)
        for symbol,weight in weights.items():
            j=codes.get_loc(symbol)
            if weight<=0 or excluded.loc[symbol]: continue
            if not np.isfinite(prices[previous,j]) or not np.isfinite(av[previous,j]): raise ValueError('首日目标缺少历史价格或成交额')
            selections.append(dict(date=dates[previous],symbol=symbol,score=sc[previous,j],target_weight=weight))
            pending.append((j,cash*weight/prices[previous,j],av[previous,j]*config.participation,dates[previous]))
        pending.sort(key=lambda order:codes[order[0]])
        if not pending: raise ValueError('首日强制建仓失败：无合格的非零买入目标；空仓策略不适用于此运行规则')
    for i, dt in enumerate(dates):
        if start is not None and dt < pd.Timestamp(start): continue
        if end is not None and dt > pd.Timestamp(end): break
        state = status_filter.at(dt,codes) if status_filter else None
        blocked = status_filter.blocked(state) if status_filter else pd.Series(False,index=codes)
        if status_filter:
            forced.update(j for j in np.flatnonzero(units>1e-12) if state.iloc[j] in ('ST','*ST','EXCLUDE'))
            forced = {j for j in forced if units[j]>1e-12}
            pending = [order for order in pending if order[0] not in forced]
            if i>0:
                for j in sorted(forced):
                    cap=av[i-1,j]*config.participation if np.isfinite(av[i-1,j]) else 0.
                    pending.append((j,-units[j],cap,dates[i-1]))
            pending.sort(key=lambda order:(order[1]>0,codes[order[0]]))
            status_log.append(dict(date=dt,unknown=int((state=='UNKNOWN').sum()),normal=int((state=='NORMAL').sum()),excluded=int(state.isin(['ST','*ST','EXCLUDE']).sum()),forced_positions=len(forced)))
        if progress and i%10==0:
            selected_dates=dates[(dates>=pd.Timestamp(start or dates[0])) & (dates<=pd.Timestamp(end or dates[-1]))]
            progress(str(dt.date()),float((selected_dates<=dt).sum()/len(selected_dates)))
        terminal=dt==terminal_date and config.terminal_mode!='hold'
        if terminal:
            # Scheduled exit replaces all pending rebalances and prohibits buys.
            pending=[(j,-units[j],av[i-1,j]*config.participation if i>0 and np.isfinite(av[i-1,j]) else 0.,dates[i-1] if i>0 else dt) for j in np.flatnonzero(units>1e-12)]
        old_units = units.copy()  # Day-start sellable units, enforces no same-day resale.
        day_fee = day_slip = turnover = 0.
        for j, requested, capacity, signal_date in pending:
            side = 'buy' if requested > 0 else 'sell'
            raw_o = arrays['open'][i,j]; factor = arrays['cumadj'][i,j]
            reason = rejection(side, *[arrays[k][i,j] for k in ('open','high','low','close','amt','cumadj')],
                               arrays['close'][i-1,j], arrays['cumadj'][i-1,j], codes[j], dt, config)
            if side=='buy' and blocked.iloc[j]:
                reason = 'status_unknown_blocked' if state.iloc[j]=='UNKNOWN' else 'status_excluded'
            qty = 0.; fee = slip = notional = 0.; fill_raw = np.nan
            if not reason:
                down, up = limits(codes[j], dt, arrays['close'][i-1,j], arrays['cumadj'][i-1,j], factor)
                fill_raw = raw_o * (1 + (1 if side == 'buy' else -1)*config.slippage_bps/10000)
                # Adverse slippage must fit the observed bar and estimated band; no favorable clipping.
                if fill_raw > min(arrays['high'][i,j], up) + 1e-8 or fill_raw < max(arrays['low'][i,j], down) - 1e-8:
                    reason = 'slippage_outside_range'
                else:
                    price = fill_raw * factor
                    fee_rate = (config.fee_bps + (config.sell_extra_bps if side == 'sell' else 0))/10000
                    qty = min(abs(requested), capacity/price)
                    if side == 'sell':
                        qty = min(qty, old_units[j], units[j])
                    else:
                        qty = min(qty, max(0., cash)/(price*(1+fee_rate)))
                    notional = qty * price; fee = notional * fee_rate
                    slip = qty * factor * abs(fill_raw - raw_o)
                    if qty <= 1e-12:
                        reason = 'cash_or_sellable'
                    else:
                        signed = qty if side == 'buy' else -qty
                        units[j] += signed
                        cash -= signed * price + fee
                        day_fee += fee; day_slip += slip; turnover += notional
                        reason = 'filled' if qty >= abs(requested)*(1-1e-9) else 'partial_capacity_or_cash'
                        trades.append(dict(date=dt, signal_date=signal_date, symbol=codes[j], side=side,
                            units=qty, raw_fill=fill_raw, adjusted_fill=price, notional=notional, fee=fee, slippage_cost=slip))
            orders.append(dict(date=dt, signal_date=signal_date, symbol=codes[j], side=side,
                requested_units=abs(requested), filled_units=qty, status=reason,
                requested_value_at_signal=abs(requested)*prices[i-1,j], filled_notional=notional))
        if config.entry_mode=='first_open' and dt==selected_dates[0] and not (units>1e-12).any():
            reasons=pd.Series([row['status'] for row in orders]).value_counts().to_dict()
            raise ValueError('首日强制建仓失败：买单全部未成交，不能推迟建仓。原因：'+str(reasons))
        observed = np.isfinite(prices[i])
        mark[observed] = prices[i,observed]
        age = np.where(observed, 0, age+1)
        if terminal and config.terminal_mode=='settle':
            for j in np.flatnonzero(units>1e-12):
                # Hypothetical closing settlement, never represented as an executable fill.
                if not np.isfinite(mark[j]) or mark[j]<=0:
                    raise ValueError('无法强制结算：缺少有效当前或历史估值 '+codes[j])
                qty=float(units[j]); price=float(mark[j]); notional=qty*price
                fee=notional*(config.fee_bps+config.sell_extra_bps)/10000
                basis='current_close' if observed[j] else 'last_valid_adjusted_mark'
                settlements.append(dict(date=dt,symbol=codes[j],units=qty,adjusted_price=price,notional=notional,fee=fee,valuation_basis=basis,stale_days=int(age[j])))
                # Ledger entries included for account/P&L reconciliation only; identified by settlement ledger.
                trades.append(dict(date=dt,signal_date=dt,symbol=codes[j],side='sell',units=qty,raw_fill=np.nan,adjusted_fill=price,notional=notional,fee=fee,slippage_cost=0.))
                orders.append(dict(date=dt,signal_date=dt,symbol=codes[j],side='sell',requested_units=qty,filled_units=qty,status='hypothetical_settlement',requested_value_at_signal=notional,filled_notional=notional))
                cash+=notional-fee;day_fee+=fee;turnover+=notional;units[j]=0.
        value = units * mark
        equity = cash + value.sum()
        assert cash >= -1e-6 and (units >= -1e-9).all() and np.isfinite(equity)
        daily.append(dict(date=dt, equity=equity, cash=cash, market_value=value.sum(),
            positions=int((units>1e-12).sum()), fees=day_fee, slippage_cost=day_slip, traded_notional=turnover,
            stale_value=value[~observed].sum(), stale_positions=int(((units>1e-12)&~observed).sum())))
        for j in np.flatnonzero(units > 1e-12):
            holdings.append(dict(date=dt,symbol=codes[j],units=units[j],adjusted_mark=mark[j],
                value=value[j],weight=value[j]/equity,stale_days=age[j]))
        pending = []
        if terminal: continue
        # Month-end recognized by next observed session's month, never by future price values.
        month_end = i+1 < len(dates) and dt.month != dates[i+1].month
        weights = None
        if strategy is not None:
            context=Context(data, i, cash, equity, dict(zip(codes, units)))
            context.security_status = state.to_dict() if state is not None else {symbol:'UNKNOWN' for symbol in codes}
            context.unknown_status_policy = status_filter.unknown_policy if status_filter else 'allow'
            weights = strategy.on_close(context)
        elif month_end:
            eligible = np.flatnonzero(np.isfinite(sc[i]))
            selected = sorted(eligible, key=lambda j:(-sc[i,j], codes[j]))[:config.top_n]
            weights = {codes[j]: 1/config.top_n for j in selected}
        if weights is not None:
            validate_weights(weights, codes)
            if status_filter:
                for symbol,weight in weights.items():
                    if weight>0 and blocked.loc[symbol]:
                        orders.append(dict(date=dt,signal_date=dt,symbol=symbol,side='buy',requested_units=0.,filled_units=0.,status='signal_status_'+state.loc[symbol].lower(),requested_value_at_signal=equity*weight,filled_notional=0.))
                weights={symbol:weight for symbol,weight in weights.items() if not blocked.loc[symbol]}

            target = np.zeros(len(codes))
            for symbol, weight in weights.items():
                j = codes.get_loc(symbol)
                if weight > 0 and (not np.isfinite(prices[i,j]) or prices[i,j] <= 0):
                    raise ValueError(f'目标证券缺少有效收盘价格: {symbol}')
                if weight > 0: target[j] = equity*weight/prices[i,j]
                selections.append(dict(date=dt,symbol=symbol,score=sc[i,j],target_weight=weight))
            for j in np.flatnonzero((units>1e-12)|(target>0)):
                if not np.isfinite(prices[i,j]) or not np.isfinite(av[i,j]):
                    orders.append(dict(date=dt,signal_date=dt,symbol=codes[j],side='sell' if units[j]>0 else 'buy',
                        requested_units=float(units[j]),filled_units=0.,status='signal_missing_mark',
                        requested_value_at_signal=float(value[j]),filled_notional=0.))
                    continue
                delta = target[j]-units[j]
                if abs(delta)*prices[i,j] > .01:
                    pending.append((j,delta,av[i,j]*config.participation,dt))
            pending.sort(key=lambda order:(order[1]>0,codes[order[0]]))
    schemas = {
        'status_coverage': 'date unknown normal excluded forced_positions',
        'daily': 'date equity cash market_value positions fees slippage_cost traded_notional stale_value stale_positions',
        'orders': 'date signal_date symbol side requested_units filled_units status requested_value_at_signal filled_notional',
        'trades': 'date signal_date symbol side units raw_fill adjusted_fill notional fee slippage_cost',
        'holdings': 'date symbol units adjusted_mark value weight stale_days',
        'selections': 'date symbol score target_weight'}
    result = {k:pd.DataFrame(v, columns=schemas[k].split()) for k,v in dict(status_coverage=status_log,daily=daily,orders=orders,trades=trades,holdings=holdings,selections=selections).items()}

    if config.terminal_mode!='hold':
        result['trades']['execution_type']=np.where(result['trades'].raw_fill.isna(),'hypothetical_settlement','simulated_fill')
        result['settlements']=pd.DataFrame(settlements,columns='date symbol units adjusted_price notional fee valuation_basis stale_days'.split())
    return result
