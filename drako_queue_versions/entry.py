"""Version-aware continuation of the existing bounded active-lane runner."""
import argparse,contextlib,fcntl,io,json,subprocess,sys,uuid
from pathlib import Path
DIST=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(DIST),str(DIST/'drako_resilient_queue')]
from drako_resilient_queue import entry as q
b=q.b
import compatibility as compat
FILES=sorted(Path(__file__).parent.glob('*.py'))+[Path(__file__).with_name('contract.json'),Path(__file__).with_name('nullish.test.mjs')]
_original_manifest=b.manifest

def version_manifest(paths):
 extra=list(FILES)
 for p in paths:
  if Path(p).name=='admission.json' and (Path(p).parent/'continuation.json').exists():extra.append(Path(p).parent/'continuation.json')
 return _original_manifest(list(dict.fromkeys([*paths,*extra])))
b.manifest=version_manifest

def request_key(config,tickets,branches,faults):
 b.need(1<=len(tickets)==len(set(tickets))==len(branches)<=2,'One or two distinct admitted tickets required')
 branches=[q.branch_name(x) for x in branches];b.need(len(set(branches))==len(branches),'Distinct branches required')
 return {'config_path':str(Path(config).resolve(strict=True)),'ticket_ids':tickets,'branches':branches,'fault_plan':['after_tests','after_verified'] if faults else []}

def existing(parent,key):
 route=parent/'successor.json'
 if not route.exists():return None
 link=b.private_json(route);child,a,s,c=compat.load(link['queue_dir'])
 b.need(b.common.digest(child/'admission.json')==link['admission_sha256'],'Successor routing drift')
 b.need(a['config_path']==key['config_path'] and [t['id'] for t in a['tickets']]==key['ticket_ids'] and a['branches']==key['branches'] and a.get('fault_plan',[])==key['fault_plan'],'Parent already has a different successor; preserve it')
 b.need(a['runner_head']==b.git(DIST,'rev-parse','HEAD'),'Existing successor belongs to another version; use its pinned runtime')
 b.need(b.private_json(child/'continuation.json')['parent_queue']==str(parent),'Successor parent drift')
 return {'queue_dir':str(child),'tickets':key['ticket_ids'],'admission_reused':True}

