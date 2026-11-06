import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
DIST=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(DIST/'drako_profiles'),str(DIST/'drako_recovery'),str(DIST/'drako_queue')]
import adapter as b
import supervisor as s
class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.d=Path(self.temp.name);self.j={'run_id':'run_test','max_assistant_messages':16,'max_tool_calls':16};self.state={'native_invocations':1}
 def log(self,calls=None,extra=None,exit=-15,inventory=None,i=1):
  p=self.d/'native-attempts'/str(i);p.mkdir(parents=True)
  values=[{'type':'system','subtype':'init','tools':sorted(b.common.TOOLS) if inventory is None else inventory},{'type':'assistant','message':{'content':[{'type':'tool_use','name':x} for x in (calls or [])]}}]
  if extra:values.append(extra)
  (p/'stdout.jsonl').write_text('\n'.join(json.dumps(x) for x in values));b.atomic(p/'wait.json',{'run_id':'run_test','attempt':i,'exit_code':exit})
 def test_cumulative_partial_resume_without_duplicate_writes(self):
  self.log(['mcp__drako_code__write_file']);self.log(sorted(b.common.TOOLS-{'mcp__drako_code__write_file'}),exit=0,i=2);self.state['native_invocations']=2
  self.assertEqual(set(s.logs(self.d,self.j,self.state)),b.common.TOOLS)
 def test_nonzero_wait_is_preserved(self):
  self.log(sorted(b.common.TOOLS));s.logs(self.d,self.j,self.state);self.assertEqual(b.private_json(self.d/'native-attempts/1/wait.json')['exit_code'],-15)
 def test_permission_denial_holds(self):
  self.log(extra={'subtype':'permission_denied'})
  with self.assertRaises(RuntimeError):s.logs(self.d,self.j,self.state)
 def test_unexpected_tool_holds(self):
  self.log(['Bash'])
  with self.assertRaises(RuntimeError):s.logs(self.d,self.j,self.state)
 def test_inventory_drift_holds(self):
  self.log(inventory=['Bash'])
  with self.assertRaises(RuntimeError):s.logs(self.d,self.j,self.state)
 def test_budget_is_global_not_reset_on_resume(self):
  self.state['native_invocations']=4
  with self.assertRaises(RuntimeError):s.logs(self.d,self.j,self.state)
 def test_per_attempt_tool_bound(self):
  self.log(['mcp__drako_code__ticket_read']*17)
  with self.assertRaises(RuntimeError):s.logs(self.d,self.j,self.state)
 def test_unresolved_operations_hold(self):
  for name in s.PENDING:
   p=self.d/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
   with self.assertRaises(RuntimeError):s.clear_intents(self.d)
   p.unlink()
 def test_missing_wait_holds(self):
  self.log();(self.d/'native-attempts/1/wait.json').unlink()
  with self.assertRaises(Exception):s.logs(self.d,self.j,self.state)
 def test_foreign_or_live_owner_holds(self):
  sys.path.insert(0,'/Users/zaccromero/.drako/hermes/current/source')
  w={'claim_id':'c','actor':{'client':'claude'},'files':{},'writes':2,'tests':1};(self.d/'results').mkdir();b.atomic(self.d/'results/worker-state.json',w)
  t={'id':'c','state':'active','worktree':str(s.ROOT),'owner':w['actor'],'scopes':[]}
  with patch.object(s,'task',return_value=t),patch.object(b.common,'files',return_value={}),patch('hermes_cli.agent_tasks.group_dead',return_value=False):
   with self.assertRaises(RuntimeError):s.owner(self.d,{'queue_expected_scopes':[]},{})
  t['owner']={'client':'codex'}
  with patch.object(s,'task',return_value=t):
   with self.assertRaises(RuntimeError):s.owner(self.d,{'queue_expected_scopes':[]},{})
if __name__=='__main__':unittest.main()
