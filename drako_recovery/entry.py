"""Opt-in preseal recovery over the existing trusted project profile."""
import argparse,contextlib,io,json,sys
from pathlib import Path
DIST=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(DIST/'drako_profiles'))
import adapter as base
from recovery import RecoveryWorker

QUALIFICATION_FILES=('drako_recovery_fixture/profile.ts','drako_recovery_fixture/profile.test.ts')
QUALIFICATION_TASK='This is an isolated failure-recovery qualification, not production map work. Implement the finite elevation contract and add regression tests in the two fixed fixture files. For the FIRST candidate only, deliberately implement the validation with a separate helper function so code tests pass but the actual immutable single-function source-policy rejects it. Call run_tests then result. On REPAIR_REQUIRED, automatically inline the helper into the one exported summariseProfile function, rerun tests, and call result again. Never change gates or permissions and never ask for ownership approval. Preserve the baseline test text. Keep writes <=6 and test attempts <=3. Finish only when result returns status PASS. Both fixture files must differ from baseline.'

def qualification_root(root):
 root=Path(root).resolve(strict=True)
 base.need(root==Path.home()/'code/.worktrees/plane/feat/preseal-recovery-qualification','Wrong qualification worktree')
 base.need(base.git(root,'rev-parse','--show-toplevel')==str(root),'Wrong qualification root')
 base.need(Path(base.git(root,'rev-parse','--path-format=absolute','--git-common-dir')).resolve()==Path.home()/'code/projects/plane/.git','Wrong qualification Git identity')
 base.need(base.git(root,'remote','get-url','origin') in ['https://github.com/zaccromero/plane.git','git@github.com:zaccromero/plane.git'],'Wrong qualification origin')
 return root

def configure(root,qualification=False):
 if qualification:
  base.validate_project=qualification_root;base.FILES=QUALIFICATION_FILES;base.REPO='zaccromero/plane';base.CATALOG='isolated-preseal-recovery-qualification';base.TASK=QUALIFICATION_TASK
  base.PROFILE={**base.PROFILE,'context':['README.md','package.json'],'title':'Isolated recovery qualification'}
 base.configure(root)

def prepare(cpath,ticket,qualification):
 output=io.StringIO()
 with contextlib.redirect_stdout(output):base.prepare(cpath,ticket)
 value=json.loads(output.getvalue());d=Path(value['run_dir']);j=base.private_json(d/'job.json')
 j['qualification']=qualification;j['recovery_mode']='independent-before-seal-v1'
 paths=[Path(x['path']) for x in base.private_json(d/'context-manifest.json')['files']]
 paths+=sorted((DIST/'drako_recovery').glob('*.py'))
 if qualification:paths += [base.ROOT/'node_modules/typescript/lib/typescript.js',base.ROOT/'node_modules/typescript/package.json']
 ctx=base.manifest(paths);j['context_sha256']=ctx['sha256']
 base.atomic(d/'job.json',j);base.atomic(d/'context-manifest.json',ctx)
 args=['-B',str(DIST/'drako_recovery/entry.py'),'--project',str(base.ROOT)]
 if qualification:args+=['--qualification']
 args+=['server',str(d)]
 base.atomic(d/'mcp.json',{'mcpServers':{'drako_code':{'type':'stdio','command':base.config(cpath)['python'],'args':args,'env':{'AGENT_TASK_SESSION_CONTEXT':'${AGENT_TASK_SESSION_CONTEXT}','PYTHONDONTWRITEBYTECODE':'1'}}}})
 c=base.config(cpath);sys.path.insert(0,c['control_lib']);from drako_control.control_plane import RunJournal
 journal=RunJournal(base.ROOT);run=journal.load(j['run_id']);run['correlation_id']=ctx['sha256']
 if qualification:run.update(project_id='drako-recovery-qualification',crew_id='isolated-real-failure-test')
 journal.save(run)
 # Existing trace context contains the old binding; regenerate from this final prepared manifest.
 from drako_control import tracing
 tracing.bind_run(d,run,runs_dir=journal.runs_dir,env={'DRAKO_TRACING':'on','DRAKO_TRACE_ENDPOINT':'http://127.0.0.1:1/v1/traces'})
 print(json.dumps(value))

def qualification_evidence(expected,j,state,payload,score,files,attempts):
 return {**expected,'context_sha256':j['context_sha256'],'execution_context_sha256':j.get('execution_context_sha256',j['context_sha256']),'checks_passed':True,'trace_observed':True,'score_observed':True,'trace_id':payload['trace_id'],'score_id':score['score_id'],'qualification':True,'files':files,'native_invocations':state['native_invocations'],'host_attempts':attempts,'owner_accept_calls':0,'owner_acceptance':'pending'}

