"""Local process jobs; only terminate child processes created by this manager."""
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4
import os
import signal

PROCESSES={}

def write_state(path,state):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(state,ensure_ascii=False))
    temp.replace(path)

def launch(settings,source,root):
    job=Path(root)/'jobs'/uuid4().hex
    job.mkdir(parents=True)
    (job/'settings.json').write_text(json.dumps(settings))
    (job/'strategy.py').write_text(source)
    write_state(job/'state.json',{'status':'running','stage':'启动进程','progress':0})
    with (job/'worker.log').open('w') as log:
        process=subprocess.Popen([sys.executable,'-m','ashare.worker',str(job),str(Path(root)/'runs')],cwd=Path(__file__).resolve().parent.parent,stdout=log,stderr=log,start_new_session=True)
    PROCESSES[str(job)]=process
    return str(job)

def read_state(job):
    path=Path(job)/'state.json'
    state=json.loads(path.read_text())
    proc=PROCESSES.get(str(job))
    if proc is not None and proc.poll() is not None and state['status']=='running':
        state.update(status='failed',stage='工作进程异常退出，请查看worker.log')
        write_state(path,state)
    return state

def cancel(job):
    proc=PROCESSES.get(str(job))
    if proc is None: raise ValueError('无法确认工作进程身份，未发送终止信号')
    state=read_state(job)
    if state['status']!='running': return state
    # Separate process group also terminates strategy-created child processes.
    if proc.poll() is None:
        os.killpg(proc.pid,signal.SIGTERM)
        try:proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=2)
    state=read_state(job)
    if state['status']=='complete': return state
    state.update(status='cancelled',stage='已取消，结果未完成')
    write_state(Path(job)/'state.json',state)
    if state.get('output'):
        write_state(Path(state['output'])/'status.json',{'status':'cancelled'})
    return state
