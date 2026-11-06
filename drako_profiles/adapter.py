"""One fixed external-project catalog, composed with the merged Plane coding engine."""
import argparse,fcntl,json,os,re,resource,subprocess,sys,uuid
from pathlib import Path
DISTRIBUTION=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(DISTRIBUTION/'drako_coding'),str(DISTRIBUTION/'drako_runner'),str(DISTRIBUTION/'drako')]
import coding_common as common
import coding_runner as engine
import coding_tool_server as service
from coding_common import atomic,need,private_json,config,fingerprint,payload_hash,ticket_context
from agent_lane import load_binding,native_request
from lane import manifest,verify_context
from trace_bridge import stage,deliver
from workflow import post_evidence
PROFILE=json.loads((Path(__file__).with_name('profile.json')).read_text())
REPO=PROFILE['repo']
FILES=tuple(PROFILE['files'])
CATALOG=PROFILE['id']
TASK=PROFILE['task']
ROOT=None
_original_load=common.load_job

def git(root,*args):return subprocess.check_output(['git',*args],cwd=root,text=True).strip()
def validate_project(root):
 root=Path(root).resolve(strict=True)
 need(Path.home()/'code/.worktrees/drako-map' in root.parents,'Use an admitted isolated drako-map worktree')
 need(git(root,'rev-parse','--show-toplevel')==str(root),'Wrong Git root')
 need(Path(git(root,'rev-parse','--path-format=absolute','--git-common-dir')).resolve()==(Path.home()/'code/projects/drako-map/.git').resolve(),'Wrong project Git identity')
 need(git(root,'remote','get-url','origin') in ['https://github.com/zaccromero/drako-map.git','git@github.com:zaccromero/drako-map.git'],'Wrong project origin')
 return root

def configure(root):
 global ROOT
 ROOT=validate_project(root)
 common.ROOT=ROOT;common.FILES[:]=FILES;common.CATALOG=CATALOG
 engine.ROOT=ROOT;service.ROOT=ROOT;engine.legacy.ROOT=ROOT
 service.load_job=load_job

def load_job(directory):
 d,j,c=_original_load(directory)
 need(j['source_repo']==REPO and j['runner_root']==str(DISTRIBUTION),'Wrong catalog source')
 need(git(DISTRIBUTION,'rev-parse','HEAD')==j['runner_head'],'Runner distribution changed')
 validate_project(ROOT)
 return d,j,c

def node_profile(node,root,scratch):
 allowed=[Path(node).resolve(),root/'package.json',*[(root/name) for name in FILES],DISTRIBUTION/'drako_profiles/acceptance.test.mjs',DISTRIBUTION/'package.json']
 literals=set()
 for p in allowed:
  literals.add(str(p));literals.update(str(parent) for parent in p.parents)
 reads=' '.join('(literal '+json.dumps(p)+')' for p in sorted(literals))
 systems=' '.join('(subpath '+json.dumps(p)+')' for p in ['/System','/usr','/opt/homebrew','/Library','/private/etc','/private/var/db','/private/preboot','/dev'])
 return '(version 1)(deny default)(allow process*)(deny process-fork)(deny process-exec (require-not (literal '+json.dumps(str(Path(node).resolve()))+')))(allow mach-lookup)(allow sysctl-read)(allow file-read*)(deny file-read-data (require-not (require-any '+reads+' '+systems+' (subpath '+json.dumps(str(scratch))+'))))(allow file-write* (subpath '+json.dumps(str(scratch))+') (literal "/dev/null"))'

def tap_pass(output,code):
 def count(name):
  found=re.findall(r'^# '+name+r' (\d+)\s*$',output,re.M);return int(found[-1]) if found else None
 n=count('tests')
 return code==0 and n is not None and n>0 and count('pass')==n and all(count(k)==0 for k in ['fail','cancelled','skipped','todo']) and re.search(r'^not ok\b',output,re.M) is None

