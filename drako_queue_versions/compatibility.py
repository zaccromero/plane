"""Proof-based compatible successor admission; no historical execution migration."""
import json,subprocess
from pathlib import Path
import adapter as b
CORE=('drako','drako_runner','drako_coding','drako_project','drako_profiles','drako_recovery','drako_queue','drako_resilient_queue')
DIST=Path(__file__).resolve().parents[1]
CONTRACT=Path(__file__).with_name('contract.json')

def core_tree(root,head):
 result={}
 for folder in CORE:
  tree=b.git(root,'rev-parse',head+':'+folder)
  b.need(len(tree)==40,'Missing protected runner component');result[folder]=tree
 return result

def runtime(root,head):
 root=Path(root).resolve(strict=True)
 b.need(Path.home()/'code/.worktrees/plane' in root.parents,'Untrusted historical runtime location')
 b.need(Path(b.git(root,'rev-parse','--path-format=absolute','--git-common-dir')).resolve()==(Path.home()/'code/projects/plane/.git').resolve(),'Wrong historical runtime Git identity')
 b.need(b.git(root,'rev-parse','HEAD')==head,'Historical runtime changed; no repinning')
 b.need(not b.git(root,'status','--porcelain','--untracked-files=no'),'Dirty historical runtime')
 b.need(not b.git(root,'ls-files','--others','--exclude-standard','--',*CORE,'drako_queue_versions'),'Untracked runner implementation')
 expected=core_tree(DIST,'HEAD');b.need(core_tree(root,head)==expected,'Protected runner interfaces incompatible')
 return {'runner_root':str(root),'runner_head':head,'protected_trees':expected}

def location(directory):
 p=Path(directory).resolve(strict=True);b.need(p.parent==(b.ROOT/'.drako/queues').resolve(),'Wrong queue root');return p

def load(directory):
 p=location(directory);a=b.private_json(p/'admission.json');s=b.private_json(p/'state.json')
 b.need(a['schema']=='drako.queue-admission.v1' and a['queue_id']==p.name and a['project_root']==str(b.ROOT) and a['source_repo']==b.REPO and a['file_scope']==list(b.FILES),'Parent queue identity drift')
 b.need(1<=len(a['tickets'])==len(a['branches'])==a['max_tickets']<=2,'Parent admission bounds drift')
 return p,a,s,b.config(a['config_path'])

def previous(directory):
 p,a,s,c=load(directory)
 b.need(s['phase']=='idle_active' and s['index']==len(s['jobs'])==len(s['completed'])==len(a['tickets']),'Only completed idle parent can continue')
 proofs=[];old_runtime=None
 for i,done in enumerate(s['completed']):
  d=Path(s['jobs'][i]).resolve(strict=True)
  b.need(d.parent==(b.ROOT/'.drako/runs').resolve() and str(d)==done['run_dir'] and d.name==done['run_id'],'Wrong parent run')
  j=b.private_json(d/'job.json');v=b.private_json(d/'state.json');r=b.private_json(d/'results/report.json');check=b.private_json(d/'results/check.json');review=b.private_json(d/'review.json');verified=b.private_json(d/'results/queue-verified.json')
  b.need(j['queue_id']==p.name and j['run_id']==done['run_id'] and j['ticket_id']==a['tickets'][i]['id']==done['ticket_id'] and j['runner_head']==a['runner_head'] and j['source_repo']==b.REPO and j['project_root']==str(b.ROOT) and j['queue_mode']=='active-lane-v1' and j['resilience']=='bounded-native-recovery-v1','Parent job identity drift')
  current=runtime(j['runner_root'],a['runner_head']);b.need(old_runtime is None or old_runtime==current,'Parent runtime differs between jobs');old_runtime=current
  b.verify_context(b.private_json(d/'context-manifest.json'))
  b.need(v['phase']=='published' and v['delivery_head']==done['delivery_head'] and v['pr']==done['pr'] and 0<v['native_invocations']<=3,'Parent publication missing')
  b.need(r['status']=='PASS' and r['run_id']==j['run_id'] and r['ticket_id']==j['ticket_id'] and r['queue_id']==p.name and r['claim_id']==done['claim_id']==s['lane']['id'],'Parent report drift')
  b.need(check['passed'] is True and check['run_id']==j['run_id'] and check['ticket_id']==j['ticket_id'] and r['check_sha256']==review['check_sha256']==verified['check_sha256']==b.payload_hash(check) and r['context_sha256']==review['context_sha256']==j['context_sha256'],'Parent verification binding drift')
  b.need(review['p0']==review['p1']==0 and review['full_component_gate'] is True and verified['state']=='verified_active' and verified['reservation_released'] is False and verified['owner_accepted'] is False,'Parent independent verification missing')
  b.need(verified['claim_id']==r['claim_id'] and r['native_actor']==done['owner'],'Parent actor/claim binding drift')
  if i==len(s['completed'])-1:b.need(done['owner']==s['lane']['owner'] and done['revision']==s['lane']['revision'],'Parent latest owner/revision drift')
  b.need(r['files']==review['files']==verified['files']==check['files']==done['files'],'Parent output hashes disagree')
  for name,h in done['files'].items():
   b.need(name in b.FILES and b.common.digest(d/'verified-output'/name)==h,'Parent output snapshot drift')
   import hashlib
   b.need(hashlib.sha256(subprocess.check_output(['git','show',done['delivery_head']+':'+name],cwd=b.ROOT)).hexdigest()==h,'Parent Git output drift')
  for g in review['gates']:b.need(g['status']=='PASS' and b.common.digest(g['log'])==g['sha256'],'Parent gate log drift')
  b.need(not any((d/n).exists() for n in ['preseal-intent.json','results/write-intent.json','results/test-intent.json','results/finish.json']),'Parent unresolved operation')
  proofs.append({'run_id':j['run_id'],'job_sha256':b.common.digest(d/'job.json'),'context_sha256':j['context_sha256'],'report_sha256':b.common.digest(d/'results/report.json'),'delivery_head':done['delivery_head']})
 b.need(old_runtime is not None,'No predecessor runtime')
 if 'continuation_contract_sha256' in a:
  old_contract=Path(old_runtime['runner_root'])/'drako_queue_versions/contract.json'
  b.need(b.common.digest(old_contract)==a['continuation_contract_sha256']==b.common.digest(CONTRACT),'Continuation protocol incompatible')
 b.need(b.git(b.ROOT,'rev-parse','HEAD')==s['completed'][-1]['delivery_head'] and b.common.files()==s['completed'][-1]['files'],'Parent source/output changed')
 # Actual actor/liveness is independently checked by q._init immediately before admission.
 receipt={'schema':'drako.runner-transition.v1','parent_queue':str(p),'parent_admission_sha256':b.common.digest(p/'admission.json'),'parent_state_sha256':b.common.digest(p/'state.json'),'from_runtime':old_runtime,'to_runtime':{'runner_root':str(DIST),'runner_head':b.git(DIST,'rev-parse','HEAD')},'contract_sha256':b.common.digest(CONTRACT),'completed_proofs':proofs,'claim_id':s['lane']['id'],'parent_revision':s['lane']['revision'],'historical_jobs_modified':False,'ownership_approvals':0}
 return p,a,s,c,receipt
