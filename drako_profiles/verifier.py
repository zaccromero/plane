"""Automatic fail-closed verifier for the one trusted pure-elevation profile."""
import hashlib,io,json,os,shutil,subprocess,tarfile
from pathlib import Path

def host_profile(snapshot,scratch,node):
 reads=[str(snapshot),str(scratch),str(Path(node).resolve().parent.parent),'/System','/usr','/opt/homebrew','/Library','/private/etc','/private/var/db','/private/preboot','/dev']
 allow=' '.join('(subpath '+json.dumps(p)+')' for p in reads)
 literals={str(p) for v in [snapshot,scratch,Path(node).resolve()] for p in v.parents}
 allow += ' '+ ' '.join('(literal '+json.dumps(p)+')' for p in sorted(literals))
 return '(version 1)(deny default)(allow process*)(allow mach-lookup)(allow sysctl-read)(allow file-read*)(deny file-read-data (require-not (require-any '+allow+')))(allow file-write* (subpath '+json.dumps(str(scratch))+') (subpath '+json.dumps(str(snapshot/'packages/elevation/dist'))+') (literal "/dev/null"))'

def verify(d,j,c,root):
 import adapter as a
 check=a.common.checked(d,j);hashes=a.common.files();target=d/'review.json'
 if target.exists():
  old=a.private_json(target);a.need(old['files']==hashes and old['check_sha256']==a.payload_hash(check) and old['context_sha256']==j['context_sha256'],'Verifier receipt stale');return old
 baseline=a.private_json(d/'baseline-files.json')
 a.need(baseline[a.FILES[1]]['content'] in (root/a.FILES[1]).read_text(),'Original tests must be retained verbatim')
 changed=a.git(root,'diff','--name-only').splitlines();a.need(set(changed)==set(a.FILES),'Output scope mismatch')
 snapshot=d/'verification-snapshot';scratch=d/'verification-scratch';scratch.mkdir(mode=0o700,exist_ok=True)
 a.need(not snapshot.exists(),'Uncertain verification snapshot; reconcile logs instead of replay')
 snapshot.mkdir(mode=0o700)
 archive=subprocess.check_output(['git','archive',j['source_head']],cwd=root)
 tarfile.open(fileobj=io.BytesIO(archive)).extractall(snapshot,filter='data')
 shutil.copytree(root/'node_modules',snapshot/'node_modules',symlinks=True)
 for n in a.FILES:(snapshot/n).write_bytes((root/n).read_bytes())
 # The independent baseline copy and acceptance source are never supplied by the worker.
 (scratch/'profile.ts').write_bytes((root/a.FILES[0]).read_bytes())
 (scratch/'original.test.ts').write_text(baseline[a.FILES[1]]['content'].replace('../src/profile.js','./profile.ts'))
 (scratch/'acceptance.test.mjs').write_bytes(Path(__file__).with_name('acceptance.test.mjs').read_bytes())
 (scratch/'source-policy.mjs').write_bytes(Path(__file__).with_name('source-policy.mjs').read_bytes())
 sb=host_profile(snapshot,scratch,c['node'])
 env={'PATH':str(Path(c['node']).parent)+':/usr/bin:/bin','HOME':str(scratch),'TMPDIR':str(scratch),'LANG':'en_US.UTF-8','DRAKO_TARGET_SOURCE':str(scratch/'profile.ts')}
 node=c['node'];npm=str(Path(node).with_name('npm'))
 commands=[('source-policy',[node,str(scratch/'source-policy.mjs'),str(snapshot/a.FILES[0]),str(snapshot/'node_modules/typescript/lib/typescript.js')]),('independent',[node,'--experimental-strip-types','--experimental-test-isolation=none','--test',str(scratch/'acceptance.test.mjs'),str(scratch/'original.test.ts')]),('typecheck',[npm,'run','typecheck','-w','packages/elevation']),('build',[npm,'run','build','-w','packages/elevation']),('canonical-tests',[npm,'test','-w','packages/elevation']),('lint',[npm,'run','lint'])]
 receipts=[]
 for name,argv in commands:
  logs=d/'verification-logs';logs.mkdir(mode=0o700,exist_ok=True)
  log=logs/(name+'.log')
  with open(log,'w') as out:
   r=subprocess.run([c['workload'],'run','/usr/bin/env','-i',*[k+'='+v for k,v in env.items()],'/usr/bin/sandbox-exec','-p',sb,*argv],cwd=snapshot,env=dict(os.environ),stdout=out,stderr=subprocess.STDOUT,timeout=180)
  text=log.read_text();ok=r.returncode==0
  if name in ['independent','canonical-tests']:ok=ok and a.tap_pass(text,r.returncode)
  receipts.append({'gate':name,'exit_code':r.returncode,'status':'PASS' if ok else 'FAIL','log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
  a.atomic(d/'automatic-verification-progress.json',receipts)
  a.need(ok,'Automatic verification failed: '+name+'; see '+str(log))
 a.need(a.common.files()==hashes,'Outputs changed during verification')
 value={'p0':0,'p1':0,'full_component_gate':True,'files':hashes,'check_sha256':a.payload_hash(check),'context_sha256':j['context_sha256'],'source_repo':a.REPO,'source_head':j['source_head'],'runner_head':j['runner_head'],'kind':'automatic-profile-policy-and-independent-verification','owner_accepted':False,'gates':receipts,'scope':'one pure-function profile; no general semantic/security certification'}
 a.atomic(target,value);return value
