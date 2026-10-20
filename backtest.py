"""Offline daily adjusted-unit simulator. No broker connectivity."""
from __future__ import annotations
import argparse
from dataclasses import dataclass, asdict
import hashlib
import json
from pathlib import Path
import platform
import numpy as np
import pandas as pd

FIELDS = ('open', 'high', 'low', 'close', 'amt', 'num_trades', 'cumadj')

@dataclass(frozen=True)
class Config:
    initial_cash: float = 1_000_000
    lookback: int = 20
    top_n: int = 20
    min_adv: float = 20_000_000  # Assumes amt is CNY, not vendor-confirmed.
    participation: float = .001
    fee_bps: float = 3
    sell_extra_bps: float = 5  # Constant scenario cost, NOT historical tax rules.
    slippage_bps: float = 5
    max_factor_jump: float = .30


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load_data(root):
    data, audit = {}, {}
    for name in FIELDS:
        path = root / f'{name}.feather'
        frame = pd.read_feather(path).set_index('date')
        if not frame.index.is_unique or not frame.index.is_monotonic_increasing or not frame.columns.is_unique:
            raise ValueError('Duplicate or unordered index')
        if data:
            first = data['open']
            if not frame.index.equals(first.index) or not frame.columns.equals(first.columns):
                raise ValueError('Unaligned matrices')
        arr = frame.to_numpy(dtype=float)
        if np.isinf(arr).any() or (arr[np.isfinite(arr)] < 0).any():
            raise ValueError(f'Invalid values: {name}')
        if name not in ('amt', 'num_trades') and (arr == 0).any():
            raise ValueError(f'Zero price/factor: {name}')
        data[name] = frame
        audit[name] = dict(sha256=sha256(path), shape=list(frame.shape),
                           missing=int(frame.isna().sum().sum()), zeros=int((frame == 0).sum().sum()),
                           final_valid=int(frame.iloc[-1].notna().sum()))
    bad = ((data['high'] < data['low']) | (data['high'] < data['open']) |
           (data['high'] < data['close']) | (data['low'] > data['open']) | (data['low'] > data['close']))
    if bad.to_numpy().any():
        raise ValueError('OHLC violations')
    audit['contract'] = dict(start=str(frame.index[0]), end=str(frame.index[-1]),
        factor_convention='ASSUMED: adjusted_price = raw_price * cumadj', amt_unit='ASSUMED CNY',
        archive_hash_status='Not verified: supplied hash target archive not identified',
        supplied_archive_hash=None)
    return data, audit


def band(symbol, date):
    if symbol.startswith('688'):
        return .20
    if symbol.startswith(('300', '301')):
        return .20 if pd.Timestamp(date) >= pd.Timestamp('2020-08-24') else .10
    if symbol.startswith(('000', '001', '002', '003', '600', '601', '603', '605')):
        return .10
    return None


def limits(symbol, date, previous_close, previous_factor, factor):
    rate = band(symbol, date)
    if rate is None or not np.all(np.isfinite([previous_close, previous_factor, factor])) or min(previous_close, previous_factor, factor) <= 0:
        return None
    ref = previous_close * previous_factor / factor
    # Decimal half-up to one tick; small epsilon only addresses binary float noise.
    return (np.floor(ref * (1-rate)*100 + .5 + 1e-9)/100,
            np.floor(ref * (1+rate)*100 + .5 + 1e-9)/100)


def rejection(side, o, h, l, c, amount, factor, previous_close, previous_factor, symbol, date, config):
    if not np.all(np.isfinite([o,h,l,c,amount,factor])) or min(o,h,l,c,factor) <= 0:
        return 'missing_data'
    if amount <= 0:
        return 'zero_amount'
    bounds = limits(symbol, date, previous_close, previous_factor, factor)
    if bounds is None:
        return 'unknown_reference'
    if abs(factor / previous_factor - 1) > config.max_factor_jump:
        return 'factor_jump'
    if max(o,h,l,c) - min(o,h,l,c) < 1e-8:
        return 'one_price_bar'
    down, up = bounds
    if side == 'buy' and o >= up - 1e-8:
        return 'estimated_limit_up'
    if side == 'sell' and o <= down + 1e-8:
        return 'estimated_limit_down'
    return ''


def signals(data, config):
    adj = data['close'] * data['cumadj']
    valid = adj.notna() & (data['amt'] > 0)
    ratio = data['cumadj'] / data['cumadj'].shift(1) - 1
    clean = ratio.abs().le(config.max_factor_jump) | ratio.isna()
    eligible = (valid & clean).rolling(config.lookback + 1).sum().eq(config.lookback + 1)
    adv = data['amt'].rolling(config.lookback).mean()
    score = (adj / adj.shift(config.lookback) - 1).where(eligible & adv.ge(config.min_adv))
    return adj, adv, score


