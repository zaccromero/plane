"""Run-local stdio MCP server: three fixed capabilities, no general execution."""
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

from common import ROOT, atomic, need, load_job, private_json, ticket_context, check_argv, check_result, payload_hash
from agent_lane import load_binding, claim_ticket, native_request


class Worker:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.read = False

    def call(self, name, arguments):
        need(name in {'ticket_read', 'approved_check', 'result'} and arguments == {}, 'Unknown capability or extra parameters')
        d, job, c = load_job(self.directory)
        client = load_binding(c['binding'])
        ticket = client.get(job['ticket_id'])
        need(ticket_context(ticket) == private_json(d / 'ticket-context.json'), 'Ticket contract changed')
        if name == 'ticket_read':
            self.read = True
            return dict(ticket_context(ticket), catalog=job['catalog'], context_sha256=job['context_sha256'])
        need(self.read, 'Read the bound ticket before execution')
        permit = private_json(d / 'capabilities-verified.json')
        need(permit['tools'] == sorted(job['tools']) and permit['run_id'] == job['run_id'], 'Native tool inventory not verified')
        results = d / 'results'
        results.mkdir(mode=0o700, exist_ok=True)
        with open(results / 'worker.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            receipt = results / 'report.json'
            if receipt.exists():
                need((results / 'finish.json').exists(), 'Receipt not sealed; host reconciliation required')
                need(private_json(results / 'finish.json')['state'] == 'finish_pending', 'Unsealed claim')
                return private_json(receipt)
            if name == 'approved_check':
                if (results / 'check.json').exists():
                    value = check_result(d, job)
                    t = native_request({'action':'show', 'id':value['claim_id']})
                    actor = json.loads(subprocess.check_output([c['session'], 'context'], text=True))
                    need(t['state'] == 'active' and t['owner'] == value['native_actor'] == actor['actor'], 'Cached check actor changed')
                    return dict(status='PASS', claim_id=value['claim_id'], tests_run=1, skipped=0, cached=True)
                # A server restart cannot adopt or repeat an uncertain claim/execution.
                need(not (results / 'ownership/claim.json').exists(), 'Existing claim requires host reconciliation')
                actor = json.loads(subprocess.check_output([c['session'], 'context'], text=True))
                need(actor['active'] and actor['actor']['client'] == 'claude' and actor['project'] == str(ROOT), 'Wrong native actor')
                claim = claim_ticket(client, job['ticket_id'], str(ROOT),
                    [str(results.relative_to(ROOT))], results / 'ownership')
                need(not (results / 'check-intent.json').exists(), 'Execution outcome uncertain; no replay')
                argv = check_argv(c)
                atomic(results / 'check-intent.json', dict(run_id=job['run_id'], argv_sha256=payload_hash(argv), status='started'))
                env = dict(os.environ, DRAKO_CONTROL_LIB=c['control_lib'], PYTHONDONTWRITEBYTECODE='1')
                env.pop('PYTHONPATH', None); env.pop('PYTHONHOME', None)
                r = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, timeout=45)
                value = dict(run_id=job['run_id'], ticket_id=job['ticket_id'], claim_id=claim['claim']['id'],
                    native_actor=claim['claim']['owner'], python=c['python'], exit_code=r.returncode,
                    output=r.stdout+r.stderr, argv_sha256=payload_hash(argv))
                atomic(results / 'check.json', value)
                check_result(d, job)
                return dict(status='PASS', claim_id=value['claim_id'], tests_run=1, skipped=0, python=c['python'])
            value = check_result(d, job)
            t = native_request({'action':'show', 'id':value['claim_id']})
            need(t['state'] == 'active' and t['owner'] == value['native_actor'], 'Claim actor/state changed')
            report = dict(status='PASS', run_id=job['run_id'], ticket_id=job['ticket_id'], claim_id=t['id'],
                context_sha256=job['context_sha256'], check_sha256=payload_hash(value), native_actor=t['owner'])
            atomic(receipt, report)
            t = native_request(dict(action='finish', id=t['id'], revision=t['revision'],
                receipt=str(receipt.relative_to(ROOT)), result='PASS'))
            atomic(results / 'finish.json', dict(claim_id=t['id'], revision=t['revision'], state=t['state']))
            return report


def serve(worker, incoming=sys.stdin, outgoing=sys.stdout):
    for line in incoming:
        response = None
        try:
            need(len(line) <= 65536, 'Oversized MCP request')
            request = json.loads(line)
            if 'id' not in request:
                continue
            method = request.get('method')
            if method == 'initialize':
                result = dict(protocolVersion=request.get('params', {}).get('protocolVersion', '2024-11-05'),
                    capabilities={'tools':{}}, serverInfo={'name':'drako-lane', 'version':'1.0.0'})
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools':[dict(name=name, description=description,
                    inputSchema={'type':'object','properties':{},'additionalProperties':False}) for name,description in [
                        ('ticket_read','Read this one bound Plane ticket and approved catalog.'),
                        ('approved_check','Acquire your native scope and run the one approved read-only Python check.'),
                        ('result','Return the verified check receipt and seal your scoped delivery for owner review.')]]}
            elif method == 'tools/call':
                params = request.get('params', {})
                value = worker.call(params.get('name'), params.get('arguments', {}))
                result = {'content':[{'type':'text','text':json.dumps(value)}], 'isError':False}
            else:
                raise ValueError('Unsupported MCP method')
            response = {'jsonrpc':'2.0','id':request['id'],'result':result}
        except Exception as error:
            response = {'jsonrpc':'2.0','id':request.get('id') if 'request' in locals() else None,
                'error':{'code':-32602,'message':str(error)[:300]}}
        if response is not None:
            outgoing.write(json.dumps(response)+'\n');outgoing.flush()


if __name__ == '__main__':
    serve(Worker(sys.argv[1]))
