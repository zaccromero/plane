import json,subprocess,unittest
from pathlib import Path
import adapter as a
class AdapterTests(unittest.TestCase):
 def test_rejects_canonical_or_foreign_project(self):
  for root in [Path.home()/'code/projects/drako-tools',Path('/private/tmp')]:
   with self.assertRaises(RuntimeError):a.validate_project(root)
 def test_real_project_identity(self):
  root=Path('/Users/zaccromero/code/.worktrees/drako-tools/feat/plane-guard-config-validation')
  self.assertEqual(a.validate_project(root),root)
 def test_tap_requires_real_positive_full_success(self):
  output='# tests 2\n# pass 2\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n'
  self.assertTrue(a.tap_pass(output,0))
  for bad in [output.replace('# tests 2','# tests 0'),output.replace('# fail 0','# fail 1'),output.replace('# skipped 0','# skipped 1'),'Ran 2 tests\nOK\n',output+'not ok 1 - failure\n']:
   self.assertFalse(a.tap_pass(bad,0))
  self.assertFalse(a.tap_pass(output,1))
 def test_invalid_tool_parameters_refused(self):
  for name,args in [('read_context',{'path':'/tmp'}),('run_tests',{'command':'sh'}),('write_file',{'path':'../bad','content':'x'})]:
   with self.assertRaises(RuntimeError):a.ProjectWorker('/unused').call(name,args)
 def test_real_node_restrictions(self):
  root=Path('/Users/zaccromero/code/.worktrees/drako-tools/feat/plane-guard-config-validation');scratch=root/'.drako/node-profile-probe';scratch.mkdir(parents=True,exist_ok=True)
  node=str(Path('/Users/zaccromero/.local/bin/node').resolve())
  script="""const fs=require('node:fs'),net=require('node:net'),cp=require('node:child_process');const out={};
for(const [name,fn] of [['read',()=>fs.readFileSync('/Users/zaccromero/.config/drako-plane/token')],['write',()=>fs.writeFileSync('/private/tmp/drako-project-forbidden','x')]]){try{fn();out[name]='ESCAPED';}catch(e){out[name]=['EACCES','EPERM'].includes(e.code)?'DENIED':'UNKNOWN';}}
const child=cp.spawnSync(process.execPath,['-e','console.log(1)']);out.fork=child.error&&['EACCES','EPERM'].includes(child.error.code)?'DENIED':'UNKNOWN';
fs.writeFileSync('allowed','ok');out.scratch=fs.readFileSync('allowed','utf8');
const s=net.connect(8097,'127.0.0.1');s.on('error',e=>{out.network=['EACCES','EPERM'].includes(e.code)?'DENIED':'UNKNOWN';console.log(JSON.stringify(out));});"""
  r=subprocess.run(['/usr/bin/sandbox-exec','-p',a.node_profile(node,root,scratch),node,'-e',script],cwd=scratch,env={'PATH':'/usr/bin:/bin','HOME':str(scratch),'TMPDIR':str(scratch)},capture_output=True,text=True,timeout=10)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout),{'read':'DENIED','write':'DENIED','fork':'DENIED','scratch':'ok','network':'DENIED'})
if __name__=='__main__':unittest.main()
