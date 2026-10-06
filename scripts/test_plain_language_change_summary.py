#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,shutil,subprocess,sys,tempfile
from pathlib import Path
from typing import Any,Callable
CFG=Path('config/release/PLAIN_LANGUAGE_CHANGE_SUMMARY.json');DOC=Path('docs/RC3_8D_PLAIN_LANGUAGE_CHANGE_SUMMARY.md')
def sha(v:Any)->str:return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def write(p:Path,v:Any)->None:p.write_text(json.dumps(v,indent=2,sort_keys=True,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
def mutcfg(r:Path,fn:Callable[[dict[str,Any]],None],rehash=True):
 v=json.loads((r/CFG).read_text());fn(v)
 if rehash:b=dict(v);b.pop('summary_sha256',None);v['summary_sha256']=sha(b)
 write(r/CFG,v)
def run(r:Path)->tuple[bool,list[str]]:
 cmds=[[sys.executable,'scripts/build_plain_language_change_summary.py','--repo','.','--check','--json-output','reports/plain-language-change-summary.json'],['node','scripts/check_plain_language_change_summary.mjs','--repo','.','--json-output','reports/plain-language-change-summary-node.json']];ok=True;errs=[]
 for c in cmds:
  x=subprocess.run(c,cwd=r,text=True,capture_output=True,check=False,timeout=90);ok=ok and x.returncode==0;t=(x.stdout or '')+'\n'+(x.stderr or '')
  try:s=t.find('{');p=json.loads(t[s:]);errs.extend(p.get('errors') or []);errs.extend(p.get('mismatches') or [])
  except Exception:errs.append(t[-1200:])
 return ok,sorted(set(str(e) for e in errs if e))
def main()->int:
 a=argparse.ArgumentParser();a.add_argument('--repo',default='.');a.add_argument('--json-output',default='reports/plain-language-change-summary-mutations.json');z=a.parse_args();src=Path(z.repo).resolve()
 cases=[('baseline',None,True,None),('learner-section-removed',lambda r:mutcfg(r,lambda v:v['sections'].__setitem__('learner_gain',[])),False,'section missing:learner_gain'),('heading-order-weakened',lambda r:mutcfg(r,lambda v:v['required_heading_order'].reverse()),False,'heading order differs'),('direct-care-promoted',lambda r:mutcfg(r,lambda v:v['authority_boundaries'].__setitem__('direct_patient_care','PERMITTED')),False,'authority boundary differs:direct_patient_care'),('validated-proficiency-claim',lambda r:mutcfg(r,lambda v:v['sections']['scoring_change'].append('This is a validated proficiency score.')),False,'unsupported plain-language claim:this is a validated proficiency score'),('markdown-drift',lambda r:(r/DOC).write_text((r/DOC).read_text()+'\nextra\n'),False,'Markdown differs'),('summary-hash-forged',lambda r:mutcfg(r,lambda v:v.__setitem__('summary_sha256','0'*64),False),False,'self hash differs'),('output-traversal',lambda r:mutcfg(r,lambda v:v.__setitem__('output_path','../escape.md')),False,'unsafe repository path:output_path')]
 results=[];errors=[]
 with tempfile.TemporaryDirectory(prefix='asklepios-plain-summary-') as t:
  template=Path(t)/'template';shutil.copytree(src,template,ignore=shutil.ignore_patterns('.git','node_modules','.asklepios','dist','__pycache__','*.pyc'))
  for cid,m,e,req in cases:
   c=Path(t)/('case-'+cid);shutil.copytree(template,c);m(c) if m else None;obs,errs=run(c);ok=obs==e and (req is None or any(req in x for x in errs));cl='PASS' if e and obs else 'EXPECTED_REJECTION' if not e and not obs else 'FAIL';results.append({'case_id':cid,'classification':cl,'expected_pass':e,'observed_pass':obs,'checker_errors':errs,'required_error':req,'pass':ok});errors+=[] if ok else ['case failed:'+cid]
 report={'schema_version':'1.0.0','classification':'PASS' if not errors else 'FAIL','cases':len(results),'attacks':len(results)-1,'accepted_attacks':sum(1 for i in results[1:] if i['observed_pass']),'results':results,'errors':errors};write(src/z.json_output,report);print(json.dumps(report,indent=2,sort_keys=True));return 0 if not errors else 3
if __name__=='__main__':raise SystemExit(main())
