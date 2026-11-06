import json,os,subprocess,tempfile,unittest
from pathlib import Path
import adapter as a
from verifier import host_profile
ROOT=Path.home()/'code/.worktrees/drako-map/feat/plane-elevation-finite'
NODE=str(Path.home()/'.hermes/node/bin/node')
class ProfileTests(unittest.TestCase):
 def test_identity_and_fixed_scope(self):
  self.assertEqual(a.validate_project(ROOT),ROOT)
  self.assertEqual(a.FILES,('packages/elevation/src/profile.ts','packages/elevation/test/profile.test.ts'))
  for p in [Path.home()/'code/projects/drako-map',Path.home()/'code/.worktrees/drako-tools/feat/plane-set-config-qualification',Path('/private/tmp')]:
   with self.assertRaises(RuntimeError):a.validate_project(p)
 def test_arbitrary_tool_arguments_denied(self):
  for n,v in [('read_context',{'path':'/tmp'}),('run_tests',{'command':'sh'}),('write_file',{'path':'package.json','content':'{}'})]:
   with self.assertRaises(RuntimeError):a.ProjectWorker('/unused').call(n,v)
 def test_tap_cannot_fake_success(self):
  good='# tests 1\n# pass 1\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n'
  self.assertTrue(a.tap_pass(good,0))
  for x in ['',good.replace('# tests 1','# tests 0'),good.replace('# skipped 0','# skipped 1'),good+'not ok 1\n'] :self.assertFalse(a.tap_pass(x,0))
  self.assertFalse(a.tap_pass(good,1))
 def test_worker_real_denials(self):
  scratch=Path(tempfile.mkdtemp(prefix='map-profile-probe-')).resolve()
  script="""const fs=require('node:fs'),cp=require('node:child_process'),net=require('node:net');let o={};for(const [n,f] of [['private',()=>fs.readFileSync('/Users/zaccromero/.config/drako-plane/token')],['outside',()=>fs.writeFileSync('/private/tmp/map-escape','x')]]){try{f();o[n]='ESCAPED'}catch(e){o[n]=['EPERM','EACCES'].includes(e.code)?'DENIED':'UNKNOWN'}};let p=cp.spawnSync(process.execPath,['-e','']);o.fork=p.error&&['EPERM','EACCES'].includes(p.error.code)?'DENIED':'UNKNOWN';fs.writeFileSync('allowed','ok');o.scratch=fs.readFileSync('allowed','utf8');net.connect(8097,'127.0.0.1').on('error',e=>{o.network=['EPERM','EACCES'].includes(e.code)?'DENIED':'UNKNOWN';console.log(JSON.stringify(o))});"""
  r=subprocess.run(['/usr/bin/sandbox-exec','-p',a.node_profile(NODE,ROOT,scratch),NODE,'-e',script],cwd=scratch,env={'PATH':'/usr/bin:/bin','HOME':str(scratch),'TMPDIR':str(scratch)},capture_output=True,text=True,timeout=10)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout),{'private':'DENIED','outside':'DENIED','fork':'DENIED','scratch':'ok','network':'DENIED'})
 def test_verifier_denies_private_network_and_source_writes(self):
  scratch=Path(tempfile.mkdtemp(prefix='map-host-probe-')).resolve();snap=scratch/'snapshot';snap.mkdir();(snap/'source').write_text('original');work=scratch/'allowed';work.mkdir()
  script="""const fs=require('node:fs'),net=require('node:net');let o={};for(const [n,p] of [['private','/Users/zaccromero/.config/drako-plane/token'],['source','./source'],['outside','/private/tmp/map-host-escape']]){try{n==='private'?fs.readFileSync(p):fs.writeFileSync(p,'x');o[n]='ESCAPED'}catch(e){o[n]=['EACCES','EPERM'].includes(e.code)?'DENIED':'UNKNOWN'}}net.connect(8097,'127.0.0.1').on('error',e=>{o.network=['EPERM','EACCES'].includes(e.code)?'DENIED':'UNKNOWN';console.log(JSON.stringify(o))});"""
  r=subprocess.run(['/usr/bin/sandbox-exec','-p',host_profile(snap,work,NODE),NODE,'-e',script],cwd=snap,env={'PATH':'/usr/bin:/bin','HOME':str(work),'TMPDIR':str(work)},capture_output=True,text=True,timeout=10)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout),{'private':'DENIED','source':'DENIED','outside':'DENIED','network':'DENIED'})
 def test_source_policy_rejects_worker_runtime_access(self):
  scratch=Path(tempfile.mkdtemp(prefix='map-static-probe-'));p=scratch/'profile.ts'
  for source in ['export function summariseProfile(x:number[]){process.exit(0)}','export function summariseProfile(x:number[]){return eval("1")}','import fs from "node:fs";export function summariseProfile(x:number[]){return x}']:
   p.write_text(source);r=subprocess.run([NODE,str(Path(__file__).with_name('source-policy.mjs')),str(p),str(ROOT/'node_modules/typescript/lib/typescript.js')],capture_output=True);self.assertNotEqual(r.returncode,0)
