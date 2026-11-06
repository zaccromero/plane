import importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).with_name('fresh_runner.py');s=importlib.util.spec_from_file_location('runner',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Contracts(unittest.TestCase):
 def test_claude_closed_tools_no_bypass(self):
  c={'session':'/session','python':'/python'};a=m.command(Path('/run'),{'engine':'claude','native_session_id':'id'},c)
  self.assertEqual(a[a.index('--tools')+1],'');self.assertEqual(set(a[a.index('--allowedTools')+1].split(',')),m.TOOLS);self.assertNotIn('--dangerously-skip-permissions',a)
 def test_codex_readonly_and_managed_mcp(self):
  a=m.command(Path('/run'),{'engine':'codex'},{'session':'/session','python':'/python'})
  self.assertEqual(a[:3],['/session','codex','exec']);self.assertEqual(a[a.index('--sandbox')+1],'read-only');self.assertIn('AGENT_TASK_SESSION_CONTEXT',a[a.index('-c')+1]);self.assertNotIn('--approve-for-me',a)
 def test_profile_set_fixed(self):self.assertEqual(set(m.PROFILES),{'drako-tools','drako-map'});self.assertTrue(all('zacc' not in p for p in m.PROFILES))
 def test_no_arbitrary_command_capability(self):
  w=m.Worker('/not-used')
  for name,args in [('shell',{}),('approved_check',{'command':'whoami'}),('result',{'path':'/tmp'})]:
   with self.assertRaisesRegex(RuntimeError,'Fixed parameter-free'):w.call(name,args)
 def test_no_unknown_native_replay(self):
  with self.assertRaisesRegex(RuntimeError,'replay'):m.execute(Path('/run'),{},{},{'phase':'launch_started','native_invocations':1})
 def test_inputs_require_all_admitted_sources(self):
  with tempfile.TemporaryDirectory() as t:
   p={'root':t,'files':['one','two','three']}
   with self.assertRaisesRegex(RuntimeError,'missing'):m.inputs(p)
 def test_inputs_detect_dirty_byte_change(self):
  with tempfile.TemporaryDirectory() as t:
   p={'root':t,'files':['one','two','three']}
   for n in p['files']:(Path(t)/n).write_text(n)
   old=m.inputs(p);(Path(t)/'one').write_text('changed');self.assertNotEqual(old,m.inputs(p))
 def test_source_symlink_denied(self):
  with tempfile.TemporaryDirectory() as t:
   p={'root':t,'files':['one','two','three']}
   for n in ['two','three']:(Path(t)/n).write_text(n)
   (Path(t)/'one').symlink_to(Path(t)/'two')
   with self.assertRaisesRegex(RuntimeError,'Invalid admitted'):m.inputs(p)
 def test_runtime_config_and_executable_drift_changes_binding(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);config=root/'config';config.write_text('one');program=root/'program';program.write_text('program')
   c={x:str(program) for x in ['python','node','session','doctor','claude']}
   old=m.runtime_binding(config,c,'claude');config.write_text('two');self.assertNotEqual(old,m.runtime_binding(config,c,'claude'))
   old=m.runtime_binding(config,c,'claude');program.write_text('changed program');self.assertNotEqual(old,m.runtime_binding(config,c,'claude'))
if __name__=='__main__':unittest.main()
