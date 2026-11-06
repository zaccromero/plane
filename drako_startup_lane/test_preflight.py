import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from preflight import verify,evaluate_handoff
class PreflightTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name).resolve();self.state=self.p/'STARTUP_STATE.md';self.state.write_text('current approved project context')
  rows=[{'path':str(self.state),'sha256':hashlib.sha256(self.state.read_bytes()).hexdigest()}];h=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest();self.v='drako-startup-v1-'+h[:12];s='Project context receipt '+self.v;(self.p/'STARTUP.md').write_text(s)
  self.r={'schema':'drako.project-startup.v1','project':'drako-os','sources':rows,'manifest_sha256':h,'version':self.v,'startup_sha256':hashlib.sha256(s.encode()).hexdigest(),'observed_at':'2026-11-06T00:00:00Z'};self.save()
 def save(self):(self.p/'STARTUP_RECEIPT.json').write_text(json.dumps(self.r))
 def good(self):return verify(self.p,'drako-os',[self.p])
 def test_actual_valid_receipt_produces_explicit_snapshot(self):
  x=self.good();self.assertTrue(x['checks_passed']);self.assertFalse(x['continuous_freshness']);self.assertEqual(x['startup_version'],self.v)
 def test_changed_current_state_holds(self):
  self.state.write_text('changed')
  with self.assertRaises(ValueError):self.good()
 def test_missing_source_holds(self):
  self.state.unlink()
  with self.assertRaises(ValueError):self.good()
 def test_changed_startup_holds(self):
  (self.p/'STARTUP.md').write_text('foreign')
  with self.assertRaises(ValueError):self.good()
 def test_wrong_project_holds(self):
  with self.assertRaises(ValueError):verify(self.p,'milo',[self.p])
 def test_rewritten_manifest_without_rehash_holds(self):
  self.r['sources'][0]['sha256']='0'*64;self.save()
  with self.assertRaises(ValueError):self.good()
 def test_forged_version_holds(self):
  self.r['version']='invented';self.save()
  with self.assertRaises(ValueError):self.good()
 def test_external_source_holds_even_if_rehashed(self):
  f=self.p.parent/(self.p.name+'-private');f.write_text('private');self.addCleanup(f.unlink)
  self.r['sources']=[{'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}];self.r['manifest_sha256']=hashlib.sha256(json.dumps(self.r['sources'],sort_keys=True).encode()).hexdigest();self.r['version']='drako-startup-v1-'+self.r['manifest_sha256'][:12];self.save()
  with self.assertRaises(ValueError):self.good()
 def test_symlink_source_holds(self):
  real=self.p/'real.md';self.state.rename(real);self.state.symlink_to(real)
  with self.assertRaises(ValueError):self.good()
 def test_truncated_hook_cannot_pass(self):
  s='x'*1800+self.v;(self.p/'STARTUP.md').write_text(s);self.r['startup_sha256']=hashlib.sha256(s.encode()).hexdigest();self.save()
  with self.assertRaises(ValueError):self.good()
class BindingTests(unittest.TestCase):
 def setUp(self):
  self.j={'project':'drako-os','ticket_id':'ticket','run_id':'run','context_sha256':'context','startup_version':'loaded'}
  self.h={**self.j,'claim_id':'native','loaded_startup_version':'loaded','checks_passed':True,'continuous_freshness':False}
  self.c={k:self.j[k] for k in ['ticket_id','run_id','context_sha256','startup_version']};self.c.update(claim_id='native',checks_passed=True,status='PASS');self.rehash()
 def rehash(self):self.c['handoff_sha256']=hashlib.sha256(json.dumps(self.h,sort_keys=True).encode()).hexdigest()
 def test_valid_bound_handoff(self):self.assertEqual(evaluate_handoff(self.h,self.j,self.c)['status'],'PASS')
 def test_other_ticket_or_run_or_context_holds(self):
  for key in ['ticket_id','run_id','context_sha256','startup_version']:
   bad={**self.c,key:'wrong'}
   with self.assertRaises(ValueError):evaluate_handoff(self.h,self.j,bad)
 def test_wrong_loaded_receipt_even_with_hash_holds(self):
  self.h['loaded_startup_version']='invented';self.rehash()
  with self.assertRaises(ValueError):evaluate_handoff(self.h,self.j,self.c)
 def test_false_check_cannot_be_pass(self):
  self.c['checks_passed']=False
  with self.assertRaises(ValueError):evaluate_handoff(self.h,self.j,self.c)
 def test_scope_or_live_freshness_forgery_holds(self):
  for key,val in [('project','milo'),('continuous_freshness',True),('claim_id','other')]:
   h={**self.h,key:val};c={**self.c,'handoff_sha256':hashlib.sha256(json.dumps(h,sort_keys=True).encode()).hexdigest()}
   with self.assertRaises(ValueError):evaluate_handoff(h,self.j,c)
if __name__=='__main__':unittest.main()
