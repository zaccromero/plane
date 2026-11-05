import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import common
import runner
import tool_server

class RunnerTests(unittest.TestCase):
    def test_inventory_exact(self):
        runner.validate_inventory(list(common.TOOLS))
        for tools in [[], list(common.TOOLS)+['Bash'], list(common.TOOLS)-[] if False else ['Bash']]:
            with self.assertRaises(RuntimeError): runner.validate_inventory(tools)

    def test_permission_scope(self):
        argv=runner.native_argv({'native_session_id':'bounded'}, {'session':'/session'}, '/run')
        self.assertEqual(argv[argv.index('--tools')+1], '')
        self.assertEqual(set(argv[argv.index('--allowedTools')+1].split(',')),common.TOOLS)
        self.assertIn('--strict-mcp-config',argv)
        self.assertNotIn('--dangerously-skip-permissions',argv)
        self.assertEqual(argv[argv.index('--permission-mode')+1],'manual')

    def test_no_model_arguments(self):
        worker=tool_server.Worker('/unused')
        for name,args in [('approved_check',{'command':'rm'}),('Bash',{}),('result',{'path':'/tmp'})]:
            with self.assertRaises(RuntimeError): worker.call(name,args)

    def test_mcp_schema_and_protocol(self):
        output=io.StringIO()
        tool_server.serve(None,io.StringIO(json.dumps({'id':1,'method':'tools/list'})+'\n'),output)
        tools=json.loads(output.getvalue())['result']['tools']
        self.assertEqual(len(tools),3)
        for tool in tools:
            self.assertFalse(tool['inputSchema']['additionalProperties'])
            self.assertEqual(tool['inputSchema']['properties'],{})

    def test_recovery_preserves_owner_acceptance(self):
        rows=[{'id':'review','name':'Owner Review','group':'started'}, {'id':'done','name':'Done','group':'completed'}, {'id':'todo','name':'Todo','group':'unstarted'}]
        self.assertIsNone(runner.review_transition('published', {'state':'done'}, rows))
        self.assertIsNone(runner.review_transition('published', {'state':'review'}, rows))
        with self.assertRaises(RuntimeError):runner.review_transition('executed', {'state':'done'}, rows)
        with self.assertRaises(RuntimeError):runner.review_transition('published', {'state':'todo'}, rows)
        self.assertEqual(runner.review_transition('executed', {'state':'todo'}, rows),'review')

    def test_fixed_check(self):
        argv=common.check_argv({'workload':'/guard','python':'/python3.14'})
        self.assertEqual(argv[:4],['/guard','run','/python3.14','-B'])
        self.assertEqual(argv[-2:],['test_stage.py','-v'])

    def test_unknown_execution_never_relaunches(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp)
            common.atomic(d/'state.json',{'phase':'launch_started','native_invocations':1})
            with patch.object(runner,'load_job',return_value=(d,{},{})),patch.object(runner,'execute') as execute:
                with self.assertRaises(RuntimeError):runner.run(d)
                execute.assert_not_called()

    def test_completed_execution_recovery_skips_model(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp)
            common.atomic(d/'state.json',{'phase':'executed','native_invocations':1})
            with patch.object(runner,'load_job',return_value=(d,{},{})),patch.object(runner,'execute') as execute,patch.object(runner,'publish') as publish:
                runner.run(d)
                execute.assert_not_called();publish.assert_called_once()

    def test_private_file_and_check_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);(d/'results').mkdir()
            value={'run_id':'run_a','ticket_id':'a','exit_code':0,'output':'Ran 1 test\n\nOK\n'}
            common.atomic(d/'results/check.json',value)
            self.assertEqual(common.check_result(d,{'run_id':'run_a','ticket_id':'a'}),value)
            with self.assertRaises(RuntimeError):common.check_result(d,{'run_id':'run_b','ticket_id':'a'})
            (d/'results/check.json').chmod(0o644)
            with self.assertRaises(RuntimeError):common.private_json(d/'results/check.json')

if __name__=='__main__': unittest.main()
