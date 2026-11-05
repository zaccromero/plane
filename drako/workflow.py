"""Project-bound Plane operations; ownership remains in the native controller."""
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from lane import Plane, verify_context


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Plane redirects are refused; credentials stay at the configured origin')


class ProjectPlane(Plane):
    def __init__(self, base, token, workspace, project):
        super().__init__(base, token, workspace, project)
        u = urllib.parse.urlsplit(base)
        if u.username or u.password or u.query or u.fragment or u.path not in ('', '/'):
            raise ValueError('Plane binding requires a plain origin')
        self.project = project
        self.open = urllib.request.build_opener(NoRedirect()).open

    def request(self, method, path, data=None):
        if not path.startswith('/') or '..' in path or '?' in path or '#' in path:
            raise ValueError('Invalid project-relative API route')
        req = urllib.request.Request(self.base + self.prefix + path,
            data=None if data is None else json.dumps(data).encode(), method=method,
            headers={'X-API-Key': self.token, 'Content-Type': 'application/json'})
        with self.open(req, timeout=15) as response:
            return None if response.status == 204 else json.load(response)

    def get(self, ticket):
        value = super().get(ticket)
        if value['id'] != ticket or value.get('project') != self.project:
            raise ValueError('Ticket/project identity mismatch')
        return value

    def comments(self, ticket):
        self.get(ticket)
        page = self.request('GET', '/issues/' + urllib.parse.quote(ticket, safe='') + '/comments/')
        if isinstance(page, list):
            return page
        if page.get('next_page_results'):
            raise ValueError('Comment history requires pagination reconciliation')
        return page.get('results', [])


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError('Refuse symlink state')
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(value, out, sort_keys=True, indent=2)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)


def validate_evidence(evidence, expected, context):
    verify_context(context)
    for key in ('ticket_id', 'project_id', 'run_id', 'claim_id'):
        if not expected.get(key) or evidence.get(key) != expected[key]:
            raise ValueError('Evidence identity mismatch: ' + key)
    if evidence.get('context_sha256') != context['sha256']:
        raise ValueError('Evidence context mismatch')
    if evidence.get('checks_passed') is not True or evidence.get('trace_observed') is not True or evidence.get('score_observed') is not True:
        raise ValueError('Completion requires independently verified checks, trace and score')
    if evidence.get('owner_acceptance') != 'pending':
        raise ValueError('Machine checks cannot grant owner acceptance')


def post_evidence(client, evidence, expected, context, state_dir):
    """At most one POST per marker, even after timeout or concurrent invocation.

    An uncertain POST is read back; absent proof stays UNKNOWN, never blindly retried.
    """
    import fcntl
    validate_evidence(evidence, expected, context)
    if client.project != expected['project_id']:
        raise ValueError('Client project mismatch')
    marker = 'drako-evidence:' + hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    root = Path(state_dir)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(root / 'evidence.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = root / 'evidence-post.json'
        matches = [c for c in client.comments(expected['ticket_id']) if marker in c.get('comment_html', '')]
        if matches:
            atomic(path, {'marker': marker, 'status': 'confirmed', 'comment_id': matches[0]['id']})
            return {'status': 'confirmed', 'comment_id': matches[0]['id'], 'created': False}
        if path.exists():
            raise RuntimeError('Evidence write uncertain or different; reconcile existing state')
        atomic(path, {'marker': marker, 'status': 'submission_started'})
        import html
        text = html.escape(json.dumps(evidence, sort_keys=True, indent=2))
        client.comment(expected['ticket_id'], '<p>Qualification PASS; ready for owner review. ' + marker + '</p><pre>' + text + '</pre>')
        matches = [c for c in client.comments(expected['ticket_id']) if marker in c.get('comment_html', '')]
        if not matches:
            raise RuntimeError('Evidence POST returned but readback is unconfirmed')
        atomic(path, {'marker': marker, 'status': 'confirmed', 'comment_id': matches[0]['id']})
        return {'status': 'confirmed', 'comment_id': matches[0]['id'], 'created': True}
