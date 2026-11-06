import unittest
from publisher import review_gate,payload_hash
class ReviewGate(unittest.TestCase):
 def setUp(self):
  self.files={'one':'a','two':'b'};self.check={'status':'PASS','files':self.files};self.report={'files':self.files,'check_sha256':payload_hash(self.check)};self.review={'p0':0,'p1':0,'release_gate_passed':True,'files':self.files,'check_sha256':payload_hash(self.check)}
 def test_exact_review_and_check_pass(self):review_gate(self.review,self.check,self.report,self.files)
 def test_failed_or_missing_gate_refused(self):
  for field,value in [('p1',1),('release_gate_passed',False)]:
   with self.assertRaises(RuntimeError):review_gate({**self.review,field:value},self.check,self.report,self.files)
 def test_stale_source_or_check_refused(self):
  with self.assertRaises(RuntimeError):review_gate(self.review,self.check,self.report,{'one':'changed'})
  with self.assertRaises(RuntimeError):review_gate({**self.review,'check_sha256':'changed'},self.check,self.report,self.files)
if __name__=='__main__':unittest.main()
