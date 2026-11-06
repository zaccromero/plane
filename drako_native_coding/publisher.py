"""Reviewed native coding delivery; commit/PR/trace/evidence recovery never replays the model."""
import argparse,fcntl,json,os,subprocess,sys
from pathlib import Path
import coding
from common import atomic,private_json,need,payload_hash,ticket_context
from agent_lane import load_binding
from workflow import post_evidence
from trace_bridge import stage,deliver
REPO='zaccromero/drako-claude-config'

def review_gate(review,check,report,current):
 need(review.get('p0')==0 and review.get('p1')==0 and review.get('release_gate_passed') is True,'Independent exact-output review/release gate required')
 need(check['status']=='PASS' and check['files']==report['files']==review['files']==current,'Source changed after native test/review')
 need(report['check_sha256']==review['check_sha256']==payload_hash(check),'Reviewed check binding changed')

def run(directory):
 d=Path(directory).resolve(strict=True);j=private_json(d/'job.json');need(d.parent==coding.ROOT/'.drako/runs' and d.name==j['run_id'],'Wrong publication root')
 with (d/'runner.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);state=private_json(d/'state.json');need(state['phase'] in ['executed','published'],'No unexecuted/unknown publication or model replay');head=coding.fresh.git(coding.ROOT,'rev-parse','HEAD')
  if head!=state.get('delivery_head',j['source_head']):
   intent=private_json(d/'commit-intent.json');need(not state.get('delivery_head') and coding.fresh.git(coding.ROOT,'rev-parse','HEAD^')==intent['parent']==j['source_head'] and coding.fresh.git(coding.ROOT,'log','-1','--format=%s')==intent['message'] and intent['files']==coding.files(),'Unrecognized commit outcome');state['delivery_head']=head;state['commit_reconciled']=True;atomic(d/'state.json',state)
  d,j,c=coding.load(d);check=private_json(d/'results/check.json');report=private_json(d/'results/report.json');review=private_json(d/'review.json');review_gate(review,check,report,coding.files());wait=private_json(d/'native-wait.json');need(wait['exit_code']==0 and wait['ack'] and set(wait['calls'])==coding.TOOLS and report['writes']>0,'Actual native coding evidence absent')
  need(private_json(d/'startup-ack.json')['receipt']==j['live_context']['receipt'],'Startup receipt changed');client=load_binding(c['binding']);need(ticket_context(client.get(j['ticket_id']))==private_json(d/'ticket.json'),'Ticket changed')
  sys.path.insert(0,c['hermes_source']);from hermes_cli.agent_tasks import ControllerSupervisor,group_dead
  with ControllerSupervisor(board='default',board_db=Path(c['board_db']),project_path=coding.ROOT) as sup:
   t=sup.request({'action':'show','id':report['claim_id']})['result']['task'];need(t['owner']==report['native_actor'] and sorted(t['scopes'])==j['expected_scopes'] and group_dead(t['owner']),'Native writer/scope not quiescent/exact')
   if t['state']=='finish_pending':t=sup.request({'action':'settle','id':t['id'],'revision':t['revision']})['result']['task']
   need(t['state']=='owner_review','Native delivery not settled')
  git=lambda *a:coding.fresh.git(coding.ROOT,*a)
  need(git('remote','get-url','origin') in ['https://github.com/zaccromero/drako-claude-config.git','git@github.com:zaccromero/drako-claude-config.git'],'Wrong publication repository')
  if not state.get('delivery_head'):
   need(not (d/'commit-intent.json').exists(),'Uncertain commit; retain exact intent');need(set(git('diff','--name-only','HEAD').splitlines())==set(coding.FILES),'Unexpected/missing coding diff');message='Keep empty mapped context refreshes quiet';atomic(d/'commit-intent.json',{'parent':j['source_head'],'files':coding.files(),'message':message});subprocess.run(['git','add','--',*coding.FILES],cwd=coding.ROOT,check=True);need(set(git('diff','--cached','--name-only').splitlines())==set(coding.FILES),'Unexpected staged source');subprocess.run(['git','commit','-m',message],cwd=coding.ROOT,check=True);state['delivery_head']=git('rev-parse','HEAD');atomic(d/'state.json',state)
  need(set(git('diff','--name-only',j['source_head'],state['delivery_head']).splitlines())==set(coding.FILES),'Delivery exceeds source scope');need(not git('status','--porcelain','--untracked-files=no'),'Dirty delivery source')
  subprocess.run(['git','push','-u','origin','HEAD:refs/heads/'+j['branch']],cwd=coding.ROOT,check=True,timeout=60);query=['gh','pr','list','--repo',REPO,'--head',j['branch'],'--base','main','--state','all','--json','number,url,headRefOid,state'];prs=json.loads(subprocess.check_output(query,text=True))
  if not prs:
   need(not (d/'pr-intent.json').exists(),'PR write uncertain; query before retry');body=d/'pr-body.md';body.write_text('A mapped Git repository without recognized curated context sections can produce an empty render while its live receipt succeeds, causing explicit refresh to split empty text and raise ValueError. Preserve quiet successful normal/hook behavior for absent or empty packs while keeping explicit live receipts and nonempty context behavior.\n\nNative Claude accepted the existing exact source reservation in the isolated checkout, read baseline context, edited only the loader and its tests, and passed independent actual-Git regressions plus all preserved/additive loader tests under network/private-data/source-write restrictions. Current-main source release contracts and independent scoped host review passed. No hooks, permissions, credentials, curated decisions or primary checkout changed.\n\nDRAKO32; native run '+j['run_id']+'; source base '+j['source_head']+'; delivery '+state['delivery_head']+'. Regression contracts: '+', '.join(str(x['tests'])+' tests' for x in check['results'])+'. Hosted CI is separate. Merge and deployment not performed.\n');atomic(d/'pr-intent.json',{'head':state['delivery_head'],'status':'submission_started'});subprocess.run(['gh','pr','create','--repo',REPO,'--base','main','--head',j['branch'],'--title','Keep empty mapped project context refreshes quiet','--body-file',str(body)],check=True,timeout=60);prs=json.loads(subprocess.check_output(query,text=True))
  need(len(prs)==1 and prs[0]['state']=='OPEN' and prs[0]['headRefOid']==state['delivery_head'],'PR identity mismatch');atomic(d/'pr-receipt.json',prs[0]);sys.path.insert(0,c['control_lib']);from drako_control.control_plane import RunJournal
  os.environ['DRAKO_TRACING']='off';journal=RunJournal(coding.ROOT);run=journal.load(j['run_id'])
  if run['status']!='completed':journal.event(run,'task_completed',{'agent_id':'claude','gate':'native coding + exact reviewed source + actual tests + PR'});run['status']='completed';journal.save(run)
  envelope=stage(d);trace=deliver(envelope,c['trace_host'],c['trace_identity']);score=deliver({'kind':'score','trace_id':envelope['trace_id'],'root_span_id':envelope['root_span_id'],'passed':True},c['trace_host'],c['trace_identity']);need(trace['trace_observed'] and score['score_observed'] and score['value'] is True,'Backend trace/eval absent')
  expected={'ticket_id':j['ticket_id'],'project_id':client.project,'run_id':j['run_id'],'claim_id':t['id']};evidence={**expected,'context_sha256':j['context_sha256'],'checks_passed':True,'trace_observed':True,'score_observed':True,'trace_id':envelope['trace_id'],'score_id':score['score_id'],'source_repo':REPO,'source_base':j['source_head'],'delivery_head':state['delivery_head'],'runner_head':j['runner_head'],'pr':prs[0]['url'],'native_invocations':state['native_invocations'],'native_writes':report['writes'],'test_attempts':report['tests'],'test_counts':[x['tests'] for x in check['results']],'owner_acceptance':'pending','merge':'NOT_RUN','deployment':'NOT_RUN'};posted=post_evidence(client,evidence,expected,private_json(d/'context-manifest.json'),d/'evidence');atomic(d/'evaluation.json',evidence);atomic(d/'trace-receipt.json',trace);atomic(d/'score-receipt.json',score);state.update(phase='published',pr=prs[0]['url'],comment_id=posted['comment_id'],trace_id=envelope['trace_id'],score_id=score['score_id']);atomic(d/'state.json',state);print(json.dumps(state))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory');a=p.parse_args()
 try:run(a.directory)
 except Exception as error:print(json.dumps({'status':'BLOCKED','error':str(error)[:350]}));raise SystemExit(1)
