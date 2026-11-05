"""Explicit native-agent entry point. Ticket text is data, never a command."""
import argparse
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

from workflow import ProjectPlane, atomic, post_evidence


def load_binding(path):
    path=Path(path)
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError('Binding must be a private regular file')
    data=json.loads(path.read_text())
    token=Path(data['token_file'])
    if token.is_symlink() or stat.S_IMODE(token.stat().st_mode) & 0o077:
        raise ValueError('Token must be a private regular file')
    return ProjectPlane(data['base_url'], token.read_text().strip(), data['workspace'], data['project_id'])


def native_request(request):
    if not os.environ.get('AGENT_TASK_SESSION_CONTEXT'):
        raise RuntimeError('No registered native executor; acquire supported supervisor/session route')
    raw=subprocess.check_output([str(Path.home()/'.local/bin/agent-session'),'request',json.dumps(request)],text=True)
    packet=json.loads(raw)
    if not isinstance(packet.get('task'),dict):
        raise RuntimeError('Native ownership request not confirmed')
    return packet['task']


def claim_ticket(client, ticket, source_project, scopes, state_dir, resume=None, request=native_request):
    import fcntl
    client.get(ticket)
    root=Path(state_dir);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(root/'claim.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        receipt=root/'claim.json'
        if receipt.exists():
            value=json.loads(receipt.read_text())
            if value['ticket_id']!=ticket or value['source_project']!=str(source_project):
                raise ValueError('Claim receipt belongs to another lane')
            task=request({'action':'show','id':value['claim']['id']})
            if task['state']!='active':
                raise RuntimeError('Claim is no longer active')
            # A prior process is not adopted merely because its receipt exists.
            if resume is None:
                raise RuntimeError('Existing claim requires explicit registered owner resumption')
            if resume != value['claim']['id']:
                raise ValueError('Cannot resume a different claim into this lane')
        elif (root/'claim-uncertain.json').exists():
            raise RuntimeError('Native claim result unknown; reconcile board before retry')
        if resume:
            task=request({'action':'show','id':resume})
            if task['worktree']!=str(source_project):
                raise ValueError('Ownership source mismatch')
            task=request({'action':'resume_owner','id':resume,'revision':task['revision']})
        else:
            atomic(root/'claim-uncertain.json',{'ticket_id':ticket,'source_project':str(source_project)})
            task=request({'action':'claim','project':str(source_project),'scopes':scopes,
                'task_key':'PLANE_'+ticket.replace('-',''),'legacy_reconciled':True})
        value={'ticket_id':ticket,'project_id':client.project,'source_project':str(source_project),'claim':task}
        atomic(receipt,value)
        marker='drako-claim:'+task['id']
        comments=client.comments(ticket)
        if not any(marker in row.get('comment_html','') for row in comments):
            intent=root/'claim-comment.json'
            if intent.exists():
                raise RuntimeError('Claim retained; API comment outcome uncertain, query before retry')
            atomic(intent,{'marker':marker,'status':'submission_started'})
            client.comment(ticket,'<p>Execution ownership acquired: '+marker+'. Source and scope remain governed by the native Drako controller. This is not completion.</p>')
            if not any(marker in row.get('comment_html','') for row in client.comments(ticket)):
                raise RuntimeError('Claim retained; API claim comment unconfirmed')
        return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding',required=True)
    commands=parser.add_subparsers(dest='command',required=True)
    read=commands.add_parser('read');read.add_argument('ticket')
    claim=commands.add_parser('claim');claim.add_argument('ticket');claim.add_argument('--source-project',required=True)
    claim.add_argument('--scope',action='append',default=[]);claim.add_argument('--state-dir',required=True);claim.add_argument('--resume')
    evidence=commands.add_parser('evidence');evidence.add_argument('--evidence',required=True);evidence.add_argument('--expected',required=True)
    evidence.add_argument('--context',required=True);evidence.add_argument('--state-dir',required=True)
    args=parser.parse_args();client=load_binding(args.binding)
    if args.command=='read':
        ticket=client.get(args.ticket)
        result={key:ticket.get(key) for key in ['id','name','description_html','project','state','sequence_id']}
    elif args.command=='claim':
        value=claim_ticket(client,args.ticket,str(Path(args.source_project).resolve(strict=True)),args.scope,args.state_dir,args.resume)
        result={'ticket_id':value['ticket_id'],'claim_id':value['claim']['id'],'state':value['claim']['state']}
    else:
        result=post_evidence(client,json.loads(Path(args.evidence).read_text()),json.loads(Path(args.expected).read_text()),
            json.loads(Path(args.context).read_text()),args.state_dir)
    print(json.dumps(result))


if __name__=='__main__':
    main()
