"""One-way import of live drako-cortex records into the bound Plane project.

Cortex (markdown in git) is retired as a board and stays read-only history; Plane is
the board for work and deadlines. This copies the records still worth acting on:

  tasks/<project>/<ULID>-slug.md      status open, triage, deferred-with-trigger
  timeline/<ULID>-slug.md             every milestone not already done or cancelled
  workflow/tickets/<ID>/ticket.md     governance tickets that are not closed

Rules this tool keeps:
  * Never writes to drako-cortex. Never deletes or edits an existing Plane issue.
  * Idempotent through Plane's own (external_source, external_id) pair: a record that
    already exists answers 409 and is counted as existing, not duplicated.
  * Every issue lands in the Backlog state group. Nothing imported is ever "ready".
  * No dates are imported. Every Cortex due date is in the past; a milestone keeps its
    original date as text and gets the label needs-redate, so a deadline exists in
    Plane only after the owner sets one.
  * A record that does not parse is reported and skipped, never guessed at.
  * Dry run is the default. The API token is never printed.

Usage:
  python3 drako/cortex_import.py --binding ~/.config/drako-plane/binding.json
  python3 drako/cortex_import.py --binding ... --apply --limit 3     # canary
  python3 drako/cortex_import.py --binding ... --apply
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from agent_lane import load_binding
from workflow import ProjectPlane

SOURCE = 'drako-cortex'
TASK_STATUSES = ('open', 'triage', 'deferred-with-trigger')
MILESTONE_CLOSED = ('done', 'cancelled', 'completed')
GOVERNANCE_CLOSED = ('closed', 'done', 'cancelled')
PRIORITY = {'urgent': 'urgent', 'p0': 'urgent', 'high': 'high', 'p1': 'high', 'load-bearing': 'high',
            'medium': 'medium', 'p2': 'medium', 'low': 'low', 'p3': 'low'}
MAX_NAME = 255
MAX_BODY = 60000
LABEL_COLOR = '#6b7280'
PACE_SECONDS = 1.1      # Plane allows about 60 API requests a minute per key
MAX_RATE_WAITS = 8      # a 429 waits for the window to reopen; it is never counted as a failed record


def parse_frontmatter(text):
    """Top-level scalar keys of a `---` fenced block, plus the body. Nested values are ignored."""
    lines = text.split('\n')
    if not lines or lines[0].strip() != '---':
        raise ValueError('no frontmatter fence')
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == '---')
    except StopIteration:
        raise ValueError('unterminated frontmatter') from None
    meta = {}
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith('#') or raw[0] in ' \t-':
            continue  # blank, comment, or part of a nested block we do not need
        key, sep, value = raw.partition(':')
        if not sep or not key.strip() or ' ' in key.strip():
            raise ValueError('invalid frontmatter line')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        meta[key.strip()] = None if value in ('', 'null', '~', '[]') else value
    return meta, '\n'.join(lines[end + 1:]).strip()


def collect(root, statuses=TASK_STATUSES):
    """Read-only walk of a cortex checkout. Returns (records, skipped)."""
    root = Path(root)
    records, skipped = [], []

    def skip(path, reason):
        skipped.append({'path': str(path.relative_to(root)), 'reason': reason})

    def read(path, kind):
        try:
            meta, body = parse_frontmatter(path.read_text(encoding='utf-8'))
        except (ValueError, UnicodeDecodeError) as error:
            return skip(path, str(error))
        ident, title = meta.get('id'), meta.get('title')
        if not ident or not title:
            return skip(path, 'missing id or title')
        status = (meta.get('state') if kind == 'governance' else meta.get('status')) or 'unknown'
        status = status.lower()
        if kind == 'task' and status not in statuses:
            return skip(path, 'status not selected: ' + status)
        if kind == 'milestone' and status in MILESTONE_CLOSED:
            return skip(path, 'milestone closed: ' + status)
        if kind == 'governance' and status in GOVERNANCE_CLOSED:
            return skip(path, 'governance ticket closed: ' + status)
        project = meta.get('project') or (path.parent.name if kind == 'task' else None)
        records.append({'kind': kind, 'id': ident, 'title': title, 'status': status, 'project': project,
                        'priority': PRIORITY.get((meta.get('priority') or '').lower(), 'none'),
                        'due': meta.get('due'), 'path': str(path.relative_to(root)), 'body': body})

    for kind, pattern in (('task', 'tasks/*/*.md'), ('milestone', 'timeline/*.md'),
                          ('governance', 'workflow/tickets/*/ticket.md')):
        for path in sorted(root.glob(pattern)):
            if path.is_symlink() or not path.is_file():
                continue
            if path.name.startswith('_') or any(part.startswith('.') for part in path.relative_to(root).parts):
                continue  # schema documents and templates are not records
            read(path, kind)
    seen = {}
    unique = []
    for record in records:
        if record['id'] in seen:
            skipped.append({'path': record['path'], 'reason': 'duplicate id, first seen at ' + seen[record['id']]})
            continue
        seen[record['id']] = record['path']
        unique.append(record)
    return unique, skipped


def labels_for(record):
    names = ['cortex-import', 'cortex:' + record['kind'], 'status:' + record['status']]
    if record['project']:
        names.append('project:' + record['project'].lower())
    if record['kind'] == 'milestone':
        names.append('needs-redate')
    return names


def describe(record):
    body = record['body']
    if len(body) > MAX_BODY:
        body = body[:MAX_BODY] + '\n\n[truncated on import; full text is in the Cortex file]'
    parts = ['<p>' + html.escape(block).replace('\n', '<br/>') + '</p>' for block in body.split('\n\n') if block.strip()]
    origin = 'Imported from drako-cortex: ' + record['path'] + ' (id ' + record['id'] + ', status ' + record['status'] + ').'
    if record['kind'] == 'milestone' and record['due']:
        origin += ' Original due date ' + record['due'] + ' has passed and was not imported; set a new date here.'
    parts.append('<p><em>' + html.escape(origin) + '</em></p>')
    return ''.join(parts)


def payload(record, state_id, label_ids):
    return {'name': record['title'][:MAX_NAME], 'description_html': describe(record),
            'priority': record['priority'], 'state': state_id, 'labels': label_ids,
            'external_source': SOURCE, 'external_id': record['id']}


class ImportPlane(ProjectPlane):
    """ProjectPlane plus the few list/create calls an import needs. Still one origin, no redirects."""

    sleep = staticmethod(time.sleep)

    def send(self, req):
        """One request, paced, waiting out Plane's rate limit instead of failing the record."""
        for _ in range(MAX_RATE_WAITS):
            self.sleep(PACE_SECONDS)
            try:
                with self.open(req, timeout=15) as response:
                    return None if response.status == 204 else json.load(response)
            except urllib.error.HTTPError as error:
                if error.code != 429:
                    raise
                try:
                    wait = float(error.headers.get('Retry-After') or 20)
                except (TypeError, ValueError):
                    wait = 20.0
                self.sleep(min(max(wait, 1.0), 65.0))
        raise ValueError('Plane rate limit did not clear')

    def request(self, method, path, data=None):
        if not path.startswith('/') or '..' in path or '?' in path or '#' in path:
            raise ValueError('Invalid project-relative API route')
        return self.send(urllib.request.Request(self.base + self.prefix + path,
            data=None if data is None else json.dumps(data).encode(), method=method,
            headers={'X-API-Key': self.token, 'Content-Type': 'application/json'}))

    def paged(self, path):
        rows, cursor = [], None
        for _ in range(200):
            query = {'per_page': '100'}
            if cursor:
                query['cursor'] = cursor
            req = urllib.request.Request(self.base + self.prefix + path + '?' + urllib.parse.urlencode(query),
                                         method='GET', headers={'X-API-Key': self.token})
            page = self.send(req)
            if isinstance(page, list):
                return rows + page
            rows += page.get('results', [])
            if not page.get('next_page_results'):
                return rows
            cursor = page.get('next_cursor')
            if not cursor:
                raise ValueError('Plane pagination gave no cursor')
        raise ValueError('Plane pagination did not end')

    def states(self):
        return self.paged('/states/')

    def labels(self):
        return self.paged('/labels/')

    def create_label(self, name):
        return self.request('POST', '/labels/', {'name': name, 'color': LABEL_COLOR})

    def create_issue(self, data):
        """Returns (issue_id, created). An existing (external_source, external_id) is not an error."""
        try:
            return self.request('POST', '/issues/', data)['id'], True
        except urllib.error.HTTPError as error:
            if error.code != 409:
                raise
            existing = json.load(error).get('id')
            if not existing:
                raise ValueError('Plane reported a conflict without the existing issue') from None
            return existing, False


