"""Stable RunJournal telemetry over a fixed SSH command, without a tunnel."""
import base64
import hashlib
import json
import re
import subprocess
from pathlib import Path

from workflow import atomic


def stage(run_dir):
    """Freeze span IDs and bytes once. A retry never calls run_spans again."""
    import fcntl
    from drako_control import tracing
    root = Path(run_dir)
    with open(root / 'trace-stage.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run = json.loads((root / 'run.json').read_text())
        trace = json.loads((root / 'trace.json').read_text())
        events = (root / 'events.jsonl').read_bytes()
        if run['status'] != 'completed':
            raise ValueError('Only completed execution may be qualified')
        identity = {key: run[key] for key in ('run_id','task_id','project_id','correlation_id','status','created_at')}
        identity['trace_id'] = trace['trace_id']
        identity['root_span_id'] = trace['root_span_id']
        source_sha = hashlib.sha256(json.dumps(identity, sort_keys=True).encode() + events).hexdigest()
        path = root / 'trace-payload.json'
        if path.exists():
            value = json.loads(path.read_text())
            if value['source_sha256'] != source_sha:
                raise ValueError('Run changed after telemetry was frozen')
            return value
        spans = tracing.run_spans(run, [json.loads(line) for line in events.splitlines()], trace)
        payload = tracing.encode(spans, service='drako-plane-lane', project='drako-agents')
        value = dict(kind='trace', trace_id=trace['trace_id'], root_span_id=trace['root_span_id'],
            source_sha256=source_sha, payload_sha256=hashlib.sha256(payload).hexdigest(),
            payload=base64.b64encode(payload).decode())
        atomic(path, value)
        return value


def deliver(envelope, host, identity_file, receiver='/opt/drako-plane-lane/trace_receiver.py'):
    if not re.fullmatch(r'[a-zA-Z0-9_.@-]+', host) or host.startswith('-'):
        raise ValueError('Invalid fixed SSH destination')
    if receiver != '/opt/drako-plane-lane/trace_receiver.py':
        raise ValueError('Receiver command is fixed')
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
        '-i', str(identity_file), host, 'python3 ' + receiver],
        input=json.dumps(envelope), text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError('Trace receiver did not confirm delivery: ' + result.stdout[:300])
    return json.loads(result.stdout)
