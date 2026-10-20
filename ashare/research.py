from dataclasses import replace
import json
import pandas as pd
from .engine import simulate
from .report import summarize


def run_research(data,config,cls,settings,out,status_filter=None,progress=None):
    research=settings.get('research',{})
    dates=data['close'].index
    dates=dates[(dates>=pd.Timestamp(settings['start']))&(dates<=pd.Timestamp(settings['end']))]
    params=settings.get('strategy_params',{})
    attempts=[]; sensitivity=[]; validation=[]
    def execute(label,cfg,args,window):
        if progress:progress('研究重跑 '+label,.7)
        r=simulate(data,cfg,cls(**args),window[0],window[-1],status_filter=status_filter)
        stats=summarize(r,cfg)
        attempts.append({'label':label,'params':args,'start':str(window[0]),'end':str(window[-1]),'status':'complete'})
        row=dict(label=label,start=str(window[0]),end=str(window[-1]),params=json.dumps(args),**{k:stats[k] for k in ['total_return','cagr','max_drawdown','sharpe_rf_zero','trades']})
        # Keep daily account evidence for every alternative run.
        r['daily'].to_csv(out/(label+'_daily.csv'),index=False)
        return row
    for multiplier in research.get('cost_multipliers',[]):
        if not isinstance(multiplier,(int,float)) or not 0<=multiplier<=10: raise ValueError('成本倍数须在0至10之间')
        cfg=replace(config,fee_bps=config.fee_bps*multiplier,sell_extra_bps=config.sell_extra_bps*multiplier,slippage_bps=config.slippage_bps*multiplier)
        sensitivity.append(execute(f'cost_{multiplier}',cfg,params,dates))
    variants=research.get('parameter_sets',[])
    if not isinstance(variants,list) or len(variants)>10: raise ValueError('参数组须为列表且不超过10组')
    for i,args in enumerate(variants):
        sensitivity.append(execute(f'params_{i}',config,{**params,**args},dates))
    mode=research.get('validation','none')
    if mode=='split':
        train_end=pd.Timestamp(research['train_end']); valid_end=pd.Timestamp(research['validation_end'])
        if not dates[0]<=train_end<valid_end<dates[-1]: raise ValueError('划分需满足开始≤训练结束<验证结束<结束')
        windows=[dates[dates<=train_end],dates[(dates>train_end)&(dates<=valid_end)],dates[dates>valid_end]]
        if any(len(x)<2 for x in windows): raise ValueError('每个区间至少需要2个观察日')
        for label,window in zip(['train','validation','test'],windows):
            validation.append(execute(label,config,params,window))
    elif mode=='walk_forward':
        train=int(research.get('train_days',252)); test=int(research.get('test_days',63))
        if train<2 or test<2 or train+test>len(dates): raise ValueError('前推窗口不足或长度非法')
        for index,offset in enumerate(range(train,len(dates)-test+1,test)):
            window=dates[offset:offset+test]
            row=execute(f'walk_{index}',config,params,window)
            row.update(train_start=str(dates[offset-train]),train_end=str(dates[offset-1]))
            validation.append(row)
    elif mode!='none': raise ValueError('未知验证模式')
    columns=['label','start','end','params','total_return','cagr','max_drawdown','sharpe_rf_zero','trades']
    pd.DataFrame(sensitivity,columns=columns).to_csv(out/'sensitivity.csv',index=False)
    pd.DataFrame(validation,columns=columns+['train_start','train_end']).to_csv(out/'validation.csv',index=False)
    (out/'attempts.json').write_text(json.dumps({'historical_data_already_observed':True,'automatic_parameter_selection':False,'attempts':attempts},indent=2))
    if (out/'report.md').exists():
        import html
        text=(out/'report.md').read_text()
        for title,rows in [('成本与参数重跑结果',sensitivity),('时间验证结果',validation)]:
            text+='\n## '+title+'\n\n'
            if not rows:
                text+='本次未启用。\n'
            else:
                text+='| 情景 | 开始 | 结束 | 收益 | 最大回撤 | 参数 |\n| --- | --- | --- | --- | --- | --- |\n'
                for row in rows:
                    text+=f'| {row["label"]} | {row["start"][:10]} | {row["end"][:10]} | {row["total_return"]:.2%} | {row["max_drawdown"]:.2%} | {row["params"]} |\n'
        (out/'report.md').write_text(text)
        (out/'report.html').write_text('<meta charset="utf-8"><title>回测报告</title><style>body{max-width:1000px;margin:40px auto;font:16px system-ui;white-space:pre-wrap;line-height:1.7}</style><body>'+html.escape(text)+'</body>')
