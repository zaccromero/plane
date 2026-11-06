"""Per-ticket verification and receipts inside one continuously active native lane."""
import json,subprocess
from pathlib import Path
import adapter as b
from recovery import RecoveryWorker
ORIGINAL_CALL=b.service.Worker.call

def active_result(self,name,args):
 if name!='result':return ORIGINAL_CALL(self,name,args)
 b.need(args=={},'No result parameters')
 # Existing worker performs ticket/actor/output validation before its result path.
 ORIGINAL_CALL(self,'ticket_read',{})
 d,j,c=b.load_job(self.directory);b.need(j.get('queue_mode')=='active-lane-v1','Not a queue job')
 state=b.private_json(d/'results/worker-state.json');check=b.common.checked(d,j);review=b.private_json(d/'review.json');t=b.native_request({'action':'show','id':state['claim_id']})
 b.need(t['state']=='active' and t['owner']==state['actor'] and b.common.exact_scopes(t['scopes'],j['queue_expected_scopes']),'Queue owner/scope mismatch')
 b.need(review['p0']==0 and review['p1']==0 and review['full_component_gate'] is True and review['files']==b.common.files() and review['check_sha256']==b.payload_hash(check) and review['context_sha256']==j['context_sha256'],'Independent verification required')
 report={'status':'PASS','run_id':j['run_id'],'ticket_id':j['ticket_id'],'claim_id':t['id'],'native_actor':t['owner'],'context_sha256':j['context_sha256'],'check_sha256':b.payload_hash(check),'files':b.common.files(),'queue_id':j['queue_id'],'controller_state':'active'}
 b.atomic(d/'results/report.json',report);b.atomic(d/'results/queue-verified.json',{'state':'verified_active','claim_id':t['id'],'files':b.common.files(),'check_sha256':b.payload_hash(check),'reservation_released':False,'owner_accepted':False})
 return report

class QueueWorker(RecoveryWorker):
 def call(self,name,args):
  d,j,c=b.load_job(self.directory);b.need(j.get('queue_mode')=='active-lane-v1','Legacy job cannot join queue')
  report=d/'results/report.json'
  if report.exists():
   b.need(name in ['ticket_read','result'] and args=={},'Verified ticket cannot be mutated')
   value=b.private_json(report);t=b.native_request({'action':'show','id':value['claim_id']})
   context=json.loads(subprocess.check_output([c['session'],'context'],text=True))
   b.need(t['state']=='active' and t['owner']==value['native_actor']==context['actor'] and context['project']==str(b.ROOT) and value['files']==b.common.files(),'Verified ticket owner/output drift')
   return value
  if name=='ticket_read' and j.get('resume_claim') and not (d/'results/worker-state.json').exists():
   b.need(args=={},'No claim parameters')
   context=json.loads(subprocess.check_output([c['session'],'context'],text=True));t=b.native_request({'action':'show','id':j['resume_claim']})
   b.need(context['project']==str(b.ROOT) and t['worktree']==str(b.ROOT) and t['state']=='active' and t['owner']==context['actor'],'Wrong resumed queue owner')
   b.need(all(t['owner'][k]==j['queue_previous_owner'][k] for k in ['client','profile','session']) and t['revision']==j['resume_revision']+1,'Missing exact supported resume')
   b.need(b.common.exact_scopes(t['scopes'],j['queue_previous_scopes']),'Unexpected prior reservation')
   b.need(b.common.files()==j['initial_files'],'Next-ticket baseline changed')
   additional=str((d/'results').relative_to(b.ROOT))
   t=b.native_request({'action':'extend_scopes','id':t['id'],'revision':t['revision'],'scopes':[additional],'legacy_reconciled':True})
   b.need(b.common.exact_scopes(t['scopes'],j['queue_expected_scopes']),'Unexpected extended scope')
   b.atomic(d/'results/worker-state.json',{'claim_id':t['id'],'actor':t['owner'],'files':b.common.files(),'writes':0,'tests':0,'read':False})
   b.atomic(d/'results/queue-resume.json',{'claim_id':t['id'],'actor':t['owner'],'revision':t['revision'],'scopes':t['scopes'],'supported_resume':True})
   client=b.load_binding(c['binding']);marker='drako-claim:'+t['id']
   if not any(marker in x.get('comment_html','') for x in client.comments(j['ticket_id'])):
    intent=d/'results/queue-comment-intent.json';b.need(not intent.exists(),'Uncertain queue claim comment; reconcile');b.atomic(intent,{'marker':marker})
    client.comment(j['ticket_id'],'<p>Continued active lane ownership: '+marker+'. Same logical owner resumed after previous writer exit; no owner acceptance or reservation release.</p>')
    b.need(any(marker in x.get('comment_html','') for x in client.comments(j['ticket_id'])),'Queue claim comment unconfirmed')
  value=super().call(name,args)
  if name=='read_context':value['queue_lifecycle']='This ticket is within a bounded admitted queue. PASS records verified ticket delivery while retaining the active lane claim. Stop this invocation after PASS. The host alone publishes and advances to the next admitted ticket after writer exit. No merges, ownership approvals, claim release or extra task selection.'
  return value
