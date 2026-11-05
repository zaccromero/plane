"""Shared, fail-closed bindings for a single approved Plane job."""
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'drako'))
from workflow import atomic
from lane import verify_context

TOOLS = {'mcp__drako_lane__ticket_read', 'mcp__drako_lane__approved_check', 'mcp__drako_lane__result'}
CATALOG = 'immutable-span-check'


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def private_json(path):
    path = Path(path)
    st = path.lstat()
    need(stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and not st.st_mode & 0o077,
         'Expected a private, same-owner regular file')
    return json.loads(path.read_text())


def fingerprint(path):
    p = Path(path).resolve(strict=True)
    st = p.stat()
    need(stat.S_ISREG(st.st_mode), 'Executable binding is not regular')
    return dict(path=str(p), device=st.st_dev, inode=st.st_ino, size=st.st_size, mtime_ns=st.st_mtime_ns)


def config(path):
    c = private_json(path)
    need(sys.version_info[:2] == (3, 14), 'Use the installed runner: Python 3.14 is required')
    need(Path(sys.executable).resolve() == Path(c['python']).resolve(), 'Unexpected Python executable')
    for name in ['python', 'claude', 'session', 'workload', 'doctor']:
        need(Path(c[name]).is_absolute(), 'Explicit executable paths required')
    need(Path(c['control_lib']).is_absolute(), 'Explicit Drako library required')
    return c


def ticket_context(ticket):
    return {k: ticket[k] for k in ['id', 'name', 'description_html', 'project']}


def load_job(directory):
    d = Path(directory).resolve(strict=True)
    need(d.parent == (ROOT / '.drako/runs').resolve(), 'Run outside the selected project')
    job = private_json(d / 'job.json')
    need(job['catalog'] == CATALOG and job['project_root'] == str(ROOT), 'Wrong project or job catalog')
    need(job['run_id'] == d.name, 'Run identity mismatch')
    c = config(job['config_path'])
    for name, value in job['executables'].items():
        need(fingerprint(c[name]) == value, 'Runtime executable changed: ' + name)
    need(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == job['source_head'],
         'Source revision changed')
    verify_context(private_json(d / 'context-manifest.json'))
    return d, job, c


def check_argv(c):
    # There is no command, path, environment or URL argument supplied by a model/ticket.
    return [c['workload'], c['python'], '-B', '-m', 'unittest', 'discover', '-s', 'drako', '-p', 'test_stage.py', '-v']


def check_result(directory, job):
    path = Path(directory) / 'results/check.json'
    value = private_json(path)
    need(value['run_id'] == job['run_id'] and value['ticket_id'] == job['ticket_id'], 'Check identity mismatch')
    need(value['exit_code'] == 0 and 'Ran 1 test' in value['output'] and '\nOK\n' in value['output']
         and 'skipped' not in value['output'].lower(), 'Approved check did not pass')
    return value


def payload_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
