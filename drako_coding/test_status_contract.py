"""Immutable independent acceptance tests; the coding worker cannot edit these."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def module():
 spec=importlib.util.spec_from_file_location('status_under_test',ROOT/'drako_status/status.py')
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class StatusContract(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.d=Path(self.temp.name)/'run_case';self.d.mkdir();self.m=module()
 def put(self,name,value):
  p=self.d/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value))
 def valid(self):
  self.put('state.json',{'phase':'published','native_invocations':1,'trace_id':'trace','score_id':'score','comment_id':'comment','api_key':'DO_NOT_ECHO'})
  self.put('evaluation.json',{'run_id':'run_case','checks_passed':True,'trace_observed':True,'score_observed':True})
  self.put('trace-receipt.json',{'trace_observed':True,'trace_id':'trace'})
  self.put('score-receipt.json',{'score_observed':True,'value':True,'trace_id':'trace','score_id':'score'})
  self.put('evidence/evidence-post.json',{'status':'confirmed','comment_id':'comment'})
 def test_missing(self):self.assertEqual(self.m.inspect_run(self.d)['status'],'NOT_RUN')
 def test_prepared(self):
  self.put('state.json',{'phase':'prepared','native_invocations':0});self.assertEqual(self.m.inspect_run(self.d)['status'],'NOT_RUN')
 def test_uncertain(self):
  self.put('state.json',{'phase':'launch_started','native_invocations':1,'pid':1});self.assertEqual(self.m.inspect_run(self.d)['status'],'NEEDS_RECONCILIATION')
 def test_executed(self):
  self.put('state.json',{'phase':'executed','native_invocations':1});self.assertEqual(self.m.inspect_run(self.d)['status'],'EXECUTED_PENDING_PUBLICATION')
 def test_pass_and_private_fields(self):
  self.valid();r=self.m.inspect_run(self.d);self.assertEqual(r['status'],'PASS');self.assertNotIn('DO_NOT_ECHO',json.dumps(r))
  self.assertEqual(set(r),{'run_id','phase','status','native_invocations','checks_passed','trace_observed','score_observed','evidence_confirmed'})
 def test_missing_or_wrong_evidence(self):
  self.valid();(self.d/'score-receipt.json').unlink();self.assertEqual(self.m.inspect_run(self.d)['status'],'INCOMPLETE_EVIDENCE')
  self.put('score-receipt.json',{'score_observed':True,'value':True,'trace_id':'other','score_id':'score'});self.assertEqual(self.m.inspect_run(self.d)['status'],'INCOMPLETE_EVIDENCE')
 def test_malformed(self):
  (self.d/'state.json').write_text('{BAD SECRET');r=self.m.inspect_run(self.d);self.assertEqual(r['status'],'INVALID_EVIDENCE');self.assertNotIn('SECRET',json.dumps(r))
 def test_symlink(self):
  target=Path(self.temp.name)/'outside';target.write_text('{}');(self.d/'state.json').symlink_to(target)
  self.assertEqual(self.m.inspect_run(self.d)['status'],'INVALID_EVIDENCE')
 def test_negative_invocations(self):
  self.put('state.json',{'phase':'executed','native_invocations':-1});self.assertEqual(self.m.inspect_run(self.d)['status'],'INVALID_EVIDENCE')
 def test_unknown_phase(self):
  self.put('state.json',{'phase':'invented','native_invocations':1});self.assertEqual(self.m.inspect_run(self.d)['status'],'INVALID_EVIDENCE')
if __name__=='__main__':unittest.main()
