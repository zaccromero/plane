"""Independent actual-Git regression contract; no provider or private context access."""
import importlib.util,io,json,os,subprocess,tempfile,unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
ROOT=Path(os.environ.get('DRAKO_CODING_ROOT','/Users/zaccromero/code/.worktrees/drako-claude-config/feat/context-pack-session-start'))
s=importlib.util.spec_from_file_location('actual_context',ROOT/'bin/context-for-cwd.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class EmptyContext(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.root=self.base/'code/projects/example';self.root.mkdir(parents=True);self.data=self.base/'ctx';self.data.mkdir();(self.data/'paths.tsv').write_text('projects/example\texample\n');self.pack=self.data/'projects/example';subprocess.run(['git','init','-q',str(self.root)],check=True);subprocess.run(['git','-C',str(self.root),'-c','user.email=test@example.invalid','-c','user.name=Test','commit','--allow-empty','-qm','fixture'],check=True,stdout=subprocess.DEVNULL);self.env={'HOME':str(self.base),'DRAKO_CODE_ROOT':str(self.base/'code'),'DRAKO_CONTEXT_ROOT':str(self.data)}
 def tearDown(self):self.tmp.cleanup()
 def normal(self):
  out=io.StringIO()
  with redirect_stdout(out):code=m.main([str(self.root)],self.env)
  self.assertEqual(code,0);self.assertEqual(out.getvalue(),'')
 def test_missing_pack_normal_quiet(self):self.normal()
 def test_empty_pack_normal_quiet(self):self.pack.mkdir(parents=True);self.normal()
 def test_unrecognized_sections_normal_quiet(self):self.pack.mkdir(parents=True);(self.pack/'notes.md').write_text('not a context section');self.normal()
 def test_empty_pack_hook_quiet(self):
  out=io.StringIO()
  with patch('sys.stdin',io.StringIO(json.dumps({'hook_event_name':'SessionStart','cwd':str(self.root)}))),redirect_stdout(out):code=m.main(['--hook'],self.env)
  self.assertEqual(code,0);self.assertEqual(out.getvalue(),'')
 def test_explicit_receipt_without_pack_stays_available(self):
  out=io.StringIO()
  with redirect_stdout(out):code=m.main(['--receipt',str(self.root)],self.env)
  self.assertEqual(code,0);v=json.loads(out.getvalue());self.assertEqual(v['schema'],'drako.live-context.v1');self.assertEqual(v['project'],'example');self.assertTrue(v['receipt'].startswith('drako-live-v1-'))
 def test_nonempty_pack_receipt_and_compact_hook_preserved(self):
  self.pack.mkdir(parents=True);(self.pack/'BRIEF.md').write_text('actual project context');out=io.StringIO()
  with patch('sys.stdin',io.StringIO(json.dumps({'hook_event_name':'SessionStart','cwd':str(self.root)}))),redirect_stdout(out):code=m.main(['--hook'],self.env)
  self.assertEqual(code,0);text=json.loads(out.getvalue())['hookSpecificOutput']['additionalContext'];self.assertIn('FRESH_CONTEXT=drako-live-v1-',text);self.assertIn('actual project context',text);self.assertLessEqual(len(text),1800)
if __name__=='__main__':unittest.main()
