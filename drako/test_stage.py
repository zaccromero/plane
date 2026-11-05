import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

if os.environ.get('DRAKO_CONTROL_LIB'):
    sys.path.insert(0,os.environ['DRAKO_CONTROL_LIB'])

from trace_bridge import stage


@unittest.skipUnless(os.environ.get('DRAKO_CONTROL_LIB'),'Existing Drako control-plane source is an explicit integration dependency')
class StageTests(unittest.TestCase):
    def test_stable_bytes_and_changed_events_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            run=dict(run_id='run',task_id='ticket',project_id='project',correlation_id='hash',status='completed',
                created_at='2026-11-05T16:00:00Z',runtime_id='test',agent_ids=['agent'])
            events=[dict(type='task_started',occurred_at='2026-11-05T16:00:00Z',data={'agent_id':'agent'}),
                dict(type='task_completed',occurred_at='2026-11-05T16:00:01Z',data={'agent_id':'agent'})]
            (root/'run.json').write_text(json.dumps(run))
            (root/'events.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in events))
            (root/'trace.json').write_text(json.dumps(dict(trace_id='a'*32,root_span_id='b'*16,parent_span_id='')))
            first=stage(root);second=stage(root)
            self.assertEqual(first,second)
            with (root/'events.jsonl').open('a') as out:out.write(json.dumps(events[-1])+'\n')
            with self.assertRaises(ValueError):stage(root)


if __name__=='__main__':unittest.main()
