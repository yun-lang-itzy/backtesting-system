import json
import sys
import traceback
from pathlib import Path
from .runner import run
from .jobs import write_state

if __name__=='__main__':
    job,root=map(Path,sys.argv[1:])
    state={'status':'running','stage':'准备数据','progress':0}
    def progress(stage,fraction,output=None):
        state.update(stage=stage,progress=float(fraction))
        if output is not None:state['output']=str(output)
        write_state(job/'state.json',state)
    try:
        out,_,_=run(json.loads((job/'settings.json').read_text()),(job/'strategy.py').read_text(),root,progress=progress)
        state.update(status='complete',stage='报告已完成',progress=1.,output=str(out))
    except Exception as exc:
        state.update(status='failed',stage=str(exc))
        (job/'error.txt').write_text(traceback.format_exc())
    write_state(job/'state.json',state)
