"""Pinned coding inputs and a fixed two-file output scope."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'drako_runner'),str(ROOT/'drako')]
from common import atomic,need,private_json,config,fingerprint,ticket_context,payload_hash
from lane import verify_context
TOOLS={'mcp__drako_code__'+name for name in ['ticket_read','read_context','write_file','run_tests','result']}
FILES=['drako_status/status.py','drako_status/test_status.py']
CATALOG='two-file-run-status'

def contract():
 return json.loads((ROOT/'drako_coding/contract.json').read_text())

def exact_scopes(actual,expected):
 return len(actual)==len(expected) and set(actual)==set(expected)

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def files():
 values={}
 for name in FILES:
  p=ROOT/name
  need(not p.is_symlink() and not p.parent.is_symlink(),'Symlink output refused')
  if p.exists():need(p.is_file() and p.stat().st_nlink==1,'Nonregular output refused');values[name]=digest(p)
 return values

def load_job(directory):
 d=Path(directory).resolve(strict=True);need(d.parent==(ROOT/'.drako/runs').resolve(),'Wrong run directory')
 j=private_json(d/'job.json');need(j['project_root']==str(ROOT) and j['catalog']==CATALOG and j['run_id']==d.name,'Wrong job')
 c=config(j['config_path'])
 for key,value in j['executables'].items():need(fingerprint(c[key])==value,'Runtime changed: '+key)
 verify_context(private_json(d/'context-manifest.json'))
 state=private_json(d/'state.json')
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 if head!=state.get('delivery_head',j['source_head']):
  intent=private_json(d/'commit-intent.json')
  need(not state.get('delivery_head') and intent['parent']==j['source_head'] and intent['files']==files(),'Unrecognized commit outcome')
  def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
  need(git('rev-parse','HEAD^')==j['source_head'] and git('log','-1','--format=%s')==intent['message'],'Wrong commit identity')
  need(set(git('diff','--name-only',j['source_head'],head).splitlines())==set(FILES),'Commit exceeds scope')
  state['delivery_head']=head;state['commit_reconciled']=True;atomic(d/'state.json',state)
 need(head==state.get('delivery_head',j['source_head']),'Unexpected source revision')
 return d,j,c

def checked(d,j):
 value=private_json(d/'results/check.json')
 need(value['run_id']==j['run_id'] and value['ticket_id']==j['ticket_id'] and value['passed'] is True,'Tests not passed')
 need(value['files']==files() and set(value['files'])==set(FILES),'Output changed after tests')
 return value

def python_engine(python):
 return Path(python).resolve().parents[1]/'Resources/Python.app/Contents/MacOS/Python'

def profile(python,scratch):
 # Read metadata for runtime traversal; file contents only from system/runtime and this checkout.
 reads=['/System','/usr','/opt/homebrew','/Library','/private/etc','/private/var/db','/private/preboot','/dev',str(ROOT)]
 allow=' '.join('(subpath '+json.dumps(p)+')' for p in reads)
 return ('(version 1)(deny default)(allow process*)(deny process-fork)'
  '(deny process-exec (require-not (literal '+json.dumps(str(python_engine(python)))+')))'
  '(allow mach-lookup)(allow sysctl-read)(allow file-read*)'
  '(deny file-read-data (require-not (require-any (literal "/") (literal "/opt") '+allow+')))'
  '(allow file-write* (subpath '+json.dumps(str(scratch))+') (literal "/dev/null"))')

def test_commands(c,d):
 scratch=d/'test-scratch';scratch.mkdir(mode=0o700,exist_ok=True)
 sb=d/'test.sb';sb.write_text(profile(c['python'],scratch));sb.chmod(0o600)
 prefix=[c['workload'],'run','/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME='+str(scratch),'TMPDIR='+str(scratch),'LANG=en_US.UTF-8','/usr/bin/sandbox-exec','-f',str(sb),str(python_engine(c['python'])),'-I','-B','-m','unittest','discover']
 return [prefix+['-s',str(ROOT/'drako_coding'),'-p','test_status_contract.py','-v'],prefix+['-s',str(ROOT/'drako_status'),'-p','test_status.py','-v']]

def test_env(d):
 # The trusted workload guard keeps its real host context; env -i clears it before generated code.
 return dict(os.environ)
