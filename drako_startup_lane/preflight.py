"""Confined, read-only validation of the existing project startup receipt."""
import hashlib,json
from pathlib import Path

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def need(ok,message):
 if not ok:raise ValueError(message)
def regular(path,roots):
 p=Path(path);need(p.is_absolute() and not p.is_symlink() and p.is_file(),'Missing/non-regular context source')
 r=p.resolve(strict=True);need(any(r.is_relative_to(Path(root).resolve()) for root in roots),'Context source outside admitted roots')
 return r

def verify(pack,project,roots):
 pack=Path(pack);need(not pack.is_symlink(),'Symlink pack refused');receipt=regular(pack/'STARTUP_RECEIPT.json',roots);r=json.loads(receipt.read_text())
 need(r.get('schema')=='drako.project-startup.v1' and r.get('project')==project,'Startup project/schema mismatch')
 rows=r.get('sources');need(isinstance(rows,list) and 1<=len(rows)<=32,'Startup source bounds')
 need(hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()==r.get('manifest_sha256'),'Startup manifest digest mismatch')
 need(r.get('version')=='drako-startup-v1-'+r['manifest_sha256'][:12],'Startup version mismatch')
 seen=set()
 for row in rows:
  p=regular(row['path'],roots);need(str(p) not in seen,'Duplicate startup source');seen.add(str(p));need(digest(p)==row['sha256'],'Startup source missing or changed')
 state=regular(pack/'STARTUP_STATE.md',roots);startup=regular(pack/'STARTUP.md',roots)
 need(str(state) in seen,'Current state is not bound by receipt');need(digest(startup)==r.get('startup_sha256'),'Startup payload changed')
 text=startup.read_text();need(r['version'] in text and len(text)+len('Project context: '+project+' (local drako-context; repository authority wins).\n')<=1800,'Startup receipt truncated or absent')
 return {'schema':'drako.startup-preflight.v1','project':project,'startup_version':r['version'],'startup_receipt_sha256':digest(receipt),'manifest_sha256':r['manifest_sha256'],'startup_sha256':r['startup_sha256'],'source_count':len(rows),'observed_at':r['observed_at'],'state_sha256':digest(state),'source_paths':[row['path'] for row in rows],'context_authority':'snapshot only; native permissions and claims remain authoritative','continuous_freshness':False,'checks_passed':True}


def evaluate_handoff(handoff,job,check):
 need(check.get('checks_passed') is True and check.get('status')=='PASS','Check did not pass')
 for key in ['ticket_id','run_id','context_sha256','startup_version']:
  need(check.get(key)==job.get(key),'Check identity mismatch: '+key)
 for key in ['ticket_id','run_id','context_sha256']:
  need(handoff.get(key)==job.get(key),'Handoff identity mismatch: '+key)
 need(handoff.get('claim_id')==check.get('claim_id') and bool(check.get('claim_id')),'Handoff claim mismatch')
 need(handoff.get('loaded_startup_version')==handoff.get('startup_version')==job.get('startup_version'),'Loaded context version mismatch')
 need(handoff.get('project')==job.get('project') and handoff.get('checks_passed') is True and handoff.get('continuous_freshness') is False,'Handoff project/freshness mismatch')
 need(hashlib.sha256(json.dumps(handoff,sort_keys=True).encode()).hexdigest()==check.get('handoff_sha256'),'Handoff digest mismatch')
 return {'status':'PASS','startup_bound':True,'execution_bound':True,'project_bound':True,'snapshot_limits_explicit':True}
