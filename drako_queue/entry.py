"""Bounded admitted ticket queues over a persistent, active native lane."""
import argparse,contextlib,fcntl,io,json,os,subprocess,sys,uuid
from pathlib import Path
DIST=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(DIST),str(DIST/'drako_profiles'),str(DIST/'drako_recovery')]
from drako_recovery import entry as recovery_entry
b=recovery_entry.base
from worker import QueueWorker,active_result

def configure(root):
 b.configure(root);b.service.Worker.call=active_result

def branch_name(name):
 b.need(isinstance(name,str) and name.startswith('feat/'),'Queue branch must be isolated feature branch')
 subprocess.run(['git','check-ref-format','--branch',name],check=True,capture_output=True);return name

def _init(config,tickets,branches,continue_from=None):
 b.need(len(tickets)==len(set(tickets))==len(branches)==2,'Exactly two distinct owner-admitted tickets required')
 branches=[branch_name(x) for x in branches];b.need(len(set(branches))==2,'Distinct ticket branches required')
 b.need(not b.git(b.ROOT,'status','--porcelain','--untracked-files=no'),'Clean admitted worktree required')
 parent=None;parent_q=None
 if continue_from:
  parent_q,_,parent,parent_config=load_queue(continue_from)
  b.need(parent['phase']=='idle_active' and parent_config==b.config(config),'Only this idle active lane can continue')
  lane=owner(parent_config,parent['lane']['id']);b.need(lane['owner']==parent['lane']['owner'] and lane['revision']==parent['lane']['revision'],'Parent lane changed')
  b.need(not (parent_q/'successor.json').exists(),'Parent already has a successor; reuse it')
  b.need(b.git(b.ROOT,'rev-parse','HEAD')==parent['completed'][-1]['delivery_head'],'Parent delivery changed')
  for name in branches:b.need(not b.git(b.ROOT,'branch','--list',name),'Preserve existing successor branch')
 else:
  b.need(b.git(b.ROOT,'branch','--show-current')==branches[0],'Use admitted first branch')
  b.need(not b.git(b.ROOT,'branch','--list',branches[1]),'Preserve existing second branch')
 c=b.config(config);client=b.load_binding(c['binding']);contexts=[b.ticket_context(client.get(x)) for x in tickets]
 q=b.ROOT/'.drako/queues'/('queue_'+uuid.uuid4().hex);q.mkdir(parents=True,mode=0o700)
 admission={'schema':'drako.queue-admission.v1','queue_id':q.name,'project_root':str(b.ROOT),'source_repo':b.REPO,'source_head':b.git(b.ROOT,'rev-parse','HEAD'),'runner_head':b.git(DIST,'rev-parse','HEAD'),'config_path':str(Path(config).resolve()),'tickets':contexts,'branches':branches,'max_tickets':2,'file_scope':list(b.FILES),'lifecycle':'retain active lane across verified tickets; no owner acceptance or merges','authority':'owner-requested two-real-ticket queue in current lane'}
 b.atomic(q/'admission.json',admission);b.atomic(q/'state.json',{'phase':'ready','index':0,'jobs':[],'completed':[],'lane':parent['lane'] if parent else None,**({'native_session_id':parent['native_session_id'],'parent_completion':parent['completed'][-1]} if parent else {})})
 if parent_q:b.atomic(parent_q/'successor.json',{'queue_dir':str(q),'admission_sha256':b.common.digest(q/'admission.json')})
 print(json.dumps({'queue_dir':str(q),'tickets':tickets}))

