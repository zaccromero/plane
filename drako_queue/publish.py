"""Publish verified tickets after writer exit without sealing or releasing lane ownership."""
from adapter import *
def publication(d,j,c,state):
 need(state['phase'] in {'executed','published'},'Unknown/live execution; no relaunch')
 check=common.checked(d,j);report=private_json(d/'results/report.json')
 review=private_json(d/'review.json')
 need(review['p0']==0 and review['p1']==0 and review['full_component_gate'] is True and review['files']==common.files() and review['check_sha256']==payload_hash(check),'Reviewed exact output required')
 need(report['check_sha256']==payload_hash(check) and report['context_sha256']==j.get('execution_context_sha256',j['context_sha256']),'Worker binding mismatch')
 client=load_binding(c['binding']);need(ticket_context(client.get(j['ticket_id']))==private_json(d/'ticket-context.json'),'Ticket changed')
 sys.path.insert(0,c['hermes_source']);from hermes_cli.agent_tasks import ControllerSupervisor,group_dead
 with ControllerSupervisor(board='default',board_db=Path(c['board_db']),project_path=ROOT) as sup:
  t=sup.request({'action':'show','id':report['claim_id']})['result']['task']
  need(t['owner']==report['native_actor'] and t['owner']['client']=='claude' and common.exact_scopes(t['scopes'],j['queue_expected_scopes']),'Wrong queue owner/scope')
  need(t['state']=='active' and group_dead(t['owner']),'Queue owner must remain active with positively exited writer')
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
 command=['gh','pr','list','--repo',REPO,'--head',j['publication_branch'],'--base',j['queue_pr_base'],'--state','all','--json','number,url,headRefOid,state']
 prs=json.loads(subprocess.check_output(command,text=True))
 if not prs:
  need(not (d/'pr-intent.json').exists(),'PR submission uncertain; query before retry')
  body=d/'pr-body.md';body.write_text('Reject non-finite elevation samples and derived overflow before reporting gain/loss in drako-map. Native Claude edits only the pure summary function and its tests. Automatic independent acceptance, baseline retention, source policy and canonical package checks gate publication. Network/private data/outside writes denied during generated-code checks. Existing installed runner unchanged.\n\nTicket '+j['ticket_id']+'; run '+j['run_id']+'; runner head '+j['source_head']+'; delivery head '+state['delivery_head']+'. Merge/owner acceptance are separate.\n')
  atomic(d/'pr-intent.json',{'head':state['delivery_head'],'status':'submission_started'})
  subprocess.run(['gh','pr','create','--repo',REPO,'--head',j['publication_branch'],'--base',j['queue_pr_base'],'--title',j['queue_title'],'--body-file',str(body)],check=True,text=True,timeout=60)
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
 evidence={**expected,'context_sha256':j['context_sha256'],'checks_passed':True,'trace_observed':True,'score_observed':True,'trace_id':payload['trace_id'],'score_id':score['score_id'],'source_head':j['source_head'],'source_repo':REPO,'runner_head':j['runner_head'],'execution_source_head':j.get('execution_source_head',j['source_head']),'execution_context_sha256':j.get('execution_context_sha256',j['context_sha256']),'delivery_head':state['delivery_head'],'pr':prs[0]['url'],'files':common.files(),'native_invocations':state['native_invocations'],'test_attempts':check['test_attempt'],'node':c['node'],'owner_acceptance':'pending','queue_id':j['queue_id'],'ownership_state':'active lane reservation retained'}
 receipt=post_evidence(client,evidence,expected,private_json(d/'context-manifest.json'),d/'evidence')
 rows=client.request('GET','/states/');rows=rows if isinstance(rows,list) else rows['results']
 target=engine.legacy.review_transition(state['phase'],client.get(j['ticket_id']),rows)
 if target:client.update(j['ticket_id'],{'state':target});need(client.get(j['ticket_id'])['state']==target,'Review state not confirmed')
 atomic(d/'evaluation.json',evidence);atomic(d/'trace-receipt.json',trace);atomic(d/'score-receipt.json',score)
 state.update(phase='published',pr=prs[0]['url'],comment_id=receipt['comment_id'],trace_id=payload['trace_id'],score_id=score['score_id']);atomic(d/'state.json',state)
 snapshot=d/'verified-output';snapshot.mkdir(mode=0o700,exist_ok=True)
 for name in FILES:
  p=snapshot/name;p.parent.mkdir(parents=True,exist_ok=True)
  if p.exists():need(common.digest(p)==common.files()[name],'Prior output snapshot changed')
  else:p.write_bytes((ROOT/name).read_bytes());p.chmod(0o600)
 print(json.dumps(state))

