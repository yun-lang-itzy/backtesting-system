import argparse
import json
from pathlib import Path
from ashare.runner import run

if __name__=='__main__':
    p=argparse.ArgumentParser(description='沪深策略回测命令行')
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--strategy',type=Path,required=True)
    p.add_argument('--output',type=Path,default=Path(__file__).parent/'runs')
    a=p.parse_args()
    out,_,_=run(json.loads(a.config.read_text()),a.strategy.read_text(),a.output)
    print(out)
