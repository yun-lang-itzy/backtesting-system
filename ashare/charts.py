"""Standalone report figures and offline HTML embedding."""
import os
import tempfile
import base64
import html
from pathlib import Path
import numpy as np
import pandas as pd


def export_charts(out):
    out=Path(out)
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'ceyan-mpl'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white','axes.grid':True,'grid.alpha':.18})
    import json
    initial=json.loads((out/'summary.json').read_text())['initial_cash']
    daily=pd.read_csv(out/'daily.csv',parse_dates=['date']).set_index('date')
    images=[]
    def save(fig,name,title):
        fig.tight_layout();fig.savefig(out/name,dpi=160,bbox_inches='tight');plt.close(fig)
        images.append((name,title))
    fig,ax=plt.subplots(2,1,figsize=(11,7),sharex=True)
    ax[0].plot(daily.index,daily.equity/initial,color='#2563eb',label='Strategy')
    b=pd.read_csv(out/'benchmark.csv')
    if 'benchmark_nav' in b:
        ax[0].plot(pd.to_datetime(b.iloc[:,0]),b.benchmark_nav,label='Benchmark',color='#64748b');ax[0].legend()
    if (out/'comparison.csv').exists():
        comparison=pd.read_csv(out/'comparison.csv',parse_dates=['date']).set_index('date')
        ax[0].plot(comparison.index,comparison.equal_weight_nav,label='Weekly equal weight',color='#f59e0b')
        edd=100*(comparison.equal_weight_nav/comparison.equal_weight_nav.cummax().clip(lower=1)-1)
        ax[1].plot(comparison.index,edd,label='Weekly equal weight',color='#f59e0b')
        ax[1].legend()
    ax[0].legend()
    ax[0].set(title='Net asset value',ylabel='NAV')
    drawdown=100*(daily.equity/daily.equity.cummax().clip(lower=initial)-1)
    ax[1].fill_between(daily.index,drawdown,0,color='#ef4444',alpha=.4)
    ax[1].set(title='Drawdown',ylabel='%')
    save(fig,'chart_nav_drawdown.png','净值与回撤')
    monthly=pd.read_csv(out/'monthly_returns.csv',parse_dates=[0])
    monthly['year']=monthly.iloc[:,0].dt.year;monthly['month']=monthly.iloc[:,0].dt.month
    matrix=monthly.pivot(index='year',columns='month',values='return').reindex(columns=range(1,13))*100
    fig,ax=plt.subplots(figsize=(12,max(3,len(matrix)*.55+1)))
    values=matrix.to_numpy();limit=max(1,float(np.nanmax(np.abs(values))))
    cmap=plt.get_cmap('RdYlGn').copy();cmap.set_bad('#edf0f5')
    im=ax.imshow(np.ma.masked_invalid(values),aspect='auto',cmap=cmap,vmin=-limit,vmax=limit)
    ax.set_xticks(range(12),range(1,13));ax.set_yticks(range(len(matrix)),matrix.index)
    ax.set(title='Monthly returns (%) | partial first/last months',xlabel='Month');ax.grid(False)
    for i in range(values.shape[0]):
        for j in range(12):
            if np.isfinite(values[i,j]):ax.text(j,i,f'{values[i,j]:.1f}',ha='center',va='center',fontsize=8)
    fig.colorbar(im,ax=ax,shrink=.8)
    save(fig,'chart_monthly.png','月度收益热力图（首尾月可能不完整）')
    annual=pd.read_csv(out/'annual_returns.csv',parse_dates=[0])
    fig,ax=plt.subplots(figsize=(10,4));v=annual['return']*100
    ax.bar(annual.iloc[:,0].dt.year.astype(str),v,color=np.where(v>=0,'#16a34a','#ef4444'))
    ax.axhline(0,color='#64748b',linewidth=.8);ax.set(title='Annual returns | partial first/last years',ylabel='%')
    save(fig,'chart_annual.png','年度收益（首尾年可能不完整）')
    c=pd.read_csv(out/'security_contributions.csv').sort_values('net_pnl')
    if len(c)>20:c=pd.concat([c.head(10),c.tail(10)]).drop_duplicates('symbol')
    fig,ax=plt.subplots(figsize=(11,max(4,len(c)*.28+1)))
    if len(c):
        ax.barh(c.symbol,c.net_pnl,color=np.where(c.net_pnl>=0,'#16a34a','#ef4444'));ax.axvline(0,color='#64748b',linewidth=.8)
    else:ax.text(.5,.5,'No positions or trades',transform=ax.transAxes,ha='center')
    ax.set(title='Security P&L contribution | bottom/top 10 when >20 securities',xlabel='Net P&L (CNY)')
    save(fig,'chart_contributions.png','证券盈亏贡献（超过20只时展示贡献最低及最高各10只）')
    sensitivity=pd.read_csv(out/'sensitivity.csv');cost=sensitivity[sensitivity.label.astype(str).str.startswith('cost_')]
    fig,ax=plt.subplots(figsize=(10,4))
    if cost.empty:ax.text(.5,.5,'Cost sensitivity not run',transform=ax.transAxes,ha='center');ax.set_axis_off()
    else:
        summary=json.loads((out/'summary.json').read_text())
        labels=['Base (1x)']+cost.label.tolist();v=np.array([summary['total_return']]+cost.total_return.tolist())*100
        ax.bar(labels,v,color=np.where(v>=0,'#16a34a','#ef4444'));ax.axhline(0,color='#64748b',linewidth=.8);ax.set(ylabel='Total return (%)')
    ax.set_title('Cost sensitivity | fees and slippage rerun')
    save(fig,'chart_costs.png','成本敏感性（费用与滑点重跑）')
    report=(out/'report.md').read_text().split('\n<!-- exported-charts -->')[0]
    report+='\n<!-- exported-charts -->\n\n## 图表\n'
    for name,title in images:report+=f'\n### {title}\n\n![{title}]({name})\n'
    (out/'report.md').write_text(report)
    # Standard markdown is available with Streamlit; all report HTML is escaped by the renderer.
    import markdown
    body=markdown.markdown(html.escape(report,quote=False),extensions=['tables'])
    for name,_ in images:
        encoded=base64.b64encode((out/name).read_bytes()).decode()
        body=body.replace('src="'+name+'"','src="data:image/png;base64,'+encoded+'"')
    document='<html lang="zh"><meta charset="utf-8"><title>策演 · 回测报告</title><style>body{max-width:1100px;margin:40px auto;padding:20px;font:16px system-ui;line-height:1.65;color:#172033}img{max-width:100%;height:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #dce2ea;padding:7px;text-align:left}h1,h2{color:#183b75}@media print{img{break-inside:avoid}}</style><body>'+body+'</body></html>'
    (out/'report.html').write_text(document)
    return images
