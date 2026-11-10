"""Importer behaviour against a disposable cortex tree and an in-memory Plane. No network."""
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path

import cortex_import as ci


def record(ident, title='A task', status='triage', extra=''):
    return f'---\nid: {ident}\ntitle: "{title}"\nstatus: {status}\npriority: high\ntags: []\n{extra}---\n\n# {title}\n\nBody <b>text</b>.\n'


class FakePlane:
    """Keeps Plane's contract: unique (external_source, external_id), labels by id."""
    def __init__(self, states=None):
        self.state_rows = states if states is not None else [
            {'id': 's-todo', 'group': 'unstarted', 'default': True},
            {'id': 's-back', 'group': 'backlog', 'default': False}]
        self.label_rows = [{'id': 'l0', 'name': 'cortex-import'}]
        self.issues = {}
        self.lose_reply_for = None
    def states(self):
        return self.state_rows
    def labels(self):
        return list(self.label_rows)
    def create_label(self, name):
        row = {'id': 'l%d' % len(self.label_rows), 'name': name}
        self.label_rows.append(row)
        return row
    def create_issue(self, data):
        key = (data['external_source'], data['external_id'])
        if key in self.issues:
            return self.issues[key]['id'], False
        self.issues[key] = dict(data, id='i%d' % len(self.issues))
        if self.lose_reply_for == data['external_id']:
            self.lose_reply_for = None
            raise TimeoutError('Reply lost after server write')
        return self.issues[key]['id'], True


class CortexImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for rel, text in {
            'tasks/gym-nyc/01A-open.md': record('01A', status='open'),
            'tasks/gym-nyc/01B-deferred.md': record('01B', status='deferred'),
            'tasks/milo/01C-trigger.md': record('01C', status='deferred-with-trigger', extra='project: "Milo"\n'),
            'tasks/milo/01D-nofence.md': '# just prose\n',
            'tasks/milo/01E-noid.md': '---\ntitle: x\nstatus: open\n---\n',
            'tasks/_schema.md': record('SCHEMA'),
            'tasks/milo/archive/01F-old.md': record('01F', status='open'),
            'timeline/01M-milestone.md': record('01M', title='Ship it', status='planned', extra='due: 2026-08-15\nblocked_by:\n  - 01A\n'),
            'timeline/01N-done.md': record('01N', status='done'),
            'timeline/_schema.md': record('SCHEMA2'),
            'workflow/tickets/GOV-9/ticket.md': '---\nid: GOV-9\ntitle: Open governance\nstate: Open\n---\nbody\n',
            'workflow/tickets/GOV-1/ticket.md': '---\nid: GOV-1\ntitle: Closed governance\nstate: Closed\n---\nbody\n',
            'workflow/tickets/.template/ticket.md': '---\nid: TEMPLATE\ntitle: t\nstate: Open\n---\n',
        }.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.records, self.skipped = ci.collect(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_selects_only_live_records_and_reports_the_rest(self):
        self.assertEqual(sorted(r['id'] for r in self.records), ['01A', '01C', '01M', 'GOV-9'])
        reasons = {row['path']: row['reason'] for row in self.skipped}
        self.assertEqual(reasons['tasks/gym-nyc/01B-deferred.md'], 'status not selected: deferred')
        self.assertEqual(reasons['tasks/milo/01D-nofence.md'], 'no frontmatter fence')
        self.assertEqual(reasons['tasks/milo/01E-noid.md'], 'missing id or title')
        self.assertEqual(reasons['timeline/01N-done.md'], 'milestone closed: done')
        self.assertEqual(reasons['workflow/tickets/GOV-1/ticket.md'], 'governance ticket closed: closed')
        for never in ('tasks/_schema.md', 'timeline/_schema.md', 'workflow/tickets/.template/ticket.md', 'tasks/milo/archive/01F-old.md'):
            self.assertNotIn(never, reasons)
            self.assertNotIn(never, [r['path'] for r in self.records])

    def test_include_status_widens_task_selection_only(self):
        records, _ = ci.collect(self.root, ci.TASK_STATUSES + ('deferred',))
        self.assertIn('01B', [r['id'] for r in records])
        self.assertNotIn('01N', [r['id'] for r in records])

    def test_project_comes_from_frontmatter_then_folder(self):
        by_id = {r['id']: r for r in self.records}
        self.assertEqual(by_id['01A']['project'], 'gym-nyc')
        self.assertEqual(by_id['01C']['project'], 'Milo')
        self.assertIn('project:milo', ci.labels_for(by_id['01C']))

    def test_dry_run_writes_nothing(self):
        plane = FakePlane()
        summary = ci.run(plane, self.records)
        self.assertEqual((summary['selected'], summary['created'], plane.issues, len(plane.label_rows)), (4, 0, {}, 1))
        self.assertIn('needs-redate', summary['labels_missing'])
        self.assertNotIn('cortex-import', summary['labels_missing'])

    def test_apply_lands_in_backlog_without_dates_and_is_idempotent(self):
        plane = FakePlane()
        first = ci.run(plane, self.records, apply=True)
        self.assertEqual((first['created'], first['existing'], first['failed']), (4, 0, []))
        for issue in plane.issues.values():
            self.assertEqual(issue['state'], 's-back')
            self.assertEqual(issue['external_source'], 'drako-cortex')
            self.assertNotIn('target_date', issue)
            self.assertNotIn('start_date', issue)
        milestone = plane.issues[('drako-cortex', '01M')]
        names = {row['id']: row['name'] for row in plane.label_rows}
        self.assertIn('needs-redate', [names[i] for i in milestone['labels']])
        self.assertIn('Original due date 2026-08-15', milestone['description_html'])
        self.assertIn('&lt;b&gt;text&lt;/b&gt;', milestone['description_html'])
        second = ci.run(plane, self.records, apply=True)
        self.assertEqual((second['created'], second['existing'], second['labels_created'], len(plane.issues)), (0, 4, 0, 4))

    def test_lost_reply_is_reported_then_settled_without_a_duplicate(self):
        plane = FakePlane()
        plane.lose_reply_for = '01C'
        first = ci.run(plane, self.records, apply=True)
        self.assertEqual(first['failed'], [{'id': '01C', 'error': 'TimeoutError'}])
        second = ci.run(plane, self.records, apply=True)
        self.assertEqual((second['created'], second['existing'], second['failed'], len(plane.issues)), (0, 4, [], 4))

    def test_limit_is_a_canary(self):
        plane = FakePlane()
        self.assertEqual(ci.run(plane, self.records, apply=True, limit=1)['created'], 1)
        self.assertEqual(len(plane.issues), 1)

    def test_refuses_a_project_without_backlog(self):
        with self.assertRaises(ValueError):
            ci.run(FakePlane(states=[{'id': 's', 'group': 'unstarted', 'default': True}]), self.records, apply=True)

    def test_cortex_tree_is_untouched(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        ci.run(FakePlane(), self.records, apply=True)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_frontmatter_edges(self):
        meta, body = ci.parse_frontmatter('---\na: "q: x"\nb: null\nlist:\n  - one\n# note\n---\nBody')
        self.assertEqual((meta, body), ({'a': 'q: x', 'b': None, 'list': None}, 'Body'))
        for bad in ('no fence', '---\na: 1\n', '---\nnot a pair\n---\n'):
            with self.assertRaises(ValueError):
                ci.parse_frontmatter(bad)

    def test_long_fields_are_bounded(self):
        data = ci.payload(dict(self.records[0], title='t' * 400, body='b' * 70000), 's', [])
        self.assertEqual(len(data['name']), 255)
        self.assertIn('truncated on import', data['description_html'])

    def test_expired_or_exposed_binding_is_refused(self):
        token = self.root / 'token'
        token.write_text('secret-token\n')
        binding = self.root / 'binding.json'
        def write(expires):
            binding.write_text(json.dumps({'base_url': 'http://127.0.0.1:8097', 'workspace': 'w', 'project_id': 'p',
                                           'token_file': str(token), 'expires_at': expires}))
        os.chmod(token, 0o600)
        write('2026-01-01T00:00:00Z')
        os.chmod(binding, 0o600)
        now = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(ValueError, 'expired'):
            ci.load_client(binding, now=now)
        write('2027-01-01T00:00:00Z')
        self.assertEqual(ci.load_client(binding, now=now).project, 'p')
        os.chmod(token, 0o644)
        with self.assertRaisesRegex(ValueError, 'private'):
            ci.load_client(binding, now=now)


if __name__ == '__main__':
    unittest.main()
