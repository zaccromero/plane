"""Fixed, private VM receiver. No listener, tunnel, model dispatch or prompt data."""
import base64
import datetime
import fcntl
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def save(path, value):
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(value, out, sort_keys=True)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)


class Backend:
    def __init__(self):
        env = dict(line.split('=', 1) for line in Path('/opt/otel/.env').read_text().splitlines()
                   if '=' in line and not line.startswith('#'))
        self.headers = {'Authorization': 'Basic ' + env['LANGFUSE_OTEL_AUTH'].strip().strip('"').strip("'")}

    def call(self, path, data=None, protobuf=False):
        headers = dict(self.headers)
        if protobuf:
            headers.update({'Content-Type': 'application/x-protobuf', 'x-langfuse-ingestion-version': '4'})
        elif data is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(data).encode()
        request = urllib.request.Request('http://127.0.0.1:3000/api/public/' + path,
                                         data=data, headers=headers)
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read()
            return json.loads(raw) if raw and not protobuf else {}

    def observe(self, trace, root_span):
        now = datetime.datetime.now(datetime.timezone.utc)
        query = urllib.parse.urlencode(dict(traceId=trace, fields='core,basic', limit=100,
            fromStartTime=(now-datetime.timedelta(days=7)).isoformat(), toStartTime=(now+datetime.timedelta(minutes=5)).isoformat()))
        rows = self.call('v2/observations?' + query).get('data', [])
        ids = sorted({row['id'] for row in rows if row.get('traceId') == trace})
        return {'trace_observed': root_span in ids, 'trace_id': trace, 'observation_ids': ids}

    def ingest(self, payload):
        self.call('otel/v1/traces', payload, protobuf=True)

    def score(self, trace, score_id, value):
        self.call('scores', dict(id=score_id, traceId=trace, name='drako-coding-lane-v1',
            dataType='BOOLEAN', value=int(value), comment='Deterministic checks; owner acceptance remains pending.'))

    def read_score(self, trace, score_id, value):
        rows = self.call('v3/scores?' + urllib.parse.urlencode(dict(traceId=trace, id=score_id,
            fields='subject', limit=100))).get('data', [])
        return any(row['id'] == score_id and row.get('subject') == {'kind':'trace','id':trace}
            and row.get('value') == bool(value) for row in rows)


def receive(envelope, state_root, backend, attempts=20, pause=time.sleep):
    trace = envelope.get('trace_id', '')
    root_span = envelope.get('root_span_id', '')
    if not re.fullmatch('[0-9a-f]{32}', trace) or not re.fullmatch('[0-9a-f]{16}', root_span):
        raise ValueError('Invalid trace identity')
    kind = envelope.get('kind')
    if kind not in ('trace', 'score'):
        raise ValueError('Unknown operation')
    payload = None
    if kind == 'trace':
        payload = base64.b64decode(envelope['payload'], validate=True)
        if not payload or len(payload) > 1000000 or hashlib.sha256(payload).hexdigest() != envelope.get('payload_sha256'):
            raise ValueError('Invalid immutable payload')
        digest = envelope['payload_sha256']
    else:
        if type(envelope.get('passed')) is not bool:
            raise ValueError('Score must be boolean')
        digest = hashlib.sha256(json.dumps({'trace':trace, 'passed':envelope['passed']}, sort_keys=True).encode()).hexdigest()
    root = Path(state_root) / trace
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(root / 'lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = root / (kind + '.json')
        old = json.loads(path.read_text()) if path.exists() else None
        if old and old['sha256'] != digest:
            raise ValueError('Same trace identity with different payload or score')
        score_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'drako-coding-lane-v1:' + trace))

        def receipt():
            observed = backend.observe(trace, root_span)
            if kind == 'trace':
                return observed if observed['trace_observed'] else None
            if observed['trace_observed'] and backend.read_score(trace, score_id, envelope['passed']):
                return dict(observed, score_observed=True, score_id=score_id, value=envelope['passed'])
            return None

        found = receipt()
        if found:
            # A new/different payload cannot adopt somebody else's observed identity.
            if kind == 'trace' and old is None:
                raise RuntimeError('Observed trace predates receiver state; reconcile identity')
            save(path, {'sha256':digest,'status':'confirmed','receipt':found})
            return found
        if old is None:
            save(path, {'sha256':digest,'status':'submission_started'})
            if kind == 'trace':
                backend.ingest(payload)
            else:
                # A trace must exist before its evaluation is submitted.
                if not backend.observe(trace, root_span)['trace_observed']:
                    raise RuntimeError('Cannot score an unobserved trace')
                backend.score(trace, score_id, envelope['passed'])
        # Old submission_started means unknown outcome, never permission to submit again.
        for attempt in range(attempts):
            found = receipt()
            if found:
                save(path, {'sha256':digest,'status':'confirmed','receipt':found})
                return found
            if attempt+1 < attempts:
                pause(1)
        raise RuntimeError('UNKNOWN: submission retained; query backend before any retry')


if __name__ == '__main__':
    try:
        raw = sys.stdin.buffer.read(1500001)
        if len(raw) > 1500000:
            raise ValueError('Envelope too large')
        print(json.dumps(receive(json.loads(raw), '/var/lib/drako-plane-lane/outbox', Backend())))
    except Exception as error:
        print(json.dumps({'status':'UNKNOWN', 'error_type':type(error).__name__}))
        raise SystemExit(1)
