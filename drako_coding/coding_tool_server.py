"""Five scoped capabilities; generated code never executes in the server."""
import fcntl,json,os,re,resource,subprocess,sys
from pathlib import Path
from coding_common import ROOT,FILES,TOOLS,atomic,need,private_json,load_job,ticket_context,files,digest,checked,contract,test_commands,test_env,payload_hash
from agent_lane import load_binding,claim_ticket,native_request

SCHEMAS={name:{'type':'object','properties':{},'additionalProperties':False} for name in ['ticket_read','read_context','run_tests','result']}
SCHEMAS['write_file']={'type':'object','properties':{'path':{'type':'string','enum':FILES},'content':{'type':'string','maxLength':32000}},'required':['path','content'],'additionalProperties':False}

class Worker:
 def __init__(self,directory):self.directory=Path(directory)
 def call(self,name,args):
  need(name in SCHEMAS and isinstance(args,dict),'Unknown tool')
  if name=='write_file':need(set(args)=={'path','content'} and args['path'] in FILES and isinstance(args['content'],str) and 0<len(args['content'].encode())<=32000,'Outside file scope or size bound')
  else:need(args=={},'No parameters accepted')
  d,j,c=load_job(self.directory);client=load_binding(c['binding'])
  need(ticket_context(client.get(j['ticket_id']))==private_json(d/'ticket-context.json'),'Ticket changed')
  need(private_json(d/'capabilities-verified.json')['tools']==sorted(TOOLS),'Native tool inventory not verified')
  results=d/'results';results.mkdir(mode=0o700,exist_ok=True)
  with open(results/'worker.lock','a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   state_path=results/'worker-state.json'
   if name=='ticket_read' and not state_path.exists():
    need(not (results/'ownership/claim.json').exists(),'Uncertain claim; reconcile instead of retry')
    scopes=FILES+[str(results.relative_to(ROOT))]
    claim=claim_ticket(client,j['ticket_id'],str(ROOT),scopes,results/'ownership')['claim']
    state={'claim_id':claim['id'],'actor':claim['owner'],'files':{},'writes':0,'tests':0,'read':False}
    atomic(state_path,state)
   need(state_path.exists(),'Read and claim ticket first');state=private_json(state_path)
   t=native_request({'action':'show','id':state['claim_id']})
   actor=json.loads(subprocess.check_output([c['session'],'context'],text=True))
   need(t['owner']==state['actor']==actor['actor'] and actor['project']==str(ROOT),'Native actor changed')
   if (results/'report.json').exists():
    need((results/'finish.json').exists() and t['state']=='finish_pending','Unsealed result; reconcile')
    return private_json(results/'report.json')
   need(t['state']=='active','Claim no longer active')
   need(files()==state['files'],'Output drift; reconcile')
   if name=='ticket_read':return ticket_context(client.get(j['ticket_id']))
   if name=='read_context':
    state['read']=True;atomic(state_path,state)
    return {'contract':contract(),'allowed_files':FILES,'independent_test_source':(ROOT/'drako_coding/test_status_contract.py').read_text(),'bounds':{'writes':6,'test_attempts':3}}
   need(state['read'],'Read immutable coding contract before writing/testing')
   if name=='write_file':
    need(state['writes']<6,'Write budget exhausted')
    p=ROOT/args['path'];p.parent.mkdir(mode=0o700,exist_ok=True)
    need(not p.is_symlink() and not p.parent.is_symlink(),'Symlink output refused')
    intent=results/'write-intent.json';need(not intent.exists(),'Uncertain write; reconcile')
    atomic(intent,{'path':args['path'],'before':state['files'].get(args['path'])})
    temporary=p.with_suffix('.new');fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(args['content']);f.flush();os.fsync(f.fileno())
    os.replace(temporary,p);state['files']=files();state['writes']+=1;atomic(state_path,state);intent.unlink()
    return {'status':'WRITTEN','path':args['path'],'sha256':state['files'][args['path']]}
   if name=='run_tests':
    need(set(state['files'])==set(FILES),'Both approved files required')
    if (results/'check.json').exists():
     old=private_json(results/'check.json')
     if old['passed'] and old['files']==files():return old
    need(state['tests']<3,'Test budget exhausted')
    intent=results/'test-intent.json';need(not intent.exists(),'Test outcome uncertain; reconcile')
    state['tests']+=1;atomic(state_path,state);atomic(intent,{'attempt':state['tests'],'files':files()})
    outputs=[];passed=True
    for index,argv in enumerate(test_commands(c,d)):
     def limits():
      resource.setrlimit(resource.RLIMIT_CPU,(20,20));resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
     log=d/'test-scratch'/('output-'+str(state['tests'])+'-'+str(index)+'.log')
     with open(log,'w') as out:
      r=subprocess.run(argv,cwd=d/'test-scratch',env=test_env(d),stdout=out,stderr=subprocess.STDOUT,text=True,timeout=45,preexec_fn=limits)
     output=log.read_text()[-24000:];outputs.append({'exit_code':r.returncode,'output':output})
     match=re.search(r'Ran (\d+) tests?',output)
     passed=passed and r.returncode==0 and match is not None and int(match[1])>=1 and '\nOK\n' in output and 'skipped' not in output.lower()
    need(files()==state['files'],'Tests mutated source')
    value={'run_id':j['run_id'],'ticket_id':j['ticket_id'],'passed':passed,'files':files(),'test_attempt':state['tests'],'results':outputs,'claim_id':t['id'],'native_actor':t['owner'],'python':c['python']}
    atomic(results/'check.json',value);intent.unlink();return value
   value=checked(d,j)
   report={'status':'PASS','run_id':j['run_id'],'ticket_id':j['ticket_id'],'claim_id':t['id'],'native_actor':t['owner'],'context_sha256':j['context_sha256'],'check_sha256':payload_hash(value),'files':files()}
   receipt=results/'report.json';atomic(receipt,report)
   finished=native_request({'action':'finish','id':t['id'],'revision':t['revision'],'receipt':str(receipt.relative_to(ROOT)),'result':'PASS'})
   atomic(results/'finish.json',{'state':finished['state'],'claim_id':finished['id']});return report

def serve(worker):
 for line in sys.stdin:
  request={}
  try:
   need(len(line)<=100000,'Oversized request');request=json.loads(line)
   if 'id' not in request:continue
   method=request.get('method')
   if method=='initialize':value={'protocolVersion':request.get('params',{}).get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'drako-code','version':'1.0'}}
   elif method=='ping':value={}
   elif method=='tools/list':value={'tools':[{'name':n,'description':{'ticket_read':'Read this ticket and claim exact coding scope.','read_context':'Read immutable task and independent tests.','write_file':'Write one of the two approved code files only.','run_tests':'Run fixed tests with network and unrelated-file access denied.','result':'Seal passing scoped delivery; stop afterwards.'}[n],'inputSchema':s} for n,s in SCHEMAS.items()]}
   elif method=='tools/call':
    p=request['params'];value={'content':[{'type':'text','text':json.dumps(worker.call(p['name'],p.get('arguments',{})))}],'isError':False}
   else:raise RuntimeError('Unsupported method')
   response={'jsonrpc':'2.0','id':request['id'],'result':value}
  except Exception as e:response={'jsonrpc':'2.0','id':request.get('id'),'error':{'code':-32602,'message':str(e)[:300]}}
  print(json.dumps(response),flush=True)
if __name__=='__main__':serve(Worker(sys.argv[1]))