def node_commands(c,d):
 scratch=d/'test-scratch';scratch.mkdir(mode=0o700,exist_ok=True);sb=d/'node.sb';sb.write_text(node_profile(c['node'],ROOT,scratch));sb.chmod(0o600)
 prefix=[c['workload'],'run','/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME='+str(scratch),'TMPDIR='+str(scratch),'LANG=en_US.UTF-8','DRAKO_TARGET_SOURCE='+str(scratch/'profile.ts'),'/usr/bin/sandbox-exec','-f',str(sb),str(Path(c['node']).resolve()),'--experimental-strip-types','--experimental-test-isolation=none','--test']
 (scratch/'profile.ts').write_text((ROOT/FILES[0]).read_text())
 (scratch/'profile.test.ts').write_text((ROOT/FILES[1]).read_text().replace('../src/profile.js','./profile.ts'))
 return [prefix+[str(DISTRIBUTION/'drako_profiles/acceptance.test.mjs')],prefix+[str(scratch/'profile.test.ts')]]

class ProjectWorker(service.Worker):
 def call(self,name,args):
  if name not in ['read_context','run_tests']:return super().call(name,args)
  need(args=={},'No command/path parameters accepted')
  d,j,c=load_job(self.directory);state_path=d/'results/worker-state.json';need(state_path.exists(),'Read and claim ticket first')
  if name=='run_tests':need(private_json(state_path)['read'],'Read approved context before testing')
  super().call('ticket_read',{})  # Reuse native actor, ticket, manifest, inventory and drift checks.
  with open(d/'results/worker.lock','a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX);state=private_json(state_path)
   t=native_request({'action':'show','id':state['claim_id']});need(t['state']=='active' and t['owner']==state['actor'],'Native writer no longer active')
   need(common.files()==state['files'],'Output drift')
   if name=='read_context':
    state['read']=True;atomic(state_path,state)
    return {'assignment':TASK,'source_repo':REPO,'allowed_files':FILES,'baseline_files':private_json(d/'baseline-files.json'),'public_project_context':private_json(d/'public-context.json'),'independent_acceptance':(DISTRIBUTION/'drako_profiles/acceptance.test.mjs').read_text(),'bounds':{'writes':6,'test_attempts':3}}
   check_path=d/'results/check.json'
   if check_path.exists():
    old=private_json(check_path)
    if old['passed'] and old['files']==common.files():return old
   need(state['tests']<3,'Test budget exhausted');intent=d/'results/test-intent.json';need(not intent.exists(),'Uncertain test execution; reconcile')
   state['tests']+=1;atomic(state_path,state);atomic(intent,{'attempt':state['tests'],'files':common.files()})
   outputs=[]
   for index,argv in enumerate(node_commands(c,d)):
    def limits():resource.setrlimit(resource.RLIMIT_CPU,(20,20));resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
    log=d/'test-scratch'/('node-'+str(state['tests'])+'-'+str(index)+'.log')
    with open(log,'w') as out:r=subprocess.run(argv,cwd=d/'test-scratch',env=dict(os.environ),stdout=out,stderr=subprocess.STDOUT,text=True,timeout=45,preexec_fn=limits)
    output=log.read_text()[-24000:];outputs.append({'exit_code':r.returncode,'output':output})
   need(common.files()==state['files'],'Tests mutated approved source')
   value={'run_id':j['run_id'],'ticket_id':j['ticket_id'],'passed':all(tap_pass(x['output'],x['exit_code']) for x in outputs),'files':common.files(),'test_attempt':state['tests'],'results':outputs,'claim_id':t['id'],'native_actor':t['owner'],'runner_python':c['python'],'node':c['node']}
   atomic(check_path,value);intent.unlink();return value

def prepare(cpath,ticket):
 c=config(cpath);need(Path(c['node']).resolve().is_file(),'Pinned Node binary missing');need(not os.environ.get('AGENT_TASK_SESSION_CONTEXT'),'No nested replacement executor');engine.legacy.doctor(c)
 branch=git(ROOT,'branch','--show-current');need(branch.startswith('feat/'),'An isolated feature branch is required');subprocess.run(['git','check-ref-format','--branch',branch],cwd=ROOT,check=True,capture_output=True)
 need(not git(ROOT,'status','--porcelain','--untracked-files=no'),'Preserve dirty tracked work')
 initial=common.files();need(set(initial)==set(FILES),'Both existing project files required')
 client=load_binding(c['binding']);value=client.get(ticket)
 sys.path.insert(0,c['control_lib']);from drako_control.control_plane import RunJournal
 from drako_control import tracing
 os.environ['DRAKO_TRACING']='off';journal=RunJournal(ROOT);rid='run_'+uuid.uuid4().hex
 run={'run_id':rid,'project_id':'drako-map','pod_id':'plane-project','crew_id':'fixed-project-catalog','task_id':ticket,'runtime_id':'claude-project-coding','correlation_id':'','status':'running','approval_status':'owner-authorized-small-project-task','created_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'agent_ids':['claude'],'room_ids':[],'slot_ids':[],'preflight':{'provider':'claude.ai-subscription'}}
 journal.create(run);d=journal.runs_dir/rid
 atomic(d/'ticket-context.json',ticket_context(value));atomic(d/'baseline-files.json',{n:{'sha256':h,'content':(ROOT/n).read_text()} for n,h in initial.items()})
 atomic(d/'public-context.json',{n:(ROOT/n).read_text() for n in PROFILE['context']})
 paths=[Path(cpath).resolve(),Path(c['binding']).resolve(),d/'ticket-context.json',d/'baseline-files.json',d/'public-context.json',ROOT/'package.json',Path(c['node']).resolve(),DISTRIBUTION/'drako_profiles/acceptance.test.mjs']
 paths += [Path(__file__).with_name('profile.json'),Path(__file__).with_name('source-policy.mjs')]
 for folder in ['drako','drako_runner','drako_coding','drako_project','drako_profiles']:paths+=sorted((DISTRIBUTION/folder).glob('*.py'))
 paths += [Path(c['control_lib'])/'drako_control'/n for n in ['control_plane.py','tracing.py']]
 ctx=manifest(paths)
 j={'schema':'drako.project-lane.v1','run_id':rid,'project_root':str(ROOT),'source_repo':REPO,'runner_root':str(DISTRIBUTION),'runner_head':git(DISTRIBUTION,'rev-parse','HEAD'),'source_head':git(ROOT,'rev-parse','HEAD'),'config_path':str(Path(cpath).resolve()),'ticket_id':ticket,'plane_project':client.project,'catalog':CATALOG,'initial_files':initial,'publication_branch':branch,'native_session_id':str(uuid.uuid4()),'tools':sorted(common.TOOLS),'context_sha256':ctx['sha256'],'timeout_seconds':300,'max_assistant_messages':16,'max_tool_calls':16,'executables':{n:fingerprint(c[n]) for n in ['python','node','claude','session','workload','doctor']}}
 atomic(d/'job.json',j);atomic(d/'context-manifest.json',ctx);atomic(d/'state.json',{'phase':'prepared','native_invocations':0})
 atomic(d/'mcp.json',{'mcpServers':{'drako_code':{'type':'stdio','command':c['python'],'args':['-B',str(DISTRIBUTION/'drako_profiles/adapter.py'),'--project',str(ROOT),'server',str(d)],'env':{'AGENT_TASK_SESSION_CONTEXT':'${AGENT_TASK_SESSION_CONTEXT}','PYTHONDONTWRITEBYTECODE':'1'}}}})
 run['correlation_id']=ctx['sha256'];journal.save(run);tracing.bind_run(d,run,runs_dir=journal.runs_dir,env={'DRAKO_TRACING':'on','DRAKO_TRACE_ENDPOINT':'http://127.0.0.1:1/v1/traces'})
 print(json.dumps({'run_id':rid,'run_dir':str(d),'phase':'prepared','source_repo':REPO}))

def publication(d,j,c,state):
 need(state['phase'] in {'executed','published'},'Unknown/live execution; no relaunch')
 check=common.checked(d,j);report=private_json(d/'results/report.json')
 from verifier import verify
 review=verify(d,j,c,ROOT)
 need(review['p0']==0 and review['p1']==0 and review['full_component_gate'] is True and review['files']==common.files() and review['check_sha256']==payload_hash(check),'Reviewed exact output required')
 need(report['check_sha256']==payload_hash(check) and report['context_sha256']==j.get('execution_context_sha256',j['context_sha256']),'Worker binding mismatch')
 client=load_binding(c['binding']);need(ticket_context(client.get(j['ticket_id']))==private_json(d/'ticket-context.json'),'Ticket changed')
 sys.path.insert(0,c['hermes_source']);from hermes_cli.agent_tasks import ControllerSupervisor
 with ControllerSupervisor(board='default',board_db=Path(c['board_db']),project_path=ROOT) as sup:
  t=sup.request({'action':'show','id':report['claim_id']})['result']['task']
  need(t['owner']==report['native_actor'] and t['owner']['client']=='claude' and common.exact_scopes(t['scopes'],list(FILES)+[str((d/'results').relative_to(ROOT))]),'Wrong coding claim')
  if t['state']=='finish_pending':t=sup.request({'action':'settle','id':t['id'],'revision':t['revision']})['result']['task']
  need(t['state']=='owner_review','Native writer not quiescent/delivered')
 def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
 need(git('remote','get-url','origin') in ['https://github.com/zaccromero/drako-map.git','git@github.com:zaccromero/drako-map.git'],'Unexpected publication repository')
 need(git('branch','--show-current')==j['publication_branch'] and j['publication_branch'].startswith('feat/'),'Unexpected publication branch')
 if not state.get('delivery_head'):
  need(not (d/'commit-intent.json').exists(),'Uncertain commit; reconcile exact head before retry')
  changed=git('diff','--name-only').splitlines();untracked=git('ls-files','--others','--exclude-standard','--',*FILES).splitlines()
  need(set(changed+untracked)==set(FILES),'Unexpected or missing output diff')
  atomic(d/'commit-intent.json',{'files':common.files(),'parent':j['source_head'],'message':'Drako coding delivery '+j['run_id']})
  subprocess.run(['git','add','--',*FILES],cwd=ROOT,check=True)
  need(set(git('diff','--cached','--name-only').splitlines())==set(FILES),'Unexpected staged files')
  subprocess.run(['git','commit','-m','Drako coding delivery '+j['run_id']],cwd=ROOT,check=True)
  state['delivery_head']=git('rev-parse','HEAD');atomic(d/'state.json',state)
 need(set(git('diff','--name-only',j['source_head'],state['delivery_head']).splitlines())==set(FILES),'Delivery commit changed extra paths')
 subprocess.run(['git','push','-u','origin','HEAD:refs/heads/'+j['publication_branch']],cwd=ROOT,check=True,timeout=60)
 command=['gh','pr','list','--repo',REPO,'--head',j['publication_branch'],'--base','main','--state','all','--json','number,url,headRefOid,state']
 prs=json.loads(subprocess.check_output(command,text=True))
 if not prs:
  need(not (d/'pr-intent.json').exists(),'PR submission uncertain; query before retry')
  body=d/'pr-body.md';body.write_text('Reject non-finite elevation samples and derived overflow before reporting gain/loss in drako-map. Native Claude edits only the pure summary function and its tests. Automatic independent acceptance, baseline retention, source policy and canonical package checks gate publication. Network/private data/outside writes denied during generated-code checks. Existing installed runner unchanged.\n\nTicket '+j['ticket_id']+'; run '+j['run_id']+'; runner head '+j['source_head']+'; delivery head '+state['delivery_head']+'. Merge/owner acceptance are separate.\n')
  atomic(d/'pr-intent.json',{'head':state['delivery_head'],'status':'submission_started'})
  subprocess.run(['gh','pr','create','--repo',REPO,'--head',j['publication_branch'],'--base','main','--title',PROFILE['title'],'--body-file',str(body)],check=True,text=True,timeout=60)
  prs=json.loads(subprocess.check_output(command,text=True))
 need(len(prs)==1 and prs[0]['headRefOid']==state['delivery_head'] and prs[0]['state']=='OPEN','PR head/state mismatch')
 atomic(d/'pr-receipt.json',prs[0])
 sys.path.insert(0,c['control_lib']);from drako_control.control_plane import RunJournal
 os.environ['DRAKO_TRACING']='off';journal=RunJournal(ROOT);run=journal.load(j['run_id'])
 if run['status']!='completed':
  journal.event(run,'task_completed',{'agent_id':'claude','gate':'independent-coding-contract-and-reviewed-pr'})
  run['status']='completed';journal.save(run)
 need(ticket_context(client.get(j['ticket_id']))==private_json(d/'ticket-context.json'),'Ticket changed during PR publication')
 payload=stage(d);trace=deliver(payload,c['trace_host'],c['trace_identity'])
 score=deliver({'kind':'score','trace_id':payload['trace_id'],'root_span_id':payload['root_span_id'],'passed':True},c['trace_host'],c['trace_identity'])
 need(trace['trace_observed'] and score['score_observed'] and score['value'] is True,'Backend proof missing')
 expected={'ticket_id':j['ticket_id'],'project_id':j['plane_project'],'run_id':j['run_id'],'claim_id':t['id']}
 evidence={**expected,'context_sha256':j['context_sha256'],'checks_passed':True,'trace_observed':True,'score_observed':True,'trace_id':payload['trace_id'],'score_id':score['score_id'],'source_head':j['source_head'],'source_repo':REPO,'runner_head':j['runner_head'],'execution_source_head':j.get('execution_source_head',j['source_head']),'execution_context_sha256':j.get('execution_context_sha256',j['context_sha256']),'delivery_head':state['delivery_head'],'pr':prs[0]['url'],'files':common.files(),'native_invocations':state['native_invocations'],'test_attempts':check['test_attempt'],'node':c['node'],'owner_acceptance':'pending'}
 receipt=post_evidence(client,evidence,expected,private_json(d/'context-manifest.json'),d/'evidence')
 rows=client.request('GET','/states/');rows=rows if isinstance(rows,list) else rows['results']
 target=engine.legacy.review_transition(state['phase'],client.get(j['ticket_id']),rows)
 if target:client.update(j['ticket_id'],{'state':target});need(client.get(j['ticket_id'])['state']==target,'Review state not confirmed')
 atomic(d/'evaluation.json',evidence);atomic(d/'trace-receipt.json',trace);atomic(d/'score-receipt.json',score)
 state.update(phase='published',pr=prs[0]['url'],comment_id=receipt['comment_id'],trace_id=payload['trace_id'],score_id=score['score_id']);atomic(d/'state.json',state)
 print(json.dumps(state))


def run(directory,interrupt=False):
 d,j,c=load_job(directory)
 with open(d/'runner.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);state=private_json(d/'state.json')
  if state['phase']=='prepared':engine.execute(d,j,c,state)
  if interrupt and state['phase']=='executed':print(json.dumps({'phase':'executed','interrupted':True}),flush=True);os._exit(86)
  publication(d,j,c,state)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',required=True);sub=p.add_subparsers(dest='action',required=True)
 a=sub.add_parser('prepare');a.add_argument('--config',required=True);a.add_argument('--ticket',required=True)
 for n in ['run','resume','server']:
  a=sub.add_parser(n);a.add_argument('directory')
  if n=='run':a.add_argument('--interrupt-after-execution',action='store_true')
 args=p.parse_args()
 try:
  configure(args.project)
  if args.action=='prepare':prepare(args.config,args.ticket)
  elif args.action=='server':service.serve(ProjectWorker(args.directory))
  else:run(args.directory,getattr(args,'interrupt_after_execution',False))
 except Exception as e:
  print(json.dumps({'status':'BLOCKED','error':str(e)[:400]}));raise SystemExit(1)
