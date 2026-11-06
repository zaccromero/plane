"""One fresh-context coding catalog using existing native sessions and ownership handoff."""
import argparse,fcntl,json,os,queue,re,resource,stat,subprocess,sys,threading,time,uuid
from pathlib import Path
DIST=Path(__file__).resolve().parents[1];sys.path[:0]=[str(DIST/'drako_native'),str(DIST/'drako_coding'),str(DIST/'drako_runner'),str(DIST/'drako')]
import fresh_runner as fresh
from common import config,private_json,atomic,need,payload_hash,ticket_context
from agent_lane import load_binding,native_request
from lane import manifest,verify_context
import coding_tool_server as protocol
from coding_common import python_engine
ROOT=Path.home()/'code/.worktrees/drako-claude-config/feat/context-pack-session-start'
WORK=Path('/Users/zaccromero/Documents/Codex/2026-11-04/company-memory-reuse/work')
FILES=['bin/context-for-cwd.py','tests/context-for-cwd.test.py']
TOOLS={'mcp__drako_code__'+n for n in ['ticket_read','read_context','write_file','run_tests','result']}
TASK='Fix normal context refresh for mapped Git repositories whose curated pack is missing or contains no recognized section files: preserve quiet exit0/no output instead of raising ValueError splitting empty text. Hook remains quiet in these cases. Explicit --receipt must continue returning current Git metadata. Preserve all nonempty context/hook behavior, containment, compact1800 bound and all existing tests; add meaningful missing/empty pack regressions using actual Git fixtures. Change only the two admitted existing files. No hook/settings/permissions/curated pack/runtime deployment changes.'
protocol.SCHEMAS['write_file']['properties']['path']['enum']=FILES

def files():
 out={}
 for name in FILES:
  p=ROOT/name;need(p.is_file() and not p.is_symlink() and not p.parent.is_symlink() and p.stat().st_nlink==1 and p.stat().st_size<=32000,'Nonregular/symlink/oversized output');out[name]=fresh.digest(p)
 return out

def load(directory):
 d=Path(directory).resolve(strict=True);j=private_json(d/'job.json');need(d.parent==ROOT/'.drako/runs' and d.name==j['run_id'] and j['root']==str(ROOT) and j['runner_root']==str(DIST),'Wrong coding source/run');need(j['runner_head']==fresh.git(DIST,'rev-parse','HEAD') and j['runner_files']=={p.name:fresh.digest(p) for p in Path(__file__).parent.glob('*.py')},'Coding runner changed');verify_context(private_json(d/'context-manifest.json'));c=config(j['config_path']);need(j['runtime_binding']==fresh.runtime_binding(j['config_path'],c,'claude'),'Runtime config/executable changed');need(j['loader_sha256']==fresh.digest(fresh.LOADER) and j['freshness_sha256']==fresh.digest(fresh.FRESH),'Installed startup loader changed');state=private_json(d/'state.json');need(fresh.git(ROOT,'rev-parse','HEAD')==state.get('delivery_head',j['source_head']),'Source HEAD changed');need(fresh.git(ROOT,'branch','--show-current')==j['branch'],'Publication branch changed')
 current=fresh.fresh(ROOT);expected=dict(j['live_context']);expected['head']=current['head']
 for key in ['receipt','tracked_dirty','tracked_status_sha256']:current.pop(key,None);expected.pop(key,None)
 need(current==expected,'Read-only startup authority/pack changed');changed=set(fresh.git(ROOT,'diff','--name-only','HEAD').splitlines());need(changed<=set(FILES),'Outside coding scope changed')
 return d,j,c