def load_client(binding_path, now=None):
    load_binding(binding_path)  # reuse the adapter's private-file checks for binding and token
    data = json.loads(Path(binding_path).read_text())
    expires = data.get('expires_at')
    if expires:
        when = dt.datetime.fromisoformat(str(expires).replace('Z', '+00:00'))
        if when.tzinfo is None:
            when = when.replace(tzinfo=dt.timezone.utc)
        if (now or dt.datetime.now(dt.timezone.utc)) >= when:
            raise ValueError('Plane token in the binding has expired; mint a new one before importing')
    return ImportPlane(data['base_url'], Path(data['token_file']).read_text().strip(), data['workspace'], data['project_id'])


def run(client, records, apply=False, limit=None):
    """Create what is missing. Returns a summary that contains no issue text and no credentials."""
    backlog = [s for s in client.states() if s.get('group') == 'backlog']
    if not backlog:
        raise ValueError('Bound Plane project has no Backlog state; refusing to import into an active state')
    state_id = next((s for s in backlog if s.get('default')), backlog[0])['id']
    selected = records if limit is None else records[:limit]
    known = {label['name']: label['id'] for label in client.labels()}
    wanted = sorted({name for record in selected for name in labels_for(record)})
    summary = {'apply': apply, 'selected': len(selected), 'created': 0, 'existing': 0, 'failed': [],
               'labels_missing': [name for name in wanted if name not in known], 'labels_created': 0,
               'by_kind': {}, 'state': 'backlog'}
    for record in selected:
        summary['by_kind'][record['kind']] = summary['by_kind'].get(record['kind'], 0) + 1
    if not apply:
        return summary
    for name in summary['labels_missing']:
        known[name] = client.create_label(name)['id']
        summary['labels_created'] += 1
    for record in selected:
        try:
            _, created = client.create_issue(payload(record, state_id, [known[n] for n in labels_for(record)]))
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as error:
            # A lost reply may still have written. The next run settles it through the 409 path.
            summary['failed'].append({'id': record['id'], 'error': type(error).__name__ + (' %s' % error.code if isinstance(error, urllib.error.HTTPError) else '')})
            continue
        summary['created' if created else 'existing'] += 1
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--binding', required=True)
    parser.add_argument('--cortex', default=str(Path.home() / 'code/projects/drako-cortex'))
    parser.add_argument('--apply', action='store_true', help='write to Plane; without it nothing is created')
    parser.add_argument('--limit', type=int, help='import only the first N selected records (canary)')
    parser.add_argument('--include-status', action='append', default=[],
                        help='also import tasks with this Cortex status (repeatable)')
    args = parser.parse_args(argv)
    records, skipped = collect(args.cortex, TASK_STATUSES + tuple(s.lower() for s in args.include_status))
    summary = run(load_client(args.binding), records, apply=args.apply, limit=args.limit)
    reasons = {}
    for row in skipped:
        key = row['reason'].split(':')[0]
        reasons[key] = reasons.get(key, 0) + 1
    summary['skipped'] = reasons
    summary['unparsed'] = [row for row in skipped if row['reason'] in
                           ('no frontmatter fence', 'unterminated frontmatter', 'invalid frontmatter line', 'missing id or title')]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if summary['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
