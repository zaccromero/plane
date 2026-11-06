import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import entry
import recovery as r
b=entry.base
class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.root=Path(tempfile.mkdtemp(prefix='preseal-unit-'));self.d=self.root/'run';self.d.mkdir();(self.d/'results').mkdir();self.j={'context_sha256':'ctx','runner_head':'runner'};self.hashes={'source':'a','test':'b'};self.check={'files':self.hashes,'passed':True}
  self.owner={'client':'claude','profile':'default','session':'native','executor':{'pid':1}}
  self.claim={'id':'claim','state':'active','owner':self.owner};self.seals=0
  self.worker={'claim_id':'claim','actor':self.owner,'writes':2,'tests':1}
  b.atomic(self.d/'results/worker-state.json',self.worker);b.atomic(self.d/'baseline-files.json',{'test':{'content':'original'}})
  self.patches=[patch.object(b,'ROOT',self.root),patch.object(b,'load_job',return_value=(self.d,self.j,{})),patch.object(b.common,'checked',side_effect=lambda *_:self.check),patch.object(b.common,'files',side_effect=lambda:self.hashes),patch.object(b,'native_request',side_effect=lambda req:self.claim),patch.object(b.ProjectWorker,'call',self.parent)]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
 def parent(self,name,args):
  if name=='result':self.seals+=1;return {'status':'PASS'}
  return {}
 def good(self,*args):return {'p0':0,'p1':0,'full_component_gate':True,'files':self.hashes,'check_sha256':b.payload_hash(self.check),'context_sha256':'ctx'}
 def test_real_validation_failure_keeps_active_claim_and_does_not_seal(self):
  with patch.object(r,'map_verify',side_effect=RuntimeError('Automatic verification failed: source-policy')):
   value=r.RecoveryWorker(self.d).call('result',{})
  self.assertEqual(value['status'],'REPAIR_REQUIRED');self.assertEqual(self.seals,0);self.assertEqual(self.claim['state'],'active')
  self.assertEqual(b.private_json(self.d/'results/worker-state.json'),self.worker);self.assertFalse((self.d/'preseal-intent.json').exists())
 def test_failure_then_changed_repair_pass_seals_once_same_claim(self):
  with patch.object(r,'map_verify',side_effect=RuntimeError('Output scope mismatch')):r.RecoveryWorker(self.d).call('result',{})
  self.hashes={'source':'repaired','test':'b'};self.check={'files':self.hashes,'passed':True}
  with patch.object(r,'map_verify',side_effect=self.good):v=r.RecoveryWorker(self.d).call('result',{})
  self.assertEqual(v['status'],'PASS');self.assertEqual(self.seals,1)
  h=b.private_json(self.d/'preseal-history.json');self.assertEqual([x['status'] for x in h],['FAIL','PASS']);self.assertEqual(len({x['claim_id'] for x in h}),1)
 def test_unchanged_rejection_is_not_reexecuted(self):
  with patch.object(r,'map_verify',side_effect=RuntimeError('Output scope mismatch')) as verify:
   for _ in range(2):r.RecoveryWorker(self.d).call('result',{})
   self.assertEqual(verify.call_count,1);self.assertEqual(len(b.private_json(self.d/'preseal-history.json')),1)
 def test_three_attempt_cap_and_no_budget_reset(self):
  with patch.object(r,'map_verify',side_effect=RuntimeError('Output scope mismatch')) as verify:
   for i in range(3):
    self.hashes={'source':str(i),'test':'b'};self.check={'files':self.hashes,'passed':True};r.RecoveryWorker(self.d).call('result',{})
   self.hashes={'source':'fourth','test':'b'};self.check={'files':self.hashes,'passed':True}
   with self.assertRaisesRegex(RuntimeError,'budget exhausted'):r.RecoveryWorker(self.d).call('result',{})
   self.assertEqual(verify.call_count,3);self.assertEqual(self.seals,0)
 def test_unknown_failure_retains_uncertain_intent_and_blocks_replay(self):
  with patch.object(r,'map_verify',side_effect=RuntimeError('runtime changed')) as verify:
   with self.assertRaisesRegex(RuntimeError,'runtime changed'):r.RecoveryWorker(self.d).call('result',{})
   with self.assertRaisesRegex(RuntimeError,'Uncertain independent'):r.RecoveryWorker(self.d).call('result',{})
   self.assertEqual(verify.call_count,1);self.assertEqual(self.seals,0)
 def test_foreign_terminal_claim_and_result_arguments_denied(self):
  for state in ['owner_review','finish_pending']:
   self.claim['state']=state
   with self.assertRaisesRegex(RuntimeError,'active native'):r.RecoveryWorker(self.d).call('result',{})
  self.claim['state']='active';self.claim['owner']={'different':True}
  with self.assertRaisesRegex(RuntimeError,'active native'):r.RecoveryWorker(self.d).call('result',{})
  with self.assertRaises(RuntimeError):r.RecoveryWorker(self.d).call('result',{'approve':True})
 def test_qualification_root_rejects_foreign_and_canonical(self):
  for p in ['/private/tmp',str(Path.home()/'code/projects/plane'),str(Path.home()/'code/.worktrees/drako-map/feat/plane-elevation-no-coercion')]:
   with self.assertRaises(RuntimeError):entry.qualification_root(p)
 def test_bad_verifier_binding_never_seals(self):
  def bad(*args):return {**self.good(),'files':{'source':'different'}}
  with patch.object(r,'map_verify',side_effect=bad):
   with self.assertRaisesRegex(RuntimeError,'binding mismatch'):r.RecoveryWorker(self.d).call('result',{})
  self.assertEqual(self.seals,0)
