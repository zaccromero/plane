"""Sequential bounded native work: refresh context at dispatch, retain durable run handles."""
import argparse,fcntl,json,re,subprocess,sys,uuid
from pathlib import Path
import fresh_runner as runner
from workflow import atomic
from common import need,private_json
# Complete the cross-engine matrix using existing read-only project checks.
REQUESTS=[('drako-tools','codex'),('drako-map','claude')]
BASE=Path.home()/'.config/drako-plane/native-batches'

def path_for(value):
 p=Path(value).absolute();need(p.parent==BASE and re.fullmatch(r'batch_[0-9a-f]{32}\.json',p.name) is not None,'Use the private native batch root');need(not p.is_symlink(),'Symlink batch refused');return p

def run(cpath,ticket,state_path):
 p=path_for(state_path);BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
 with p.with_suffix('.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if p.exists():
   state=private_json(p);need(state['config']==str(Path(cpath).resolve()) and state['ticket']==ticket and state['requests']==[list(x) for x in REQUESTS],'Batch identity changed')
  else:
   state={'schema':'drako.native-project-batch.v1','config':str(Path(cpath).resolve()),'ticket':ticket,'requests':[list(x) for x in REQUESTS],'runs':[],'phase':'running'};atomic(p,state)
  script=Path(runner.__file__).resolve()
  for index,(profile,engine) in enumerate(REQUESTS):
   if len(state['runs'])<=index:
    # Receipt and task sources are freshly gathered immediately before this run,
    # never reused from the previous project or engine.
    output=subprocess.check_output([sys.executable,'-B',str(script),'prepare','--config',state['config'],'--ticket',ticket,'--profile',profile,'--engine',engine],text=True)
    row=json.loads(output);row.update(profile=profile,engine=engine);state['runs'].append(row);atomic(p,state)
   d=Path(state['runs'][index]['run_dir']);current=private_json(d/'state.json')
   # Repeated batch delivery never invokes an already completed native model.
   if current['phase']!='published':runner.run(d)
   observed=private_json(d/'state.json');need(observed['phase']=='published','Native run incomplete');state['runs'][index]['result']=observed;atomic(p,state)
  state['phase']='published';atomic(p,state);print(json.dumps({'state':str(p),'phase':state['phase'],'runs':state['runs']}))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',default=str(Path.home()/'.config/drako-plane/project-runner.json'));p.add_argument('--ticket',required=True);p.add_argument('--state',default=str(BASE/('batch_'+uuid.uuid4().hex+'.json')));a=p.parse_args()
 try:run(a.config,a.ticket,a.state)
 except Exception as error:print(json.dumps({'status':'BLOCKED','error':str(error)[:350],'state':a.state}));raise SystemExit(1)