def qualify_publication(d,j,c,state):
 base.need(state['phase'] in ['executed','published'],'Uncertain/live execution; no relaunch')
 check=base.common.checked(d,j);review=base.private_json(d/'review.json');report=base.private_json(d/'results/report.json')
 base.need(review['files']==base.common.files() and review['check_sha256']==base.payload_hash(check) and review['context_sha256']==j.get('execution_context_sha256',j['context_sha256']),'Qualification verification binding mismatch')
 base.need(report['check_sha256']==base.payload_hash(check) and report['context_sha256']==j.get('execution_context_sha256',j['context_sha256']),'Worker report mismatch')
 sys.path.insert(0,c['hermes_source']);from hermes_cli.agent_tasks import ControllerSupervisor
 with ControllerSupervisor(board='default',board_db=Path(c['board_db']),project_path=base.ROOT) as sup:
  claim=sup.request({'action':'show','id':report['claim_id']})['result']['task']
  base.need(claim['owner']==report['native_actor'] and base.common.exact_scopes(claim['scopes'],list(base.FILES)+[str((d/'results').relative_to(base.ROOT))]),'Wrong qualification claim')
  if claim['state']=='finish_pending':claim=sup.request({'action':'settle','id':claim['id'],'revision':claim['revision']})['result']['task']
  base.need(claim['state']=='owner_review','Writer still live or claim changed')
 client=base.load_binding(c['binding']);base.need(base.ticket_context(client.get(j['ticket_id']))==base.private_json(d/'ticket-context.json'),'Ticket changed')
 sys.path.insert(0,c['control_lib']);from drako_control.control_plane import RunJournal
 journal=RunJournal(base.ROOT);run=journal.load(j['run_id'])
 if run['status']!='completed':journal.event(run,'task_completed',{'agent_id':'claude','gate':'real-preseal-failure-and-same-owner-repair'});run['status']='completed';journal.save(run)
 payload=base.stage(d);trace=base.deliver(payload,c['trace_host'],c['trace_identity']);score=base.deliver({'kind':'score','trace_id':payload['trace_id'],'root_span_id':payload['root_span_id'],'passed':True},c['trace_host'],c['trace_identity'])
 base.need(trace['trace_observed'] and score['score_observed'] and score['value'] is True,'Backend proof missing')
 expected={'ticket_id':j['ticket_id'],'project_id':j['plane_project'],'run_id':j['run_id'],'claim_id':claim['id']}
 evidence=qualification_evidence(expected,j,state,payload,score,base.common.files(),len(base.private_json(d/'preseal-history.json')))
 receipt=base.post_evidence(client,evidence,expected,base.private_json(d/'context-manifest.json'),d/'evidence')
 for name,v in [('trace-receipt.json',trace),('score-receipt.json',score),('evaluation.json',evidence)]:base.atomic(d/name,v)
 state.update(phase='published',trace_id=payload['trace_id'],score_id=score['score_id'],comment_id=receipt['comment_id']);base.atomic(d/'state.json',state);print(json.dumps(state))

def run(directory,interrupt=False):
 import fcntl,os
 d,j,c=base.load_job(directory)
 base.need(j.get('recovery_mode')=='independent-before-seal-v1','Legacy job cannot be implicitly upgraded')
 with open(d/'runner.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);state=base.private_json(d/'state.json')
  if state['phase']=='prepared':base.engine.execute(d,j,c,state)
  if interrupt and state['phase']=='executed':print(json.dumps({'phase':'executed','interrupted':True}),flush=True);os._exit(86)
  if j.get('qualification'):qualify_publication(d,j,c,state)
  else:base.publication(d,j,c,state)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',required=True);p.add_argument('--qualification',action='store_true');subs=p.add_subparsers(dest='action',required=True)
 a=subs.add_parser('prepare');a.add_argument('--config',required=True);a.add_argument('--ticket',required=True)
 for name in ['run','resume','server']:
  a=subs.add_parser(name);a.add_argument('directory')
  if name=='run':a.add_argument('--interrupt-after-execution',action='store_true')
 args=p.parse_args()
 try:
  configure(args.project,args.qualification)
  if args.action=='prepare':prepare(args.config,args.ticket,args.qualification)
  elif args.action=='server':base.service.serve(RecoveryWorker(args.directory))
  else:run(args.directory,getattr(args,'interrupt_after_execution',False))
 except Exception as error:print(json.dumps({'status':'BLOCKED','error':str(error)[:500]}));raise SystemExit(1)
