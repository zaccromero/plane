import importlib.util,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('batch',Path(__file__).with_name('batch.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Batch(unittest.TestCase):
 def test_unrelated_or_symlink_state_rejected(self):
  with self.assertRaisesRegex(RuntimeError,'private native'):m.path_for('/tmp/batch_123.json')
 def test_native_matrix_uses_both_existing_projects(self):
  self.assertEqual(m.REQUESTS,[('drako-tools','codex'),('drako-map','claude')])
 def test_published_run_not_reexecuted(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);state=root/('batch_'+'0'*32+'.json');runs=[]
   for n,(project,engine) in enumerate(m.REQUESTS):
    d=root/str(n);d.mkdir();(d/'state.json').write_text(json.dumps({'phase':'published','native_invocations':1}));(d/'state.json').chmod(0o600);runs.append({'run_dir':str(d)})
   state.write_text(json.dumps({'config':'/config','ticket':'ticket','requests':[list(x) for x in m.REQUESTS],'runs':runs,'phase':'published'}));state.chmod(0o600)
   with patch.object(m,'BASE',root),patch.object(m.runner,'run') as run,patch.object(m.subprocess,'check_output') as prepare:
    m.run('/config','ticket',state);run.assert_not_called();prepare.assert_not_called()
 def test_uncertain_run_propagates_without_reprepare(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);state=root/('batch_'+'1'*32+'.json');d=root/'run';d.mkdir();(d/'state.json').write_text(json.dumps({'phase':'launch_started','native_invocations':1}));(d/'state.json').chmod(0o600);state.write_text(json.dumps({'config':'/config','ticket':'ticket','requests':[list(x) for x in m.REQUESTS],'runs':[{'run_dir':str(d)}],'phase':'running'}));state.chmod(0o600)
   with patch.object(m,'BASE',root),patch.object(m.runner,'run',side_effect=RuntimeError('uncertain')),patch.object(m.subprocess,'check_output') as prepare:
    with self.assertRaisesRegex(RuntimeError,'uncertain'):m.run('/config','ticket',state)
    prepare.assert_not_called()
if __name__=='__main__':unittest.main()