def simulate(data, config):
    adj, adv, score = signals(data, config)
    dates, codes = adj.index, adj.columns
    arrays = {k:v.to_numpy() for k,v in data.items()}
    av, sc, prices = adv.to_numpy(), score.to_numpy(), adj.to_numpy()
    units = np.zeros(len(codes)); mark = np.zeros(len(codes)); age = np.zeros(len(codes), dtype=int)
    cash = config.initial_cash
    orders, trades, daily, holdings, selections = [], [], [], [], []
    pending = []
    for i, dt in enumerate(dates):
        old_units = units.copy()  # Day-start sellable units, enforces no same-day resale.
        day_fee = day_slip = turnover = 0.
        for j, requested, capacity, signal_date in pending:
            side = 'buy' if requested > 0 else 'sell'
            raw_o = arrays['open'][i,j]; factor = arrays['cumadj'][i,j]
            reason = rejection(side, *[arrays[k][i,j] for k in ('open','high','low','close','amt','cumadj')],
                               arrays['close'][i-1,j], arrays['cumadj'][i-1,j], codes[j], dt, config)
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
        observed = np.isfinite(prices[i])
        mark[observed] = prices[i,observed]
        age = np.where(observed, 0, age+1)
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
        # Month-end recognized by next observed session's month, never by future price values.
        month_end = i+1 < len(dates) and dt.month != dates[i+1].month
        if month_end:
            eligible = np.flatnonzero(np.isfinite(sc[i]))
            selected = sorted(eligible, key=lambda j:(-sc[i,j], codes[j]))[:config.top_n]
            target = np.zeros(len(codes))
            for j in selected:
                target[j] = equity/config.top_n/prices[i,j]
                selections.append(dict(date=dt,symbol=codes[j],score=sc[i,j],target_weight=1/config.top_n))
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
    return {k:pd.DataFrame(v) for k,v in dict(daily=daily,orders=orders,trades=trades,holdings=holdings,selections=selections).items()}


def summarize(result, config):
    d = result['daily']; eq = d.equity
    returns = eq.pct_change().fillna(0)
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


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path('data/feathers'))
    parser.add_argument('--output',type=Path,default=Path(__file__).parent/'results')
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    config=Config()
    (args.output/'config.json').write_text(json.dumps(asdict(config),indent=2))
    data,audit=load_data(args.data)
    audit['runtime']=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,code_sha256=sha256(__file__))
    (args.output/'data_audit.json').write_text(json.dumps(audit,indent=2))
    result=simulate(data,config); summary=summarize(result,config)
    for name,frame in result.items(): frame.to_csv(args.output/f'{name}.csv',index=False)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
    d=result['daily'].set_index('date'); yearly=d.equity.resample('YE').last()
    annual=yearly/yearly.shift().fillna(config.initial_cash)-1
    annual.to_csv(args.output/'annual_returns.csv',header=['return'])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(11,7),sharex=True)
    axes[0].plot(d.index,d.equity/config.initial_cash); axes[0].set_ylabel('NAV'); axes[0].set_title('20-day momentum | monthly top 20 | approximate execution')
    axes[1].fill_between(d.index,d.equity/d.equity.cummax()-1,0,alpha=.4); axes[1].set_ylabel('Drawdown')
    fig.tight_layout(); fig.savefig(args.output/'equity.png',dpi=160); plt.close(fig)
    lines=['# 首次全历史回测报告','', '**日频复权单位近似模拟；非实盘收益，未做参数优化或独立样本外检验。**','',
        '| 指标 | 结果 |','| --- | --- |']
    for key in ['total_return','cagr','max_drawdown','annual_volatility','average_cash_weight']:
        lines.append(f'| {key} | {summary[key]:.2%} |')
    lines += [f'| Sharpe（无风险利率0） | {summary["sharpe_rf_zero"]:.3f} |',f'| 最终权益 | {summary["final_equity"]:,.2f} |',
        f'| 成交笔数 | {summary["trades"]} |',f'| 显式费用 | {summary["fees"]:,.2f} |',f'| 已含在成交价中的滑点 | {summary["slippage_cost"]:,.2f} |','',
        '![净值与回撤](equity.png)','', '## 年度收益（首尾年可能不完整）','']
    lines += [f'- {dt.year}: {ret:.2%}' for dt,ret in annual.items()]
    lines += ['', '## 订单结果',''] + [f'- {k}: {v}' for k,v in summary['order_status'].items()]
    lines += ['', '## 边界','',
        '- 全历史只运行固定参数基线；全部结果已观察，不能再将本次末段称为未见测试集。',
        '- 假设 amt 单位为元、连续价格为原价×cumadj，均缺少供应商定义确认。',
        '- 合成持仓单位允许小数，不模拟真实整手、现金分红到账、配股和股份登记。',
        '- 主板普通股票10%、科创板20%、创业板2020-08-24起20%的代理；缺少历史ST及特殊状态，会误判。',
        '- 至少21日连续有效历史，避开样本中新出现证券的最初窗口；不等同于完整上市状态识别。',
        '- 全天零成交额、一字价和价格区间只用于事后撮合代理；开盘排队与容量不可还原。',
        '- 费用固定双边3bps、卖出额外5bps，滑点5bps，均是情景假设，不是历史税费复现。',
        '- 容量上限为过去20日平均成交额的0.1%，不是集合竞价容量；卖出后买入使用顺序撮合假设。',
        '- 缺失持仓沿用最后有效复权估值，长期停牌/退市可能高估权益；不自动删除。',
        f'- 最终滞后估值持仓金额：{summary["final_stale_value"]:,.2f}；历史最高：{summary["max_stale_value"]:,.2f}。',
        '- 输入日历未对照官方交易日历；没有市场基准，因此不报告超额收益。',
        '- 原压缩包哈希未校验；data_audit.json 保存实际读取的7个文件SHA-256。',
        '', '明细：[订单](orders.csv)、[成交](trades.csv)、[持仓](holdings.csv)、[每日账户](daily.csv)、[配置](config.json)、[数据审计](data_audit.json)。']
    (args.output/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
