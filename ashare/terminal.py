def append_terminal_report(results,config,out):
    modes={'hold':'保留持仓','liquidate':'结束日尝试清仓','settle':'结束日尝试清仓后强制结算（研究假设）'}
    d=results['daily'].iloc[-1]
    settlements=results.get('settlements')
    amount=0. if settlements is None else float(settlements.notional.sum())
    fee=0. if settlements is None else float(settlements.fee.sum())
    trades=results['trades']
    end_sells=trades[(trades.date==d.date)&(trades.side=='sell')]
    text=f"\n## 结束日处理\n\n方式：{modes[config.terminal_mode]}。实际结束观察日：{d.date}。\n\n正常模拟卖出金额：{end_sells.notional.sum()-amount:,.2f}元；正常卖出费用：{end_sells.fee.sum()-fee:,.2f}元。假设结算金额：{amount:,.2f}元；结算费用：{fee:,.2f}元。期末剩余持仓：{int(d.positions)}只，估值{d.market_value:,.2f}元。\n"
    if config.terminal_mode=='settle':
        text+='\n强制结算在末日开盘正常卖出尝试后，对剩余持仓采用当日复权收盘价；缺失时采用最后有效复权估值（滞后天数见settlements.csv）。忽略涨跌停和容量，收取卖出佣金及税费，不另加滑点。它不是可执行交易；账户净值、贡献、换手和费用包含该假设，成交笔数也含结算记账。请勿将其解释为真实清仓能力。\n'
    with (out/'report.md').open('a') as f:f.write(text)
