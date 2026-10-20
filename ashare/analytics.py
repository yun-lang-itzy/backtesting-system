"""Auditable reports: attribution identities, period metrics and execution quality."""
import json
import html
import numpy as np
import pandas as pd
from .contributions import security_report


def build_report(results, config, summary, out, data, benchmark=None):
    d=results['daily'].set_index('date').copy()
    eq=d.equity; prev=eq.shift().fillna(config.initial_cash)
    ret=eq/prev-1
    attribution=pd.DataFrame({'net_pnl':eq-prev,'explicit_fees':d.fees,'slippage':d.slippage_cost})
    attribution['holding_and_execution_pnl_before_costs']=attribution.net_pnl+attribution.explicit_fees+attribution.slippage
    # This is an accounting decomposition at actual fills, not a zero-cost rerun.
    attribution['cash_opportunity_cost_vs_benchmark']=np.nan
    comparison=pd.DataFrame(index=d.index)
    if benchmark:
        b=pd.read_csv(benchmark,parse_dates=['date']).set_index('date')['close'].sort_index()
        if not b.index.is_unique or b.isna().any() or not np.isfinite(b).all() or (b<=0).any():
            raise ValueError('基准CSV需要唯一date与正有限close')
        aligned=b.reindex(d.index)
        if aligned.isna().any(): raise ValueError('基准缺少回测日期，不进行静默填充')
        prior=b[b.index<d.index[0]]
        if prior.empty: raise ValueError('基准需要回测起始日前一个收盘值')
        br=aligned/aligned.shift().fillna(prior.iloc[-1])-1
        comparison['strategy_nav']=eq/config.initial_cash
        comparison['benchmark_nav']=(1+br).cumprod()
        comparison['relative_nav']=comparison.strategy_nav/comparison.benchmark_nav
        comparison['daily_active_return']=ret-br
        attribution['cash_opportunity_cost_vs_benchmark']=d.cash.shift().fillna(config.initial_cash)*br
        summary['benchmark_total_return']=float(comparison.benchmark_nav.iloc[-1]-1)
        summary['relative_total_return']=float(comparison.relative_nav.iloc[-1]-1)
    attribution.to_csv(out/'attribution.csv')
    comparison.to_csv(out/'benchmark.csv')
    for name,rule in [('annual','YE'),('monthly','ME')]:
        periods=(1+ret).resample(rule).prod()-1
        periods.rename('return').to_csv(out/f'{name}_returns.csv')
    rolling=pd.DataFrame({f'return_{n}d':(1+ret).rolling(n).apply(np.prod,raw=True)-1 for n in [20,60,252]})
    rolling.to_csv(out/'rolling_returns.csv')
    holdings=results['holdings']
    concentration=pd.DataFrame(index=d.index)
    concentration['largest_position_weight']=holdings.groupby('date').weight.max().reindex(d.index,fill_value=0)
    concentration['hhi']=holdings.assign(square=holdings.weight**2).groupby('date').square.sum().reindex(d.index,fill_value=0)
    concentration['cash_weight']=d.cash/eq
    concentration.to_csv(out/'concentration.csv')
    orders=results['orders'].copy()
    orders['fill_ratio_units']=np.where(orders.requested_units>0,orders.filled_units/orders.requested_units,0.)
    adv=data['amt'].rolling(config.lookback).mean()
    orders['historical_adv']=[adv.at[pd.Timestamp(row.signal_date),row.symbol] for row in orders.itertuples()]
    orders['requested_adv_ratio']=orders.requested_value_at_signal/orders.historical_adv
    orders['filled_adv_ratio']=orders.filled_notional/orders.historical_adv
    orders.to_csv(out/'capacity.csv',index=False)
    denominator=orders.requested_value_at_signal.sum()
    quality={'orders':len(orders),'orders_with_fill_ratio':float((orders.filled_units>0).mean()) if len(orders) else 0.,
        'value_weighted_fill_ratio_at_signal_prices':float((orders.requested_value_at_signal*orders.fill_ratio_units).sum()/denominator) if denominator else 0.,
        'max_single_position_weight':float(concentration.largest_position_weight.max()),
        'annual_one_way_turnover':summary['annual_one_way_turnover'],
        'max_filled_adv_ratio':float(orders.filled_adv_ratio.max()) if len(orders) and orders.filled_adv_ratio.notna().any() else 0.}
    (out/'trade_quality.json').write_text(json.dumps(quality,indent=2))
    lines=['# 回测报告','', '## 绩效指标','']
    labels={'total_return':'累计收益','cagr':'年化收益','annual_volatility':'年化波动率','sharpe_rf_zero':'夏普（无风险利率0）','max_drawdown':'最大回撤','final_equity':'最终权益'}
    lines += [f'- {label}: {summary[k]:.6f}' for k,label in labels.items()]
    lines += ['', '## 收益来源','',f'- 持仓及执行毛损益（按实际成交路径回加成本）: {attribution.holding_and_execution_pnl_before_costs.sum():,.2f}',f'- 显式费用: {d.fees.sum():,.2f}',f'- 已计入成交价的滑点: {d.slippage_cost.sum():,.2f}',f'- 净损益: {(eq.iloc[-1]-config.initial_cash):,.2f}',
        '- 毛损益 − 显式费用 − 滑点 = 净损益；毛损益并非无成本策略独立运行结果。',
        '- 现金机会成本定义：前日现金 × 当日基准收益。允许负值，不与上述净损益重复相加；它不代表可实现的全仓反事实。' if benchmark else '- 未提供基准，现金机会成本和超额收益不可计算。',
        '', '## 交易质量与容量','']
    lines += [f'- {k}: {v:.6f}' for k,v in quality.items()]
    lines += [f'- {k}: {v} 单' for k,v in summary['order_status'].items()]
    lines += ['', '容量基于历史成交额代理，不代表开盘实际容量。成交比例按信号时点金额加权，避免开盘跳空扭曲成交率。',
        '', '## 稳定性与验证','',
        '- annual_returns.csv / monthly_returns.csv：年度/月度复合收益，首尾期可能不完整。',
        '- rolling_returns.csv：20/60/252观察日滚动收益，窗口不足留空。',
        '- sensitivity.csv：真实重跑的成本情景和预先配置的参数变化。未配置的分析不视为已完成。',
        '- validation.csv：按时间分段或滚动前推的固定参数表现；每段独立资金启动、历史数据仅预热，不自动挑选参数。',
        '- 此数据历史已被查看，分段只是历史诊断，不宣称未见样本外。任何参数调整后重新查看测试期都应登记为重复使用。',
        '', '## 对照表现','',
        f'- 基准总收益: {summary.get("benchmark_total_return", "未提供")}；相对净值总收益: {summary.get("relative_total_return", "未提供")}',
        '', '## 模型与数据边界','',
        '- 原价×累计复权因子、成交额单位元均为待供应商确认假设；复权单位账户不是实际股份账户。',
        '- 缺少历史ST、精确涨跌停和公司行为；采用近似成交限制，缺失持仓沿用旧价，可能高估权益。',
        '- 费用为情景假设；无真实开盘容量、排队信息。未成交不等于策略撤销。',
        '- 数据哈希、代码、配置和尝试记录随本次结果保存。']
    coverage=results.get('status_coverage',pd.DataFrame())
    lines += ['', '## 证券状态覆盖', '', '- 清单未覆盖日期为UNKNOWN，不推断为NORMAL；未提供清单时不能宣称已经准确去除全部ST。']
    if not coverage.empty:
        lines += [f'- 未知证券日数: {int(coverage.unknown.sum())}',f'- 已知正常证券日数: {int(coverage.normal.sum())}',f'- 排除证券日数: {int(coverage.excluded.sum())}',f'- 强制退出持仓日数: {int(coverage.forced_positions.sum())}']
    contributions,risk=security_report(results,config,out)
    lines += ['', '## 按证券盈亏贡献', '', '- 净贡献 = 期末持仓市值 + 卖出金额 − 买入金额 − 显式费用；滑点已在成交金额中，不能重复扣减。', '- 全部证券贡献已与账户净损益自动对账；完整明细见security_contributions.csv。', '', '| 证券 | 净贡献（元） | 初始资金收益贡献 |', '| --- | --- | --- |']
    for row in contributions.itertuples():
        lines.append(f'| {row.symbol} | {row.net_pnl:,.2f} | {row.contribution_to_initial_capital:.2%} |')
    lines += ['', '## 未完成卖出与滞后估值持仓', '', '- 期末仍持有且存在未完成卖出或旧价估值的明细见unresolved_holdings.csv。长期阈值为5个观察日。', '- 未完成卖出持续天数不是连续每天都无法成交的证明；仅基于实际订单，可能存在策略取消退出或尚未重试。', '- 滞后估值天数按输入日历计数，不代表已确认停牌或退市。', '', '| 证券 | 期末市值 | 估值滞后日数 | 未完成卖出日数 | 最近原因 |', '| --- | --- | --- | --- | --- |']
    for row in risk.itertuples():
        lines.append(f'| {row.symbol} | {row.final_value:,.2f} | {row.stale_days} | {row.sell_unresolved_observation_days} | {row.last_sell_reason} |')
    if risk.empty:lines.append('期末未发现符合条件的持仓。')
    text='\n'.join(lines)+'\n'
    (out/'report.md').write_text(text)
    (out/'report.html').write_text('<meta charset="utf-8"><title>回测报告</title><style>body{max-width:1000px;margin:40px auto;font:16px system-ui;white-space:pre-wrap;line-height:1.7}</style><body>'+html.escape(text)+'</body>')
