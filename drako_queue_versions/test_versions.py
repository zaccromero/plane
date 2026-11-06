import contextlib,io,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
DIST=Path(__file__).resolve().parents[1];sys.path[:0]=[str(Path(__file__).parent)]
import entry as v
b=v.b;compat=v.compat
class GitCompatibility(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.home=Path(self.tmp.name).resolve();repo=self.home/'code/projects/plane';repo.mkdir(parents=True);self.repo=repo
  def git(*a):return subprocess.check_output(['git','-C',str(repo),*a],stderr=subprocess.DEVNULL,text=True).strip()
  self.git=git;git('init');git('config','user.email','test@example.test');git('config','user.name','test')
  for folder in compat.CORE:(repo/folder).mkdir();(repo/folder/'source.py').write_text('trusted=True\n')
  git('add','.');git('commit','-m','compatible baseline');self.oldhead=git('rev-parse','HEAD')
  (repo/'wrapper.txt').write_text('new admission version');git('add','.');git('commit','-m','new wrapper');self.head=git('rev-parse','HEAD')
  self.old=self.home/'code/.worktrees/plane/old';self.new=self.home/'code/.worktrees/plane/new';self.old.parent.mkdir(parents=True)
  git('worktree','add','--detach',str(self.old),self.oldhead);git('worktree','add','--detach',str(self.new),self.head)
  self.patches=[patch.object(Path,'home',return_value=self.home),patch.object(compat,'DIST',self.new)]
  for p in self.patches:p.start();self.addCleanup(p.stop)
 def test_different_heads_with_identical_protected_interfaces_pass(self):
  result=compat.runtime(self.old,self.oldhead);self.assertEqual(result['runner_head'],self.oldhead);self.assertNotEqual(self.oldhead,self.head)
 def test_wrong_runtime_head_holds(self):
  with self.assertRaises(RuntimeError):compat.runtime(self.old,self.head)
 def test_dirty_runtime_holds(self):
  (self.old/compat.CORE[0]/'source.py').write_text('changed')
  with self.assertRaises(RuntimeError):compat.runtime(self.old,self.oldhead)
 def test_untracked_executable_in_protected_folder_holds(self):
  (self.old/compat.CORE[0]/'foreign.py').write_text('changed')
  with self.assertRaises(RuntimeError):compat.runtime(self.old,self.oldhead)
 def test_protected_interface_change_holds(self):
  self.git('worktree','remove',str(self.new));(self.repo/compat.CORE[0]/'source.py').write_text('changed');self.git('add','.');self.git('commit','-m','interface changed');self.git('worktree','add','--detach',str(self.new),'HEAD')
  with self.assertRaises(RuntimeError):compat.runtime(self.old,self.oldhead)
 def test_foreign_location_holds(self):
  with self.assertRaises(RuntimeError):compat.runtime(self.repo,self.head)
class AdmissionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.parent=self.root/'.drako/queues/queue_parent';self.parent.mkdir(parents=True);self.config=self.root/'config.json';self.config.write_text('{}')
  self.lane={'id':'t_existing','owner':{'client':'claude'},'revision':11,'scopes':list(b.FILES)}
  self.state={'phase':'idle_active','index':1,'jobs':['prior'],'completed':[{'delivery_head':'oldhead'}],'lane':self.lane,'native_session_id':'same-native-session'}
  self.proof={'parent_queue':str(self.parent),'from_runtime':{'runner_head':'old'},'to_runtime':{'runner_head':'new'}}
  self.patches=[patch.object(b,'ROOT',self.root),patch.object(b,'config',return_value={'binding':'test-binding'}),patch.object(compat,'previous',return_value=(self.parent,{},self.state,{'binding':'test-binding'},self.proof)),patch.object(v.q,'owner',return_value=self.lane),patch.object(b,'git',side_effect=lambda root,*args:'newhead' if args[:1]==('rev-parse',) else ''),patch.object(b,'load_binding')]
  for p in self.patches:p.start();self.addCleanup(p.stop)
  b.load_binding.return_value.get.side_effect=lambda x:{'id':x,'name':'ticket','description_html':'bounded','project':'project-test'}
 def init(self,tickets=None):
  out=io.StringIO()
  with contextlib.redirect_stdout(out):v.init(self.config,tickets or ['ticket-1'],['feat/next'],self.parent,True)
  return json.loads(out.getvalue())
 def test_new_admission_pins_new_version_preserves_claim_and_parent(self):
  result=self.init();child=Path(result['queue_dir']);s=b.private_json(child/'state.json');a=b.private_json(child/'admission.json')
  self.assertEqual(s['lane'],self.lane);self.assertEqual(s['native_session_id'],'same-native-session');self.assertEqual(a['runner_head'],'newhead');self.assertEqual(s['jobs'],[])
  self.assertFalse((self.parent/'admission.json').exists())
 def test_repeat_init_reuses_exact_successor(self):
  one=self.init();two=self.init();self.assertEqual(one['queue_dir'],two['queue_dir']);self.assertTrue(two['admission_reused']);self.assertEqual(len(list(self.parent.parent.glob('queue_*'))),2)
 def test_other_ticket_cannot_replace_successor(self):
  self.init()
  with self.assertRaises(RuntimeError):self.init(['ticket-other'])
 def test_owner_or_revision_changed_holds_before_new_queue(self):
  changed={**self.lane,'revision':12}
  with patch.object(v.q,'owner',return_value=changed):
   with self.assertRaises(RuntimeError):self.init()
  self.assertFalse((self.parent/'successor.json').exists())
 def test_incomplete_or_changed_parent_does_not_mutate(self):
  with patch.object(compat,'previous',side_effect=RuntimeError('incomplete')):
   with self.assertRaises(RuntimeError):self.init()
  self.assertFalse((self.parent/'version-transition-intent.json').exists())
 def test_known_partial_admission_resumes_without_duplicate(self):
  original=b.atomic;triggered=False
  def crash(path,value):
   nonlocal triggered
   original(path,value)
   if path.name=='admission.json' and not triggered:triggered=True;raise OSError('realistic transport interruption after admission write')
  with patch.object(b,'atomic',side_effect=crash):
   with self.assertRaises(OSError):self.init()
  result=self.init();self.assertEqual(result['queue_dir'],b.private_json(self.parent/'version-transition-intent.json')['queue_dir']);self.assertEqual(len(list(self.parent.parent.glob('queue_*'))),2)
 def test_corrupt_partial_admission_holds(self):
  one=self.init();child=Path(one['queue_dir']);(self.parent/'successor.json').unlink();a=b.private_json(child/'admission.json');a['runner_head']='foreign';b.atomic(child/'admission.json',a)
  with self.assertRaises(RuntimeError):self.init()
 def test_bounds_no_empty_or_duplicate_admission(self):
  for tickets,branches in [([],[]),(['x','x'],['feat/a','feat/b']),(['x','y','z'],['feat/a','feat/b','feat/c'])]:
   with self.assertRaises(RuntimeError):v.request_key(self.config,tickets,branches,False)
if __name__=='__main__':unittest.main()
