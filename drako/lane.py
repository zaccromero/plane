"""Small Plane/Drako seam. No model dispatch or automatic owner acceptance."""
from __future__ import annotations
import hashlib,json,os,urllib.request,urllib.parse
from pathlib import Path

class Plane:
 def __init__(self,base,token,workspace,project):
  u=urllib.parse.urlparse(base)
  if u.scheme!='https' and not(u.scheme=='http' and u.hostname in {'localhost','127.0.0.1'}):raise ValueError('Use HTTPS or local Plane')
  if not token or not workspace or not project:raise ValueError('Explicit Plane binding required')
  self.base=base.rstrip('/');self.token=token
  self.prefix='/api/v1/workspaces/'+urllib.parse.quote(workspace,safe='')+'/projects/'+urllib.parse.quote(project,safe='')
 def request(self,method,path,data=None):
  req=urllib.request.Request(self.base+self.prefix+path,data=None if data is None else json.dumps(data).encode(),method=method,headers={'X-API-Key':self.token,'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=15) as r:return json.load(r) if r.status!=204 else None
 def create(self,title,description):return self.request('POST','/issues/',{'name':title,'description_html':description})
 def get(self,ticket):return self.request('GET','/issues/'+urllib.parse.quote(ticket,safe='')+'/')
 def update(self,ticket,data):return self.request('PATCH','/issues/'+urllib.parse.quote(ticket,safe='')+'/',data)
 def comment(self,ticket,html):return self.request('POST','/issues/'+urllib.parse.quote(ticket,safe='')+'/comments/',{'comment_html':html})

def manifest(paths):
 rows=[]
 for value in paths:
  p=Path(value)
  if p.is_symlink() or not p.is_file():raise ValueError('Context requires regular explicit files')
  rows.append({'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 raw=json.dumps(rows,sort_keys=True).encode()
 return {'schema':'drako.plane.context.v1','files':rows,'sha256':hashlib.sha256(raw).hexdigest()}

def verify_context(context):
 for row in context['files']:
  p=Path(row['path'])
  if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Context is missing or stale')
 if manifest([r['path'] for r in context['files']])['sha256']!=context['sha256']:raise ValueError('Context manifest changed')

def evaluate(result,context):
 verify_context(context)
 checks={
  'context_bound':result.get('context_sha256')==context['sha256'],
  'ticket_bound':bool(result.get('ticket_id')),
  'execution_bound':bool(result.get('run_id')) and bool(result.get('claim_id')),
  'vault_auth':result.get('authenticated_search')==200 and result.get('anonymous_search')==401,
  'paths_reconciled':result.get('relocated')==31 and result.get('absent_retained')==7,
  'database_healthy':result.get('database_check')=='ok',
  'known_symbol_fresh':result.get('known_found') is True and result.get('known_stale') is False,
  'invented_symbol_refused':result.get('invented_found') is False,
  'trace_observed':result.get('trace_observed') is True,
 }
 return {'schema':'drako.plane.eval.v1','version':1,'checks':checks,'passed':all(checks.values()),'owner_acceptance':'pending'}
