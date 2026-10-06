#!/usr/bin/env python3
from __future__ import annotations
import argparse,ast,hashlib,json,shutil,subprocess,sys,tempfile
from pathlib import Path
from typing import Any,Callable

def canonical(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def rehash(v:dict[str,Any])->None:
 b=dict(v);b.pop('policy_sha256',None);v['policy_sha256']=hashlib.sha256(canonical(b)).hexdigest()
def write(p:Path,v:Any):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')
def run(r:Path):
 p=subprocess.run([sys.executable,'scripts/check_ci_portability_policy.py','--repo','.','--json-output','reports/result.json'],cwd=r,text=True,capture_output=True,timeout=30)
 try:return p.returncode==0,json.loads((r/'reports/result.json').read_text()).get('errors',[])
 except:return False,[p.stdout[-500:],p.stderr[-500:]]
def replace(r:Path,path:str,old:str,new:str,all_occurrences:bool=False):
 p=r/path;s=p.read_text();
 if old not in s:raise RuntimeError(f'mutation marker missing:{old}')
 p.write_text(s.replace(old,new) if all_occurrences else s.replace(old,new,1))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',default='.');ap.add_argument('--json-output',default='reports/ci-portability-policy-mutations.json');a=ap.parse_args();root=Path(a.repo).resolve();policy=json.loads((root/'config/release/CI_PORTABILITY_POLICY.json').read_text())
 cases:[tuple[str,bool,Callable[[Path,dict[str,Any]],None],str|None]]=[
  ('baseline',True,lambda *_:None,None),
  ('workspace-profile-weakened',False,lambda _r,p:(p.__setitem__('workspace_path_profile','LONG_CASE_NAMES'),rehash(p)),'compiled floor differs:workspace_path_profile'),
  ('path-budget-widened',False,lambda _r,p:(p.__setitem__('portable_windows_path_budget',320),rehash(p)),'compiled floor differs:portable_windows_path_budget'),
  ('hash-length-reduced',False,lambda _r,p:(p.__setitem__('workspace_component_hash_hex',8),rehash(p)),'compiled floor differs:workspace_component_hash_hex'),
  ('runner-temp-removed',False,lambda r,_p:replace(r,'scripts/test_release_graph.py','os.environ.get("RUNNER_TEMP")','os.environ.get("NOT_RUNNER_TEMP")'),'source marker missing:os.environ.get("RUNNER_TEMP")'),
  ('mutation-full-name-regression',False,lambda r,_p:replace(r,'scripts/test_release_graph.py','worker_root = root / _compact_workspace_component("m", case_id)','worker_root = root / case_id',True),'source marker missing:_compact_workspace_component("m", case_id)'),
  ('heavy-full-name-regression',False,lambda r,_p:replace(r,'scripts/test_release_graph.py','worker_root = root / _compact_workspace_component("h", case_id)','worker_root = root / case_id',True),'source marker missing:_compact_workspace_component("h", case_id)'),
  ('internal-error-diagnostics-removed',False,lambda r,_p:replace(r,'scripts/test_release_graph.py','failed_case_diagnostics','removed_failed_diagnostics',True),'source marker missing:failed_case_diagnostics'),
  ('windows-job-removed',False,lambda _r,p:(p['required_windows_jobs'].pop(),rehash(p)),'Windows job inventory differs'),
 ]
 results=[];accepted=0
 with tempfile.TemporaryDirectory(prefix='asklepios-ci-portability-') as t:
  base=Path(t)/'base';shutil.copytree(root,base,ignore=shutil.ignore_patterns('.git','node_modules','.asklepios','__pycache__','*.pyc'))
  for cid,expected,mutate,required in cases:
   f=Path(t)/cid;shutil.copytree(base,f);p=json.loads(json.dumps(policy));
   try:mutate(f,p);write(f/'config/release/CI_PORTABILITY_POLICY.json',p)
   except Exception as exc:results.append({'case_id':cid,'classification':'INTERNAL_ERROR','pass':False,'errors':[str(exc)]});continue
   observed,errs=run(f);ok=observed==expected and (required is None or any(required in e for e in errs));accepted+=int(not expected and observed);results.append({'case_id':cid,'classification':'PASS' if expected and observed else 'EXPECTED_REJECTION' if not expected and not observed else 'FAIL','observed_pass':observed,'pass':ok,'checker_errors':errs})
 errors=[x['case_id'] for x in results if not x['pass']];report={'schema_version':'1.0.0','classification':'PASS' if not errors else 'FAIL','status':'PASS' if not errors else 'FAIL','cases':len(results),'attacks':len(results)-1,'accepted_attacks':accepted,'errors':errors,'results':results};write(root/a.json_output,report);print(json.dumps(report,indent=2));return 0 if not errors else 3
if __name__=='__main__':raise SystemExit(main())
