import json
import traceback
import platform
from pathlib import Path
from dataclasses import asdict
from datetime import datetime
from uuid import uuid4
import numpy as np
import pandas as pd
from .config import Config
from .data import load_data, sha256
from .engine import simulate
from .report import summarize
from .strategy import Strategy
from .universe import StatusFilter
from .analytics import build_report
from .charts import export_charts
from .research import run_research
from .comparison import run_comparison


def run(settings, source, output_root, progress=None):
    settings = {**settings, 'equal_weight_comparison': settings.get('equal_weight_comparison', True)}
    # All new UI/CLI/research runs must enter on the first selected session.
    settings = {**settings, 'engine': {**settings.get('engine', {}), 'entry_mode': 'first_open'}}
    config = Config(**settings['engine'])
    if config.entry_mode not in ('scheduled','first_open'): raise ValueError('未知建仓方式')
    if config.terminal_mode not in ('hold','liquidate','settle'): raise ValueError('未知结束方式')
    for name, value in asdict(config).items():
        if name in ('terminal_mode','entry_mode'): continue
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not np.isfinite(value) or value<0:
            raise ValueError('非法参数: '+name)
    if config.initial_cash<=0 or not 0<config.participation<=1 or not isinstance(config.lookback,int) or config.lookback<1 or not isinstance(config.top_n,int) or config.top_n<1:
        raise ValueError('资金、窗口、持股数或参与率无效')
    start,end=pd.Timestamp(settings['start']),pd.Timestamp(settings['end'])
    if start>=end: raise ValueError('开始日期必须早于结束日期')
    if settings.get('strict',False):
        raise ValueError('严格模式无法运行：当前七个文件缺少逐日交易状态和公司行为')
    compile(source,'strategy.py','exec')
    out=Path(output_root)/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False)
    (out/'strategy.py').write_text(source)
    (out/'config.json').write_text(json.dumps({**settings,'engine':asdict(config)},indent=2,ensure_ascii=False))
    (out/'status.json').write_text(json.dumps({'status':'running'}))
    if progress: progress('读取与校验数据',.02,out)
    try:
        namespace={'__name__':'user_strategy'}
        exec(compile(source,str(out/'strategy.py'),'exec'),namespace)
        cls=namespace.get('UserStrategy')
        if not isinstance(cls,type) or not issubclass(cls,Strategy): raise ValueError('必须定义继承 Strategy 的 UserStrategy')
        data,audit=load_data(Path(settings['data']))
        symbols=settings.get('symbols',[])
        if symbols:
            if len(set(symbols))!=len(symbols): raise ValueError('股票池代码重复')
            missing=set(symbols)-set(data['close'].columns)
            if missing: raise ValueError('未知证券: '+','.join(sorted(missing)))
            data={k:v.loc[:,symbols] for k,v in data.items()}
        dates=data['close'].index
        if ((dates>=start)&(dates<=end)).sum()<2: raise ValueError('所选范围至少需要两个交易日')
        audit['runtime']={'python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__}
        audit['source_hashes']={f.name:sha256(f) for f in Path(__file__).parent.glob('*.py')}
        audit['strategy_sha256']=sha256(out/'strategy.py')
        (out/'data_audit.json').write_text(json.dumps(audit,indent=2))
        status_path=settings.get('exclusions') or None
        if status_path:
            import shutil
            shutil.copyfile(status_path,out/'exclusions.csv')
            status_path=out/'exclusions.csv'
            audit['exclusions_sha256']=sha256(status_path)
            (out/'data_audit.json').write_text(json.dumps(audit,indent=2))
        status_filter=StatusFilter(status_path,settings.get('unknown_status_policy','allow'))
        results=simulate(data,config,cls(**settings.get("strategy_params",{})),start,end,status_filter=status_filter,progress=(lambda date,f:progress("主回测 "+date,.1+.5*f)) if progress else None)
        summary=summarize(results,config)
        for key,frame in results.items(): frame.to_csv(out/(key+'.csv'),index=False)
        benchmark=settings.get('benchmark') or None
        if benchmark:
            import shutil
            shutil.copyfile(benchmark,out/'benchmark_input.csv')
            benchmark=out/'benchmark_input.csv'
        if progress: progress('生成归因与持仓报告',.62)
        build_report(results,config,summary,out,data,benchmark)
        from .terminal import append_terminal_report
        append_terminal_report(results,config,out)
        if settings['equal_weight_comparison']:
            run_comparison(data,config,settings,out,results,status_filter,progress)
        run_research(data,config,cls,settings,out,status_filter=status_filter,progress=progress)
        (out/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
        if progress:progress('绘制导出图表',.95)
        export_charts(out)
        (out/'status.json').write_text(json.dumps({'status':'complete'}))
        return out,results,summary
    except Exception:
        (out/'error.txt').write_text(traceback.format_exc())
        (out/'status.json').write_text(json.dumps({'status':'failed'}))
        raise
