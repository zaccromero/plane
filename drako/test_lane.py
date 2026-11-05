import unittest,tempfile
from pathlib import Path
from lane import manifest,verify_context,evaluate,Plane
class LaneTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.p=Path(self.temp.name)/'context.md';self.p.write_text('approved task context');self.context=manifest([str(self.p)])
 def tearDown(self):self.temp.cleanup()
 def test_changed_context_rejected(self):
  self.p.write_text('changed')
  with self.assertRaises(ValueError):verify_context(self.context)
 def test_deleted_context_rejected(self):
  self.p.unlink()
  with self.assertRaises(ValueError):verify_context(self.context)
 def good(self):return dict(context_sha256=self.context['sha256'],ticket_id='ticket',run_id='run',claim_id='claim',authenticated_search=200,anonymous_search=401,relocated=31,absent_retained=7,database_check='ok',known_found=True,known_stale=False,invented_found=False,trace_observed=True)
 def test_positive_and_owner_acceptance_separate(self):
  r=evaluate(self.good(),self.context);self.assertTrue(r['passed']);self.assertEqual(r['owner_acceptance'],'pending')
 def test_each_bad_result_rejected(self):
  for field,value in [('context_sha256','wrong'),('ticket_id',''),('claim_id',''),('anonymous_search',200),('relocated',30),('database_check','bad'),('known_stale',True),('invented_found',True),('trace_observed',False)]:
   with self.subTest(field=field):
    r=self.good();r[field]=value;self.assertFalse(evaluate(r,self.context)['passed'])
 def test_nonlocal_http_refused(self):
  with self.assertRaises(ValueError):Plane('http://example.com','secret','w','p')
if __name__=='__main__':unittest.main()