def init(config,tickets,branches,continue_from=None):
 if continue_from:
  parent,_,_,_=load_queue(continue_from)
  with open(parent/'queue.lock','a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   return _init(config,tickets,branches,continue_from)
 return _init(config,tickets,branches)

def load_queue(directory):
 q=Path(directory).resolve(strict=True);b.need(q.parent==(b.ROOT/'.drako/queues').resolve(),'Wrong queue root')
 admission=b.private_json(q/'admission.json');state=b.private_json(q/'state.json')
 b.need(admission['queue_id']==q.name and admission['project_root']==str(b.ROOT) and admission['source_repo']==b.REPO and admission['file_scope']==list(b.FILES),'Queue identity drift')
 b.need(admission['runner_head']==b.git(DIST,'rev-parse','HEAD'),'Queue runner changed; no implicit migration')
 c=b.config(admission['config_path']);return q,admission,state,c

def owner(c,claim):
 sys.path.insert(0,c['hermes_source']);from hermes_cli.agent_tasks import ControllerSupervisor,group_dead
 with ControllerSupervisor(board='default',board_db=Path(c['board_db']),project_path=b.ROOT) as s:t=s.request({'action':'show','id':claim})['result']['task']
 b.need(t['state']=='active' and t['worktree']==str(b.ROOT) and group_dead(t['owner']),'Queue requires exact active lane with exited writer, not terminal/live/unknown owner')
 return t

def prepare_one(q,admission,state,c):
 index=state['index'];b.need(index in [0,1],'Queue bound reached')
 client=b.load_binding(c['binding']);ticket=admission['tickets'][index];b.need(b.ticket_context(client.get(ticket['id']))==ticket,'Admitted ticket changed')
 branch=admission['branches'][index]
 lane=None
 if state['lane']:
  lane=owner(c,state['lane']['id']);b.need(lane['owner']==state['lane']['owner'] and lane['revision']==state['lane']['revision'] and b.common.exact_scopes(lane['scopes'],state['lane']['scopes']),'Lane changed before next ticket')
  previous=state['completed'][-1] if state['completed'] else state['parent_completion'];b.need(not b.git(b.ROOT,'status','--porcelain','--untracked-files=no'),'Prior ticket left dirty tracked work')
  intent=q/('branch-'+str(index)+'-intent.json')
  if b.git(b.ROOT,'branch','--show-current')!=branch:
   b.need(b.git(b.ROOT,'branch','--show-current')==previous['branch'] and b.git(b.ROOT,'rev-parse','HEAD')==previous['delivery_head'],'Previous source/branch drift')
   b.need(not b.git(b.ROOT,'branch','--list',branch),'Preserve existing branch')
   if not intent.exists():b.atomic(intent,{'branch':branch,'parent':previous['delivery_head']})
   subprocess.run(['git','switch','-c',branch,previous['delivery_head']],cwd=b.ROOT,check=True,capture_output=True)
  b.need(intent.exists() and b.git(b.ROOT,'rev-parse','HEAD')==previous['delivery_head'],'Unrecognized next branch')
 prepare_intent=q/('prepare-'+str(index)+'-intent.json');b.need(not prepare_intent.exists(),'Uncertain preparation; reconcile rather than creating another job');b.atomic(prepare_intent,{'ticket_id':ticket['id'],'branch':branch})
 output=io.StringIO()
 with contextlib.redirect_stdout(output):recovery_entry.prepare(admission['config_path'],ticket['id'],False)
 value=json.loads(output.getvalue());d=Path(value['run_dir']);j=b.private_json(d/'job.json')
 expected=list(b.FILES)+[str((d/'results').relative_to(b.ROOT))] if lane is None else sorted(set(lane['scopes']+[str((d/'results').relative_to(b.ROOT))]))
 j.update(queue_mode='active-lane-v1',queue_id=q.name,queue_admission=str(q/'admission.json'),queue_expected_scopes=expected,queue_pr_base='main' if lane is None else previous['branch'],queue_title=ticket['name'])
 if lane:
  j.update(resume_claim=lane['id'],resume_revision=lane['revision'],queue_previous_owner=lane['owner'],queue_previous_scopes=lane['scopes'],native_session_id=state['native_session_id'])
 paths=[Path(x['path']) for x in b.private_json(d/'context-manifest.json')['files']]+[q/'admission.json']+sorted((DIST/'drako_queue').glob('*.py'))
 ctx=b.manifest(paths);j['context_sha256']=ctx['sha256'];b.atomic(d/'job.json',j);b.atomic(d/'context-manifest.json',ctx)
 b.atomic(d/'mcp.json',{'mcpServers':{'drako_code':{'type':'stdio','command':c['python'],'args':['-B',str(DIST/'drako_queue/entry.py'),'--project',str(b.ROOT),'server',str(d)],'env':{'AGENT_TASK_SESSION_CONTEXT':'${AGENT_TASK_SESSION_CONTEXT}','PYTHONDONTWRITEBYTECODE':'1'}}}})
 sys.path.insert(0,c['control_lib']);from drako_control.control_plane import RunJournal
 from drako_control import tracing
 journal=RunJournal(b.ROOT);run=journal.load(j['run_id']);run['correlation_id']=ctx['sha256'];run['crew_id']='continuous-admitted-queue';journal.save(run);tracing.bind_run(d,run,runs_dir=journal.runs_dir,env={'DRAKO_TRACING':'on','DRAKO_TRACE_ENDPOINT':'http://127.0.0.1:1/v1/traces'})
 state['jobs'].append(str(d));state.setdefault('native_session_id',j['native_session_id']);b.atomic(q/'state.json',state);prepare_intent.unlink();return d

def run(directory):
 q,admission,state,c=load_queue(directory)
 with open(q/'queue.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  while state['index']<2:
   index=state['index'];d=Path(state['jobs'][index]) if len(state['jobs'])>index else prepare_one(q,admission,state,c)
   d,j,c=b.load_job(d);b.need(j.get('queue_mode')=='active-lane-v1' and j['queue_id']==q.name,'Wrong queued job')
   with open(d/'runner.lock','a') as childlock:
    fcntl.flock(childlock,fcntl.LOCK_EX|fcntl.LOCK_NB);job_state=b.private_json(d/'state.json')
    if job_state['phase']=='prepared':
     import executor
     executor.ROOT=b.ROOT;executor.execute(d,j,c,job_state)
    b.need(job_state['phase'] in ['executed','published'],'Uncertain/live queue execution; no automatic relaunch')
    import publish
    publish.ROOT=b.ROOT;publish.publication(d,j,c,job_state)
   report=b.private_json(d/'results/report.json');lane=owner(c,report['claim_id']);b.need(lane['owner']==report['native_actor'] and b.common.exact_scopes(lane['scopes'],j['queue_expected_scopes']),'Published queue ownership mismatch')
   check=b.common.checked(d,j);review=b.private_json(d/'review.json');b.need(check['files']==review['files']==b.common.files(),'Published output drift')
   receipt={'ticket_id':j['ticket_id'],'run_dir':str(d),'run_id':j['run_id'],'branch':j['publication_branch'],'base':j['queue_pr_base'],'source_head':j['source_head'],'delivery_head':job_state['delivery_head'],'pr':job_state['pr'],'files':b.common.files(),'claim_id':lane['id'],'owner':lane['owner'],'revision':lane['revision'],'trace_id':job_state['trace_id'],'score_id':job_state['score_id'],'comment_id':job_state['comment_id'],'native_invocations':job_state['native_invocations'],'test_attempts':check['test_attempt'],'ownership_state':'active','owner_accepted':False}
   b.atomic(q/('ticket-'+str(index)+'-completion.json'),receipt);state['completed'].append(receipt);state['lane']={k:lane[k] for k in ['id','owner','revision','scopes']};state['index']+=1;state['phase']='advancing' if state['index']<2 else 'idle_active';b.atomic(q/'state.json',state)
  lane=owner(c,state['lane']['id']);b.need(lane['owner']==state['lane']['owner'] and lane['revision']==state['lane']['revision'],'Idle active lane changed')
  print(json.dumps({'phase':state['phase'],'completed':state['completed'],'lane_id':lane['id'],'lane_state':'active','owner_accept_calls':0}))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',required=True);sub=p.add_subparsers(dest='action',required=True)
 a=sub.add_parser('init');a.add_argument('--config',required=True);a.add_argument('--ticket',action='append',required=True);a.add_argument('--branch',action='append',required=True);a.add_argument('--continue-from')
 for name in ['run','resume','server']:a=sub.add_parser(name);a.add_argument('directory')
 args=p.parse_args()
 try:
  configure(args.project)
  if args.action=='init':init(args.config,args.ticket,args.branch,args.continue_from)
  elif args.action=='server':b.service.serve(QueueWorker(args.directory))
  else:run(args.directory)
 except Exception as error:print(json.dumps({'status':'BLOCKED','error':str(error)[:600]}));raise SystemExit(1)
