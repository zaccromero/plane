"""Independent verification while the native writer still owns an active claim."""
import fcntl,json,shutil,subprocess
from pathlib import Path
import adapter as base
from verifier import verify as map_verify,host_profile

MAX_ATTEMPTS=3
KNOWN_FAILURES=('Original tests must be retained verbatim','Output scope mismatch','Automatic verification failed:')

def qualification_verify(attempt,j,c,root):
 check=base.common.checked(attempt,j);scratch=attempt/'scratch';scratch.mkdir(mode=0o700)
 baseline=base.private_json(attempt/'baseline-files.json')
 base.need(baseline[base.FILES[1]]['content'] in (root/base.FILES[1]).read_text(),'Original tests must be retained verbatim')
 base.need(set(base.git(root,'diff','--name-only').splitlines())==set(base.FILES),'Output scope mismatch')
 for name,value in [('profile.ts',(root/base.FILES[0]).read_text()),('original.test.ts',baseline[base.FILES[1]]['content']),('worker.test.ts',(root/base.FILES[1]).read_text())]: (scratch/name).write_text(value)
 for name in ['source-policy.mjs','acceptance.test.mjs']:shutil.copyfile(base.DISTRIBUTION/'drako_profiles'/name,scratch/name)
 # Only trusted TypeScript compiler data is present in this isolated dependency snapshot.
 snapshot=attempt/'dependencies';snapshot.mkdir(mode=0o700);shutil.copytree(root/'node_modules/typescript',snapshot/'node_modules/typescript')
 sb=host_profile(snapshot,scratch,c['node'])
 env={'PATH':str(Path(c['node']).parent)+':/usr/bin:/bin','HOME':str(scratch),'TMPDIR':str(scratch),'DRAKO_TARGET_SOURCE':str(scratch/'profile.ts')}
 commands=[('source-policy',[c['node'],str(scratch/'source-policy.mjs'),str(scratch/'profile.ts'),str(snapshot/'node_modules/typescript/lib/typescript.js')]),('independent-and-original',[c['node'],'--experimental-strip-types','--experimental-test-isolation=none','--test',str(scratch/'acceptance.test.mjs'),str(scratch/'original.test.ts'),str(scratch/'worker.test.ts')])]
 gates=[]
 for name,argv in commands:
  log=attempt/(name+'.log')
  with log.open('w') as out:r=subprocess.run(['/usr/bin/env','-i',*[k+'='+v for k,v in env.items()],'/usr/bin/sandbox-exec','-p',sb,*argv],cwd=scratch,stdout=out,stderr=subprocess.STDOUT,timeout=90)
  text=log.read_text();ok=r.returncode==0 and (name=='source-policy' or base.tap_pass(text,r.returncode))
  gates.append({'gate':name,'status':'PASS' if ok else 'FAIL','exit_code':r.returncode,'log':str(log),'sha256':base.common.digest(log)})
  base.atomic(attempt/'automatic-verification-progress.json',gates)
  base.need(ok,'Automatic verification failed: '+name)
 return {'p0':0,'p1':0,'full_component_gate':True,'files':base.common.files(),'check_sha256':base.payload_hash(check),'context_sha256':j['context_sha256'],'runner_head':j['runner_head'],'gates':gates,'kind':'real isolated qualification; not production map CI','owner_accepted':False}