def prepare(cpath,ticket):
 c=config(cpath);need(not fresh.git(ROOT,'status','--porcelain','--untracked-files=no'),'Preserve dirty tracked source');need(fresh.git(ROOT,'branch','--show-current')=='feat/empty-context-refresh','Wrong isolated coding branch');client=load_binding(c['binding']);t=client.get(ticket);r=subprocess.run([c['python'],'-B',c['doctor'],'doctor','--project',str(ROOT),'--engine','claude'],capture_output=True,text=True,timeout=30);need(r.returncode==0,'Native doctor held')
 live=fresh.fresh(ROOT);need(live['project']=='drako-claude-config','Wrong mapped project');rid='run_'+uuid.uuid4().hex;sys.path.insert(0,c['control_lib']);from drako_control.control_plane import RunJournal;from drako_control import tracing
 os.environ['DRAKO_TRACING']='off';journal=RunJournal(ROOT);run={'run_id':rid,'project_id':'drako-claude-config','pod_id':'fresh-native-coding','runtime_id':'claude-native-subscription','task_id':ticket,'correlation_id':'','status':'running','created_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'agent_ids':['claude'],'crew_id':'empty-context-fix','room_ids':[],'slot_ids':[]};journal.create(run);d=journal.runs_dir/rid
 baseline={name:{'sha256':h,'content':(ROOT/name).read_text()} for name,h in files().items()};atomic(d/'baseline.json',baseline);atomic(d/'ticket.json',ticket_context(t));parent=private_json(WORK/'fresh-context-source-claim.json');need(parent['state']=='active' and parent['worktree']==str(ROOT),'Existing source reservation must be active/reconciled')
 assignment={'schema':'drako.coding-handoff.v1','task':TASK,'ticket_id':ticket,'run_id':rid,'root':str(ROOT),'source_head':live['head'],'parent_claim':parent['id'],'allowed_writes':FILES,'acceptance':['quiet normal/hook missing/empty Git pack','explicit receipt preserved','all existing tests and nonempty behavior preserved','actual native edits, scoped tests, trace/eval and PR'],'review_budget':'one initial scoped audit, batched repair, focused tests, actual release gate, one final scoped review','authority':'owner request in chat01a1a9b6; no merge/deploy or permission changes'};atomic(d/'assignment.json',assignment)
 ctx=manifest([d/'baseline.json',d/'ticket.json',d/'assignment.json',ROOT/'bin/context-freshness.py',ROOT/'tests/context-freshness.test.py',fresh.LOADER,fresh.FRESH,*sorted(Path(__file__).parent.glob('*.py'))]);atomic(d/'context-manifest.json',ctx)
 j={'schema':'drako.fresh-native-coding.v1','root':str(ROOT),'run_id':rid,'ticket_id':ticket,'config_path':str(Path(cpath).resolve()),'runner_root':str(DIST),'runner_head':fresh.git(DIST,'rev-parse','HEAD'),'runner_files':{p.name:fresh.digest(p) for p in Path(__file__).parent.glob('*.py')},'source_head':live['head'],'branch':fresh.git(ROOT,'branch','--show-current'),'initial_files':files(),'context_sha256':ctx['sha256'],'live_context':live,'loader_sha256':fresh.digest(fresh.LOADER),'freshness_sha256':fresh.digest(fresh.FRESH),'runtime_binding':fresh.runtime_binding(cpath,c,'claude'),'native_session_id':str(uuid.uuid4()),'parent_claim':parent['id'],'expected_scopes':sorted(parent['scopes']+[str((d/'results').relative_to(ROOT)),str((d/'assignment.json').relative_to(ROOT))])};atomic(d/'job.json',j);atomic(d/'state.json',{'phase':'prepared','native_invocations':0});atomic(d/'mcp.json',{'mcpServers':{'drako_code':{'type':'stdio','command':c['python'],'args':['-B',str(Path(__file__)),'server',str(d)],'env':{'AGENT_TASK_SESSION_CONTEXT':'${AGENT_TASK_SESSION_CONTEXT}'}}}});run['correlation_id']=ctx['sha256'];journal.save(run);tracing.bind_run(d,run,runs_dir=journal.runs_dir,env={'DRAKO_TRACING':'on','DRAKO_TRACE_ENDPOINT':'http://127.0.0.1:1/v1/traces'});print(json.dumps({'run_dir':str(d),'run_id':rid,'receipt':live['receipt']}))

def commands(c,d):
 scratch=d/'test-scratch';scratch.mkdir(mode=0o700,exist_ok=True);allowed=[ROOT/x for x in FILES+['bin/context-freshness.py','tests/context-freshness.test.py']]+[ROOT/'bin',ROOT/'tests',Path(__file__).parent,Path(__file__).parent/'test_empty_contract.py'];systems=['/System','/usr','/opt/homebrew','/Library','/private/etc','/private/var/db','/private/preboot','/dev'];executables=[python_engine(c['python']),Path('/usr/bin/git'),Path('/Library/Developer/CommandLineTools/usr/bin/git'),Path('/usr/bin/xcrun'),Path('/Applications/Xcode.app/Contents/Developer/usr/bin/git')];read=' '.join('(subpath '+json.dumps(p)+')' for p in systems)+' '+ ' '.join('(literal '+json.dumps(str(p))+')' for p in allowed)+' (subpath '+json.dumps(str(scratch))+')';execs=' '.join('(literal '+json.dumps(str(p))+')' for p in executables)
 sb=d/'test.sb';sb.write_text('(version 1)(deny default)(allow process*)(deny process-exec (require-not (require-any '+execs+')))(allow mach-lookup)(allow sysctl-read)(allow file-read*)(deny file-read-data (require-not (require-any '+read+')))(allow file-write* (subpath '+json.dumps(str(scratch))+') (literal "/dev/null"))');sb.chmod(0o600)
 prefix=[c['workload'],'run','/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME='+str(scratch),'TMPDIR='+str(scratch),'LANG=en_US.UTF-8','DRAKO_CODING_ROOT='+str(ROOT),'/usr/bin/sandbox-exec','-f',str(sb),str(python_engine(c['python'])),'-I','-B','-m','unittest','discover']
 return [prefix+['-s',str(Path(__file__).parent),'-p','test_empty_contract.py','-v'],prefix+['-s',str(ROOT/'tests'),'-p','context-for-cwd.test.py','-v']]

def test_outputs(c,d):
 rows=[]
 for index,argv in enumerate(commands(c,d)):
  log=d/'test-scratch'/('test-'+str(time.time_ns())+'-'+str(index)+'.log')
  def limits():resource.setrlimit(resource.RLIMIT_CPU,(20,20));resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
  with log.open('w') as out:r=subprocess.run(argv,cwd=d/'test-scratch',env=dict(os.environ),stdout=out,stderr=subprocess.STDOUT,timeout=90,preexec_fn=limits)
  text=log.read_text();match=re.search(r'Ran (\d+) tests?',text);rows.append({'exit_code':r.returncode,'tests':int(match[1]) if match else 0,'passed':r.returncode==0 and bool(match) and int(match[1])>0 and '\nOK\n' in text and 'skipped' not in text.lower(),'log':str(log),'output':text[-18000:]})
 return rows

class Worker:
 def __init__(self,d):self.directory=d
 def call(self,name,args):
  need(name in protocol.SCHEMAS and isinstance(args,dict),'Unknown coding capability')
  if name=='write_file':need(set(args)=={'path','content'} and args['path'] in FILES and isinstance(args['content'],str) and 0<len(args['content'].encode())<=32000,'Outside write scope/size')
  else:need(args=={},'No arguments admitted')
  d,j,c=load(self.directory);need(private_json(d/'startup-ack.json')['receipt']==j['live_context']['receipt'],'Missing automatically loaded receipt');actor=json.loads(subprocess.check_output([c['session'],'context'],text=True));need(actor['project']==str(ROOT) and actor['actor']['client']=='claude' and actor['active'],'Wrong native actor');results=d/'results';results.mkdir(mode=0o700,exist_ok=True)
  with (results/'worker.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX);path=results/'worker.json'
   if name=='ticket_read' and not path.exists():
    need(files()==j['initial_files'],'Source changed before handoff')
    atomic(d/'receiver.json',actor);deadline=time.monotonic()+25
    while not (d/'offer-ready.json').exists() and time.monotonic()<deadline:time.sleep(.1)
    need((d/'offer-ready.json').exists(),'Exact source handoff not ready');t=native_request({'action':'show','id':j['parent_claim']});need(t['state']=='offered' and t['receiver']==actor['actor'],'Wrong pending receiver');t=native_request({'action':'accept','id':t['id'],'revision':t['revision']});need(t['owner']==actor['actor'] and sorted(t['scopes'])==j['expected_scopes'],'Wrong accepted source scope');atomic(path,{'claim_id':t['id'],'actor':actor['actor'],'files':files(),'writes':0,'tests':0,'read':False})
   need(path.exists(),'Read ticket and accept scoped handoff first');state=private_json(path);t=native_request({'action':'show','id':state['claim_id']});need(t['owner']==state['actor']==actor['actor'] and files()==state['files'],'Native owner/output changed')
   if (results/'report.json').exists():return private_json(results/'report.json')
   need(t['state']=='active','Source claim is not active')
   if name=='ticket_read':return private_json(d/'ticket.json')
   if name=='read_context':state['read']=True;atomic(path,state);return {'task':TASK,'allowed_files':FILES,'baseline':private_json(d/'baseline.json'),'independent_acceptance':(Path(__file__).parent/'test_empty_contract.py').read_text(),'bounds':{'writes':6,'test_attempts':3},'project_authority':'existing project instructions and review budget; no source beyond2 admitted paths'}
   need(state['read'],'Read actual source context before edits/tests')
   if name=='write_file':
    need(state['writes']<6,'Write bound');p=ROOT/args['path'];mode=stat.S_IMODE(p.stat().st_mode);tmp=results/('write_'+uuid.uuid4().hex);tmp.write_text(args['content']);tmp.chmod(mode);os.replace(tmp,p);state['writes']+=1;state['files']=files();atomic(path,state);return {'status':'WRITTEN','path':args['path'],'sha256':state['files'][args['path']]}
   if name=='run_tests':
    need(state['tests']<3,'Test bound');state['tests']+=1;atomic(path,state);before=files();rows=test_outputs(c,d);need(before==files(),'Tests changed source');value={'status':'PASS' if all(x['passed'] for x in rows) else 'FAIL','run_id':j['run_id'],'ticket_id':j['ticket_id'],'claim_id':t['id'],'native_actor':t['owner'],'files':before,'attempt':state['tests'],'results':rows};atomic(results/'check.json',value);return value
   check=private_json(results/'check.json');need(check['status']=='PASS' and check['files']==files() and state['writes']>0,'No actual passing coding output');report={'status':'PASS','run_id':j['run_id'],'ticket_id':j['ticket_id'],'claim_id':t['id'],'native_actor':t['owner'],'files':files(),'writes':state['writes'],'tests':state['tests'],'context_sha256':j['context_sha256'],'check_sha256':payload_hash(check)};atomic(results/'report.json',report);finished=native_request({'action':'finish','id':t['id'],'revision':t['revision'],'receipt':str((results/'report.json').relative_to(ROOT)),'result':'PASS'});atomic(results/'finish.json',{'state':finished['state'],'claim_id':t['id']});return report

def execute(directory):
 d,j,c=load(directory)
 with (d/'runner.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);state=private_json(d/'state.json');need(state=={'phase':'prepared','native_invocations':0},'No unknown coding replay');client=load_binding(c['binding']);need(ticket_context(client.get(j['ticket_id']))==private_json(d/'ticket.json'),'Ticket changed');state.update(phase='launch_started',native_invocations=1);atomic(d/'state.json',state)
  argv=[c['session'],'claude','--print','--output-format','stream-json','--verbose','--mcp-config',str(d/'mcp.json'),'--strict-mcp-config','--tools','','--allowedTools',','.join(sorted(TOOLS)),'--permission-mode','manual','--permission-prompts','none','--no-chrome','--disable-slash-commands','--session-id',j['native_session_id']]
  prompt='Execute this one real coding ticket using only the five drako_code tools. FIRST emit FRESH_CONTEXT=<receipt automatically supplied at startup> as a separate text message before tools; UNKNOWN means stop, never infer from tool answers. Call ticket_read to accept the exact supported ownership handoff, read_context to inspect actual baseline source/contract, then implement the fix and additive meaningful tests with write_file. Run run_tests, repair within given bounds if needed, and call result only after PASS. No other tools/shell/delegation, credentials, settings changes, merge or deployment. Do not claim hypothetical tests passed. Stop after the verified result.'
  q=queue.Queue();ack=False;calls=[];final=False;size=0;offer=False
  with (d/'native-output.jsonl').open('w') as out,(d/'native-stderr.log').open('w') as err:
   p=subprocess.Popen(argv,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,text=True,start_new_session=True)
   def reader():
    for line in p.stdout:q.put(line)
    q.put(None)
   threading.Thread(target=reader,daemon=True).start();p.stdin.write(prompt);p.stdin.close();deadline=time.monotonic()+600
   try:
    while True:
     need(time.monotonic()<deadline,'Native coding timeout; retain claim/source')
     if not offer and (d/'receiver.json').exists():
      env=dict(os.environ,FRESH_ACTION='offer-coding',CODING_RUN_DIR=str(d));r=subprocess.run([c['python'],str(WORK/'fresh-context-source.py')],env=env,cwd=WORK.parent,capture_output=True,text=True,timeout=25);atomic(d/'handoff-host.json',{'exit_code':r.returncode,'output':r.stdout+r.stderr});need(r.returncode==0,'Source handoff held; retain pending receiver');atomic(d/'offer-ready.json',{'claim_id':j['parent_claim']});offer=True
     try:line=q.get(timeout=.1)
     except queue.Empty:continue
     if line is None:break
     out.write(line);out.flush();size+=len(line);need(size<=1048576,'Native output bound')
     try:e=json.loads(line)
     except ValueError:continue
     need(not e.get('permission_denials'),'Native permission denied')
     if e.get('type')=='system' and e.get('subtype')=='init':need(set(e.get('tools',[]))==TOOLS,'Unexpected tool inventory')
     if e.get('type')=='assistant':
      for item in e.get('message',{}).get('content',[]):
       if item.get('type')=='text' and not calls and 'FRESH_CONTEXT=' in item.get('text',''):need('FRESH_CONTEXT='+j['live_context']['receipt'] in item['text'],'Wrong automatic receipt');ack=True;atomic(d/'startup-ack.json',{'receipt':j['live_context']['receipt'],'before_tools':True})
       if item.get('type')=='tool_use':need(ack and item['name'] in TOOLS,'Unacknowledged/outside tool');calls.append(item['name']);need(len(calls)<=20,'Tool bound')
     if e.get('type')=='result':need(not e.get('is_error'),'Native failed');final=True
    code=p.wait(timeout=20)
   finally:
    if p.poll() is None:p.terminate()
    code=p.wait(timeout=20);atomic(d/'native-wait.json',{'exit_code':code,'calls':calls,'ack':ack});state['native_exit_code']=code;atomic(d/'state.json',state)
  need(code==0 and ack and offer and final and set(calls)==TOOLS and (d/'results/report.json').exists(),'Native coding incomplete; preserve output/ownership');state['phase']='executed';atomic(d/'state.json',state);print(json.dumps(state))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True);a=s.add_parser('prepare');a.add_argument('--config',required=True);a.add_argument('--ticket',required=True)
 for n in ['run','server']:a=s.add_parser(n);a.add_argument('directory')
 a=p.parse_args()
 try:
  if a.action=='prepare':prepare(a.config,a.ticket)
  elif a.action=='server':protocol.serve(Worker(a.directory))
  else:execute(a.directory)
 except Exception as error:print(json.dumps({'status':'BLOCKED','error':str(error)[:350]}));raise SystemExit(1)