def init(config,tickets,branches,parent,faults=False):
 key=request_key(config,tickets,branches,faults);parent=compat.location(parent)
 with open(parent/'queue.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  prior=existing(parent,key)
  if prior:print(json.dumps(prior));return
  p,a,s,c,proof=compat.previous(parent)
  b.need(c==b.config(config),'Continuation config changed')
  lane=q.owner(c,s['lane']['id']);b.need(lane['owner']==s['lane']['owner'] and lane['revision']==s['lane']['revision'] and b.common.exact_scopes(lane['scopes'],s['lane']['scopes']),'Parent owner/revision/scope changed')
  b.need(not b.git(b.ROOT,'status','--porcelain','--untracked-files=no'),'Parent tracked work dirty')
  for branch in key['branches']:b.need(not b.git(b.ROOT,'branch','--list',branch),'Preserve existing branch')
  client=b.load_binding(c['binding']);contexts=[b.ticket_context(client.get(x)) for x in tickets]
  intent_path=parent/'version-transition-intent.json'
  if intent_path.exists():
   intent=b.private_json(intent_path);b.need(intent['request']==key and intent['proof']==proof and intent['contexts']==contexts,'Transition intent drift; no new admission')
  else:
   child=b.ROOT/'.drako/queues'/('queue_'+uuid.uuid4().hex)
   intent={'schema':'drako.transition-intent.v1','request':key,'proof':proof,'contexts':contexts,'queue_dir':str(child)};b.atomic(intent_path,intent)
  child=Path(intent['queue_dir']);b.need(child.parent==(b.ROOT/'.drako/queues') and child.name.startswith('queue_'),'Wrong transition destination')
  admission={'schema':'drako.queue-admission.v1','queue_id':child.name,'project_root':str(b.ROOT),'source_repo':b.REPO,'source_head':b.git(b.ROOT,'rev-parse','HEAD'),'runner_head':b.git(DIST,'rev-parse','HEAD'),'config_path':key['config_path'],'tickets':contexts,'branches':key['branches'],'fault_plan':key['fault_plan'],'max_tickets':len(tickets),'file_scope':list(b.FILES),'lifecycle':'retain active lane; no owner acceptance or merges','authority':'owner-requested compatible-version continuation with real interrupted ticket','continuation_contract_sha256':b.common.digest(compat.CONTRACT)}
  state={'phase':'ready','index':0,'jobs':[],'completed':[],'lane':s['lane'],'native_session_id':s['native_session_id'],'parent_completion':s['completed'][-1]}
  child.mkdir(mode=0o700,exist_ok=True)
  for name,value in [('admission.json',admission),('state.json',state),('continuation.json',proof)]:
   path=child/name
   if path.exists():b.need(b.private_json(path)==value,'Partially admitted successor changed; preserve it')
   else:b.atomic(path,value)
  # This link commits the transition. Retry reads this exact child; no second queue.
  b.atomic(parent/'successor.json',{'queue_dir':str(child),'admission_sha256':b.common.digest(child/'admission.json'),'continuation_sha256':b.common.digest(child/'continuation.json')})
  print(json.dumps({'queue_dir':str(child),'tickets':tickets,'admission_reused':False}))

_original_prepare=q.prepare_one
def prepare_one(*args):
 d=_original_prepare(*args);j=b.private_json(d/'job.json');c=b.config(j['config_path'])
 b.atomic(d/'mcp.json',{'mcpServers':{'drako_code':{'type':'stdio','command':c['python'],'args':['-B',str(Path(__file__)),'--project',str(b.ROOT),'server',str(d)],'env':{'AGENT_TASK_SESSION_CONTEXT':'${AGENT_TASK_SESSION_CONTEXT}','PYTHONDONTWRITEBYTECODE':'1'}}}})
 return d
q.prepare_one=prepare_one

# Extra immutable acceptance for the admitted nullish-input project ticket.
_original_verify=q.recovery_module.map_verify
def verify(d,j,c,root):
 value=_original_verify(d,j,c,root)
 from verifier import host_profile
 import shutil
 scratch=d/'verification-scratch';snapshot=d/'verification-snapshot';shutil.copyfile(Path(__file__).with_name('nullish.test.mjs'),scratch/'nullish.test.mjs')
 log=d/'verification-logs/nullish.log';env={'PATH':str(Path(c['node']).parent)+':/usr/bin:/bin','HOME':str(scratch),'TMPDIR':str(scratch),'DRAKO_TARGET_SOURCE':str(scratch/'profile.ts')}
 with log.open('w') as out:r=subprocess.run([c['workload'],'run','/usr/bin/env','-i',*[k+'='+v for k,v in env.items()],'/usr/bin/sandbox-exec','-p',host_profile(snapshot,scratch,c['node']),c['node'],'--experimental-strip-types','--experimental-test-isolation=none','--test',str(scratch/'nullish.test.mjs')],cwd=scratch,stdout=out,stderr=subprocess.STDOUT,timeout=45)
 b.need(b.tap_pass(log.read_text(),r.returncode),'Automatic verification failed: nullish contract')
 value['gates'].append({'gate':'nullish','status':'PASS','exit_code':r.returncode,'log':str(log),'sha256':b.common.digest(log)});b.atomic(d/'review.json',value);return value
q.recovery_module.map_verify=verify

def dispatch(directory):
 p,a,s,c=compat.load(directory)
 if a['runner_head']==b.git(DIST,'rev-parse','HEAD'):return q.run(directory)
 # Older jobs are never repinned or imported into this runtime.
 b.need(bool(s['jobs']),'Unexecuted historical queue lacks a pinned runtime; hold')
 j=b.private_json(Path(s['jobs'][0])/'job.json');runtime=compat.runtime(j['runner_root'],a['runner_head']);b.verify_context(b.private_json(Path(s['jobs'][0])/'context-manifest.json'))
 old=Path(runtime['runner_root']);entry=old/'drako_queue_versions/entry.py' if 'continuation_contract_sha256' in a else old/'drako_resilient_queue/entry.py'
 subprocess.run([c['python'],'-B',str(entry),'--project',str(b.ROOT),'resume',str(p)],check=True)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',required=True);sub=p.add_subparsers(dest='action',required=True)
 a=sub.add_parser('init');a.add_argument('--config',required=True);a.add_argument('--ticket',action='append',required=True);a.add_argument('--branch',action='append',required=True);a.add_argument('--continue-from',required=True);a.add_argument('--interrupt-qualification',action='store_true')
 for name in ['run','resume','server']:a=sub.add_parser(name);a.add_argument('directory')
 args=p.parse_args()
 try:
  q.configure(args.project)
  if args.action=='init':init(args.config,args.ticket,args.branch,args.continue_from,args.interrupt_qualification)
  elif args.action=='server':b.service.serve(q.InterruptibleWorker(args.directory))
  else:dispatch(args.directory)
 except Exception as error:print(json.dumps({'status':'BLOCKED','error':str(error)[:600]}));raise SystemExit(1)
