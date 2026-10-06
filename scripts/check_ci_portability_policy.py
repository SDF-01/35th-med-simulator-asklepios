#!/usr/bin/env python3
from __future__ import annotations
import argparse, ast, hashlib, json, os, re, tempfile
from pathlib import Path
from typing import Any

PROFILE='CONTENT_ADDRESSED_COMPACT_WORKSPACE_PATHS_V1'
HASH_HEX=20
PATH_BUDGET=240
WINDOWS_JOBS=['facility-runtime-windows','facility-decision-runtime-windows','standalone-windows']

def canonical(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def sha(v:Any)->str:return hashlib.sha256(canonical(v)).hexdigest()
def read(path:Path)->Any:return json.loads(path.read_text(encoding='utf-8'))
def write(path:Path,v:Any)->None:
 path.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
 try:
  with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:f.write(json.dumps(v,indent=2)+'\n');f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
 except Exception:
  try:os.unlink(tmp)
  except FileNotFoundError:pass
  raise

def constants(path:Path)->dict[str,Any]:
 tree=ast.parse(path.read_text(encoding='utf-8')); result={}
 for node in tree.body:
  if isinstance(node,(ast.Assign,ast.AnnAssign)):
   targets=node.targets if isinstance(node,ast.Assign) else [node.target]; value=node.value
   for t in targets:
    if isinstance(t,ast.Name):
     try: result[t.id]=ast.literal_eval(value)
     except Exception: pass
 return result

def workflows(root:Path)->set[str]:
 jobs=set()
 for path in (root/'.github/workflows').glob('*.yml'):
  text=path.read_text(encoding='utf-8')
  in_jobs=False
  for line in text.splitlines():
   if line.strip()=='jobs:':in_jobs=True;continue
   if in_jobs:
    match=re.match(r'^  ([A-Za-z0-9_-]+):\s*$',line)
    if match:jobs.add(match.group(1))
 return jobs

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--repo',default='.');ap.add_argument('--json-output',default='reports/ci-portability-policy.json');args=ap.parse_args();root=Path(args.repo).resolve();errors=[]
 try:
  policy=read(root/'config/release/CI_PORTABILITY_POLICY.json');body=dict(policy);observed=body.pop('policy_sha256',None)
  if observed!=sha(body):errors.append('CI portability policy self hash differs')
  exact={'workspace_path_profile':PROFILE,'workspace_component_hash_hex':HASH_HEX,'portable_windows_path_budget':PATH_BUDGET,'preferred_temporary_root_environment':'RUNNER_TEMP','checkpoint_identity_includes_workspace_profile':True,'internal_error_requires_durable_diagnostics':True,'windows_command_boundary':'EXPLICIT_CMD_EXE_FOR_COMMAND_SHIMS_V1'}
  for key,value in exact.items():
   if policy.get(key)!=value:errors.append(f'CI portability compiled floor differs:{key}')
  if policy.get('required_windows_jobs')!=WINDOWS_JOBS:errors.append('CI portability Windows job inventory differs')
  source=root/'scripts/test_release_graph.py'; checker=root/'scripts/check_release_graph.py'; source_text=source.read_text(encoding='utf-8'); checker_text=checker.read_text(encoding='utf-8'); c=constants(source)
  if c.get('WORKSPACE_PATH_PROFILE')!=PROFILE:errors.append('release graph workspace profile differs')
  if c.get('WORKSPACE_COMPONENT_HASH_HEX')!=HASH_HEX:errors.append('release graph workspace hash length differs')
  if c.get('PORTABLE_WINDOWS_PATH_BUDGET')!=PATH_BUDGET:errors.append('release graph Windows path budget differs')
  markers=['os.environ.get("RUNNER_TEMP")','_compact_workspace_component("m", case_id)','_compact_workspace_component("h", case_id)','portable-workspace-path-budget-is-enforced','failed_case_diagnostics']
  for marker in markers:
   if marker not in source_text:errors.append(f'CI portability source marker missing:{marker}')
  for marker in [PROFILE,'release-graph-workspace-path-profile-weakened','release-graph-mutation-workspace-full-case-id-regression','release-graph-heavy-workspace-full-case-id-regression']:
   if marker not in checker_text:errors.append(f'CI portability checker marker missing:{marker}')
  observed_jobs=workflows(root)
  for job in WINDOWS_JOBS:
   if job not in observed_jobs:errors.append(f'required Windows workflow job missing:{job}')
  # The canonical release-graph checker independently validates workflow ownership.
 except Exception as exc:errors.append(str(exc))
 result={'schema_version':'1.0.0','classification':'FAIL' if errors else 'PASS','status':'FAIL' if errors else 'PASS','policy_id':'asklepios-ci-portability-policy-v1','workspace_path_profile':PROFILE,'portable_windows_path_budget':PATH_BUDGET,'required_windows_jobs':WINDOWS_JOBS,'known_failure_classes_structurally_blocked':9,'errors':errors}
 write(root/args.json_output,result);print(json.dumps(result,indent=2));return 0 if not errors else 3
if __name__=='__main__':raise SystemExit(main())
