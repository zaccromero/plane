import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import entry as q
import worker as w
b=q.b
class QueueTests(unittest.TestCase):
 def setUp(self):
  self.root=Path(tempfile.mkdtemp(prefix='queue-unit-'));self.d=self.root/'run';self.d.mkdir();(self.d/'results').mkdir()
  self.files={'source':'a','test':'b'};self.actor={'client':'claude','profile':'default','session':'lane','executor':{'pid':2}};self.scopes=['source','test','run/results'];self.claim={'id':'claim','state':'active','owner':self.actor,'scopes':self.scopes,'worktree':str(self.root),'revision':1}
  self.j={'queue_mode':'active-lane-v1','queue_id':'queue','queue_expected_scopes':self.scopes,'run_id':'run','ticket_id':'ticket','context_sha256':'context'};self.c={'session':'/session','binding':'/private-binding'};self.check={'passed':True,'files':self.files}
  b.atomic(self.d/'results/worker-state.json',{'claim_id':'claim','actor':self.actor,'files':self.files,'writes':2,'tests':1,'read':True})
  self.review={'p0':0,'p1':0,'full_component_gate':True,'files':self.files,'check_sha256':b.payload_hash(self.check),'context_sha256':'context'};b.atomic(self.d/'review.json',self.review)
  self.actions=[]
  def native(req):self.actions.append(req);return self.claim
  self.patches=[patch.object(b,'ROOT',self.root),patch.object(b,'load_job',return_value=(self.d,self.j,self.c)),patch.object(b.common,'files',return_value=self.files),patch.object(b.common,'checked',return_value=self.check),patch.object(b,'native_request',side_effect=native),patch.object(w,'ORIGINAL_CALL',return_value={})]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
 def test_verified_ticket_retains_active_claim_without_finish_or_accept(self):
  result=w.active_result(w.QueueWorker(self.d),'result',{})
  self.assertEqual(result['controller_state'],'active');self.assertFalse((self.d/'results/finish.json').exists());self.assertEqual(b.private_json(self.d/'results/queue-verified.json')['state'],'verified_active')
  self.assertTrue(all(x['action']=='show' for x in self.actions))
 def test_invalid_review_cannot_complete_ticket(self):
  for key,value in [('files',{'source':'wrong'}),('context_sha256','other'),('full_component_gate',False)]:
   b.atomic(self.d/'review.json',{**self.review,key:value})
   with self.assertRaisesRegex(RuntimeError,'Independent verification'):w.active_result(w.QueueWorker(self.d),'result',{})
  self.assertFalse((self.d/'results/report.json').exists())
 def test_terminal_or_foreign_owner_cannot_publish_verified_active(self):
  for state in ['finish_pending','owner_review','owner_accepted']:
   self.claim['state']=state
   with self.assertRaisesRegex(RuntimeError,'owner/scope'):w.active_result(w.QueueWorker(self.d),'result',{})
  self.claim['state']='active';self.claim['owner']={'foreign':True}
  with self.assertRaisesRegex(RuntimeError,'owner/scope'):w.active_result(w.QueueWorker(self.d),'result',{})
 def resumed_setup(self):
  (self.d/'results/worker-state.json').unlink();self.j.update(resume_claim='claim',resume_revision=1,queue_previous_owner={**self.actor,'executor':{'pid':1}},queue_previous_scopes=['source','test','old/results'],initial_files=self.files);self.claim.update(revision=2,scopes=['source','test','old/results']);self.j['queue_expected_scopes']=self.claim['scopes']+[str((self.d/'results').relative_to(self.root))]
 def test_next_ticket_extends_only_receipt_scope_after_supported_resume(self):
  self.resumed_setup()
  def request(req):
   self.actions.append(req)
   if req['action']=='extend_scopes':self.claim['scopes']=self.j['queue_expected_scopes'];self.claim['revision']+=1
   return self.claim
  with patch.object(b,'native_request',side_effect=request),patch.object(w.subprocess,'check_output',return_value=json.dumps({'project':str(self.root),'actor':self.actor})),patch.object(w.RecoveryWorker,'call',return_value={}),patch.object(b,'load_binding') as binding:
   binding.return_value.comments.return_value=[{'comment_html':'drako-claim:claim'}]
   w.QueueWorker(self.d).call('ticket_read',{})
  extend=next(x for x in self.actions if x['action']=='extend_scopes');self.assertEqual(extend['scopes'],['run/results']);self.assertFalse(any(x['action'] in ['claim','finish','owner_accept'] for x in self.actions));self.assertEqual(b.private_json(self.d/'results/worker-state.json')['actor'],self.actor)
 def test_resume_requires_same_logical_owner_and_exact_revision(self):
  self.resumed_setup();self.j['queue_previous_owner']['session']='foreign'
  with patch.object(w.subprocess,'check_output',return_value=json.dumps({'project':str(self.root),'actor':self.actor})):
   with self.assertRaisesRegex(RuntimeError,'supported resume'):w.QueueWorker(self.d).call('ticket_read',{})
  self.assertFalse(any(x['action']=='extend_scopes' for x in self.actions))
 def test_results_cannot_be_mutated_after_ticket_completion(self):
  w.active_result(w.QueueWorker(self.d),'result',{})
  with self.assertRaisesRegex(RuntimeError,'cannot be mutated'):w.QueueWorker(self.d).call('write_file',{'path':'source','content':'bad'})
 def test_admission_is_bounded_and_branches_are_isolated(self):
  for tickets,branches in [([],[]),(['same','same'],['feat/a','feat/b']),(['a','b','c'],['feat/a','feat/b','feat/c'])]:
   with self.assertRaises(RuntimeError):q.init('/config',tickets,branches)
  with self.assertRaises(RuntimeError):q.branch_name('main')

 def test_next_dispatch_requires_positive_writer_exit_and_active_claim(self):
  import sys
  sys.path.insert(0,'/Users/zaccromero/.drako/hermes/current/source')
  from hermes_cli import agent_tasks
  config={'hermes_source':'/Users/zaccromero/.drako/hermes/current/source','board_db':'/unused'}
  with patch.object(agent_tasks,'ControllerSupervisor') as supervisor,patch.object(agent_tasks,'group_dead',return_value=True) as dead:
   supervisor.return_value.__enter__.return_value.request.return_value={'result':{'task':self.claim}}
   self.assertEqual(q.owner(config,'claim')['id'],'claim')
   dead.return_value=False
   with self.assertRaisesRegex(RuntimeError,'exited writer'):q.owner(config,'claim')
   dead.return_value=True;self.claim['state']='owner_review'
   with self.assertRaisesRegex(RuntimeError,'exited writer'):q.owner(config,'claim')