class RecoveryWorker(base.ProjectWorker):
 def call(self,name,args):
  if name!='result':
   value=super().call(name,args)
   if name=='read_context':
    value['independent_verifier_rules']={'source_policy':(base.DISTRIBUTION/'drako_profiles/source-policy.mjs').read_text(),'diff':'Both permitted files must differ from baseline; retain all original test text','result':'result runs independent host verification BEFORE sealing. REPAIR_REQUIRED is a real rejected candidate: repair only permitted files, rerun run_tests, then call result again. Stop only on status PASS. No ownership approval is needed for this same active owner.','bounds':'Original six-write/three-test limits persist; at most three host verification attempts. Unknown/infrastructure failure stops; no relaunch or permission changes.'}
   return value
  base.need(args=={},'No result arguments accepted')
  # Reuse authenticated actor, exact ticket/context/inventory, active-state and output-drift checks.
  super().call('ticket_read',{})
  d,j,c=base.load_job(self.directory)
  if (d/'results/report.json').exists():return super().call('result',{})
  with open(d/'preseal.lock','a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   check=base.common.checked(d,j);worker=base.private_json(d/'results/worker-state.json')
   claim=base.native_request({'action':'show','id':worker['claim_id']})
   base.need(claim['state']=='active' and claim['owner']==worker['actor'],'Exact active native owner required')
   history_path=d/'preseal-history.json';history=base.private_json(history_path) if history_path.exists() else []
   intent=d/'preseal-intent.json';base.need(not intent.exists(),'Uncertain independent verification; reconcile; no automatic replay')
   hashes=base.common.files();check_hash=base.payload_hash(check)
   if history and history[-1]['files']==hashes and history[-1]['check_sha256']==check_hash:
    base.need(history[-1]['status']=='FAIL','Unexpected completed verification state')
    return {'status':'REPAIR_REQUIRED','failure':history[-1],'remaining_host_attempts':MAX_ATTEMPTS-len(history),'message':'Output unchanged since rejection. Repair within original write/test limits, then rerun tests. Do not stop or ask for ownership approval.'}
   base.need(len(history)<MAX_ATTEMPTS,'Independent verification budget exhausted; retain active claim and escalate')
   slot=d/'preseal-attempts'/str(len(history)+1);base.need(not slot.exists(),'Uncertain attempt directory; reconcile')
   slot.mkdir(parents=True,mode=0o700);(slot/'results').mkdir(mode=0o700)
   base.atomic(slot/'results/check.json',check);base.atomic(slot/'baseline-files.json',base.private_json(d/'baseline-files.json'))
   base.atomic(intent,{'attempt':len(history)+1,'files':hashes,'check_sha256':check_hash,'claim_id':claim['id']})
   try:
    verify=qualification_verify if j.get('qualification') else map_verify
    review=verify(slot,j,c,base.ROOT)
   except RuntimeError as error:
    if not any(str(error).startswith(s) for s in KNOWN_FAILURES):raise
    base.need(base.common.files()==hashes,'Outputs changed during failed verification')
    after=base.native_request({'action':'show','id':claim['id']})
    base.need(after['state']=='active' and after['owner']==claim['owner'],'Owner changed during verification')
    progress=base.private_json(slot/'automatic-verification-progress.json') if (slot/'automatic-verification-progress.json').exists() else []
    details=[{'gate':g['gate'],'output':Path(g['log']).read_text()[-3000:]} for g in progress if g['status']=='FAIL']
    failed={'attempt':len(history)+1,'status':'FAIL','reason':str(error),'details':details,'files':hashes,'check_sha256':check_hash,'claim_id':claim['id'],'claim_state_after':'active','actor':claim['owner'],'sealed':False}
    history.append(failed);base.atomic(history_path,history);base.atomic(slot/'outcome.json',failed);intent.unlink()
    return {'status':'REPAIR_REQUIRED','failure':failed,'remaining_host_attempts':MAX_ATTEMPTS-len(history),'message':'Independent verification rejected this candidate. Same active claim is retained. Repair within remaining original limits, rerun run_tests, call result again; do not stop on REPAIR_REQUIRED.'}
   base.need(review['p0']==0 and review['p1']==0 and review['full_component_gate'] is True and review['files']==hashes and review['check_sha256']==check_hash and review['context_sha256']==j['context_sha256'],'Independent review binding mismatch')
   base.need(base.common.files()==hashes,'Output drift after independent verification')
   passed={'attempt':len(history)+1,'status':'PASS','files':hashes,'check_sha256':check_hash,'claim_id':claim['id'],'actor':claim['owner'],'claim_state_before_seal':'active'}
   history.append(passed);base.atomic(history_path,history);base.atomic(slot/'outcome.json',passed);base.atomic(d/'review.json',review);intent.unlink()
  # Only this path may call the existing controller finish; no owner_accept/unlock operation exists here.
  return super().call('result',{})
