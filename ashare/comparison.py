"""Independent weekly equal-weight account; no market index implied."""
import pandas as pd
from .strategy import Strategy
from .engine import simulate
from .report import summarize

class EqualWeightStrategy(Strategy):
    def on_close(self, context):
        if not context.is_week_end:
            return None
        prices=context.history('adjusted_close',120)
        if len(prices)<120:
            return None
        factors=context.history('cumadj',120)
        amount=context.history('amt',20)
        eligible=prices.notna().all() & prices.gt(0).all() & factors.notna().all() & factors.gt(0).all()
        eligible &= factors.pct_change(fill_method=None).abs().iloc[1:].le(.30).all()
        eligible &= amount.gt(0).all() & amount.mean().ge(50_000_000)
        for symbol in prices.columns:
            state=context.security_status.get(symbol,'UNKNOWN')
            if state in ('ST','*ST','EXCLUDE') or (state=='UNKNOWN' and context.unknown_status_policy=='block'):
                eligible.loc[symbol]=False
        names=sorted(eligible[eligible].index)
        return {symbol:.95/len(names) for symbol in names}


def run_comparison(data,config,settings,out,main_results,status_filter,progress=None):
    result=simulate(data,config,EqualWeightStrategy(),pd.Timestamp(settings['start']),pd.Timestamp(settings['end']),status_filter=status_filter,
        progress=(lambda date,f:progress('周度等权对比 '+date,.62+.07*f)) if progress else None)
    for name,frame in result.items():
        frame.to_csv(out/('equal_weight_'+name+'.csv'),index=False)
    from .terminal import append_terminal_report
    with (out/'report.md').open('a') as f:f.write('\n### 等权组合结束处理\n')
    append_terminal_report(result,config,out)
    stats=pd.DataFrame([summarize(main_results,config),summarize(result,config)],index=['主策略','周度等权'])
    keys=['total_return','cagr','max_drawdown','annual_volatility','sharpe_rf_zero','annual_one_way_turnover','fees','slippage_cost','average_cash_weight']
    stats[keys].rename_axis('portfolio').to_csv(out/'comparison_metrics.csv')
    main=main_results['daily'].set_index('date').equity/config.initial_cash
    equal=result['daily'].set_index('date').equity/config.initial_cash
    curve=pd.DataFrame({'strategy_nav':main,'equal_weight_nav':equal})
    curve['relative_nav']=main/equal
    curve['return_difference']=main-equal
    curve.to_csv(out/'comparison.csv')
    text='\n## 周度等权模拟对比组合\n\n同资金、日期、股票池、状态政策、费用和成交约束，独立账户运行。每周收盘形成目标、下一交易日开盘尝试成交；95%仓位平均分配至合格股票，余下现金。要求120日有效价格与因子、因子单日变化不超过30%、20日每日成交额为正且均值至少5000万元；先排除已知ST/*ST，不使用动量、趋势及波动率排名。未知状态沿用本次配置。\n\n采用复权权益份额，可含碎股；不是正式市场指数，也不是保证可实盘复制的组合。成交受限时实际权重偏离等权。\n\n| 指标 | 主策略 | 周度等权 |\n| --- | --- | --- |\n'
    labels=['累计收益','年化收益','最大回撤','年化波动率','夏普（无风险利率0）','年化单边换手','费用（元）','滑点成本（元）','平均现金比例']
    for key,label in zip(keys,labels):
        values=stats[key].tolist()
        fmt='.2f' if key in ('sharpe_rf_zero','fees','slippage_cost') else '.2%'
        text+=f'| {label} | {values[0]:{fmt}} | {values[1]:{fmt}} |\n'
    text+=f"\n期末累计收益差：{curve.return_difference.iloc[-1]:.2%}（百分点差）；相对净值：{curve.relative_nav.iloc[-1]:.4f}（主策略净值/等权净值）。\n"
    with (out/'report.md').open('a') as f:f.write(text)
