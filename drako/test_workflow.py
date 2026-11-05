import base64
import concurrent.futures
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from lane import manifest
from workflow import ProjectPlane, NoRedirect, post_evidence, validate_evidence
from trace_receiver import receive
from agent_lane import claim_ticket


class Client:
    project = 'project'
    def __init__(self):
        self.rows = []
        self.writes = 0
        self.lose_reply = False
    def comments(self, ticket):
        return self.rows
    def get(self,ticket):
        return dict(id=ticket,project=self.project)
    def comment(self, ticket, html):
        self.writes += 1
        self.rows.append({'id':'comment', 'comment_html':html})
        if self.lose_reply:
            raise TimeoutError('Reply lost after server write')


class FakeBackend:
    def __init__(self):
        self.present = False
        self.score_present = False
        self.writes = 0
        self.score_writes = 0
        self.lose_reply = False
        self.visible = True
    def observe(self, trace, root):
        return dict(trace_observed=self.present and self.visible, trace_id=trace, observation_ids=[root] if self.present else [])
    def ingest(self, payload):
        self.writes += 1
        self.present = True
        if self.lose_reply:
            raise TimeoutError('Remote reply lost after acceptance')
    def score(self, trace, score_id, value):
        self.score_writes += 1
        self.score_present = True
    def read_score(self, trace, score_id, value):
        return self.score_present


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        p = self.root/'context.md'; p.write_text('owner-approved context')
        self.context = manifest([p])
        self.expected = dict(ticket_id='ticket', project_id='project', run_id='run', claim_id='claim')
        self.evidence = dict(self.expected, context_sha256=self.context['sha256'], checks_passed=True,
            trace_observed=True, score_observed=True, owner_acceptance='pending')
        raw = b'fixed validated caller-generated OTLP payload'
        self.envelope = dict(kind='trace', trace_id='a'*32, root_span_id='b'*16,
            payload=base64.b64encode(raw).decode(), payload_sha256=hashlib.sha256(raw).hexdigest())
    def tearDown(self):
        self.temp.cleanup()
    def test_evidence_retry_posts_once(self):
        client=Client()
        first=post_evidence(client,self.evidence,self.expected,self.context,self.root/'post')
        second=post_evidence(client,self.evidence,self.expected,self.context,self.root/'post')
        self.assertTrue(first['created']);self.assertFalse(second['created']);self.assertEqual(client.writes,1)
    def test_lost_comment_reply_is_reconciled(self):
        client=Client();client.lose_reply=True
        with self.assertRaises(TimeoutError):post_evidence(client,self.evidence,self.expected,self.context,self.root/'post')
        self.assertFalse(post_evidence(client,self.evidence,self.expected,self.context,self.root/'post')['created'])
        self.assertEqual(client.writes,1)
    def test_unknown_comment_never_reposts(self):
        client=Client();client.lose_reply=True
        with self.assertRaises(TimeoutError):post_evidence(client,self.evidence,self.expected,self.context,self.root/'post')
        client.rows=[]
        with self.assertRaises(RuntimeError):post_evidence(client,self.evidence,self.expected,self.context,self.root/'post')
        self.assertEqual(client.writes,1)
    def test_every_wrong_identity_rejected(self):
        for key in self.expected:
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_evidence(dict(self.evidence,**{key:'other'}),self.expected,self.context)
    def test_incomplete_checks_and_fake_acceptance_rejected(self):
        for key,value in [('checks_passed',False),('trace_observed',False),('score_observed',False),('owner_acceptance','accepted')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_evidence(dict(self.evidence,**{key:value}),self.expected,self.context)
    def test_redirect_refused(self):
        with self.assertRaises(ValueError):NoRedirect().redirect_request(None,None,None,None,None,None)
    def test_embedded_credentials_and_base_paths_refused(self):
        for base in ['https://user:secret@example.com','https://example.com/api','https://example.com?x=1']:
            with self.subTest(base=base),self.assertRaises(ValueError):ProjectPlane(base,'token','w','p')
    def test_wrong_project_response_rejected(self):
        p=ProjectPlane('http://localhost','token','w','project')
        p.request=lambda *args:dict(id='ticket',project='other')
        with self.assertRaises(ValueError):p.get('ticket')
    def test_trace_retry_and_parallel_delivery_ingest_once(self):
        backend=FakeBackend()
        def send(_):return receive(self.envelope,self.root/'remote',backend,attempts=1)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(send,range(2)))
        self.assertTrue(all(x['trace_observed'] for x in results));self.assertEqual(backend.writes,1)
    def test_lost_trace_reply_reconciles_without_resubmit(self):
        backend=FakeBackend();backend.lose_reply=True
        with self.assertRaises(TimeoutError):receive(self.envelope,self.root/'remote',backend,attempts=1)
        self.assertTrue(receive(self.envelope,self.root/'remote',backend,attempts=1)['trace_observed'])
        self.assertEqual(backend.writes,1)
    def test_unknown_trace_never_resubmits(self):
        backend=FakeBackend();backend.visible=False
        for _ in range(2):
            with self.assertRaises(RuntimeError):receive(self.envelope,self.root/'remote',backend,attempts=1)
        self.assertEqual(backend.writes,1)
    def test_mutated_payload_refused(self):
        backend=FakeBackend();receive(self.envelope,self.root/'remote',backend,attempts=1)
        raw=b'changed';e=dict(self.envelope,payload=base64.b64encode(raw).decode(),payload_sha256=hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ValueError):receive(e,self.root/'remote',backend,attempts=1)
        self.assertEqual(backend.writes,1)
    def test_score_retry_writes_once(self):
        backend=FakeBackend();receive(self.envelope,self.root/'remote',backend,attempts=1)
        e=dict(kind='score',trace_id=self.envelope['trace_id'],root_span_id=self.envelope['root_span_id'],passed=True)
        for _ in range(2):self.assertTrue(receive(e,self.root/'remote',backend,attempts=1)['score_observed'])
        self.assertEqual(backend.score_writes,1)
    def test_bad_payload_and_trace_path_refused(self):
        for e in [dict(self.envelope,trace_id='../escape'),dict(self.envelope,payload_sha256='0'*64)]:
            with self.assertRaises(ValueError):receive(e,self.root/'remote',FakeBackend(),attempts=1)
    def test_claim_requires_native_grant_before_api_evidence(self):
        client=Client();calls=[]
        def request(value):
            calls.append(value)
            return dict(id='claim',state='active',revision=1,worktree=str(self.root))
        value=claim_ticket(client,'ticket',str(self.root),['owned'],self.root/'claim',request=request)
        self.assertEqual(calls[0]['action'],'claim');self.assertTrue(calls[0]['legacy_reconciled'])
        self.assertEqual(value['claim']['id'],'claim');self.assertEqual(client.writes,1)
        with self.assertRaises(RuntimeError):claim_ticket(client,'ticket',str(self.root),['owned'],self.root/'claim',request=request)
        self.assertEqual(client.writes,1)
    def test_claim_denial_never_posts_grant(self):
        client=Client()
        def deny(value):raise RuntimeError('existing owner active')
        with self.assertRaises(RuntimeError):claim_ticket(client,'ticket',str(self.root),['owned'],self.root/'claim',request=deny)
        self.assertEqual(client.writes,0)
    def test_resume_requires_exact_source(self):
        client=Client()
        def request(value):return dict(id='claim',state='active',revision=1,worktree='elsewhere')
        with self.assertRaises(ValueError):claim_ticket(client,'ticket',str(self.root),[],self.root/'claim',resume='claim',request=request)
        self.assertEqual(client.writes,0)


if __name__ == '__main__':
    unittest.main()
