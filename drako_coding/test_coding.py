import json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import coding_common as c
from coding_tool_server import Worker,SCHEMAS
class CodingTests(unittest.TestCase):
 def test_tool_scope(self):
  self.assertEqual(len(SCHEMAS),5)
  for path in ['../outside','/tmp/foo','drako_coding/runner.py']:
   with self.assertRaises(RuntimeError):Worker('/unused').call('write_file',{'path':path,'content':'x'})
  with self.assertRaises(RuntimeError):Worker('/unused').call('run_tests',{'command':'anything'})
 def test_size_bound(self):
  with self.assertRaises(RuntimeError):Worker('/unused').call('write_file',{'path':c.FILES[0],'content':'x'*32001})
 def test_drift_and_symlink(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'drako_status').symlink_to('/private/tmp')
   with patch.object(c,'ROOT',root):
    with self.assertRaises(RuntimeError):c.files()
 def test_real_os_restrictions(self):
  scratch=c.ROOT/'.drako/profile-probe';scratch.mkdir(parents=True,exist_ok=True)
  script="""import os,socket,pathlib,json
out={}
for name,action in [('read',lambda:pathlib.Path('/Users/zaccromero/.config/drako-plane/token').read_text()),('write',lambda:pathlib.Path('/private/tmp/drako-forbidden-write').write_text('x')),('network',lambda:socket.create_connection(('127.0.0.1',8097),1))]:
 try:action();out[name]='ESCAPED'
 except PermissionError:out[name]='DENIED'
 except OSError as e:out[name]='DENIED' if e.errno in (1,13) else 'UNKNOWN'
pathlib.Path('allowed').write_text('ok')
out['scratch_write']=pathlib.Path('allowed').read_text()
print(json.dumps(out))"""
  py='/opt/homebrew/bin/python3';p=subprocess.run(['/usr/bin/sandbox-exec','-p',c.profile(py,scratch),str(c.python_engine(py)),'-I','-B','-c',script],cwd=scratch,env={'PATH':'/usr/bin:/bin','HOME':str(scratch),'TMPDIR':str(scratch)},capture_output=True,text=True,timeout=10)
  self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout),{'read':'DENIED','write':'DENIED','network':'DENIED','scratch_write':'ok'})
if __name__=='__main__':unittest.main()
