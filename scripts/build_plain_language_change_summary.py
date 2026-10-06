#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path,PurePosixPath
from typing import Any
CONFIG='config/release/PLAIN_LANGUAGE_CHANGE_SUMMARY.json'
COMPILED_HEADINGS=(
 'What changed?','What can a learner do now?','What can an instructor do now?',
 'What changed in scenario variety?','What changed in scoring?','What changed in treatment content?',
 'What safety limitation remains?','What is still not calibrated or validated?',
)
SECTION_KEYS=('what_changed','learner_gain','instructor_gain','scenario_variety','scoring_change','treatment_change','safety_limitations','not_calibrated_or_validated')
FORBIDDEN=('clinically validated','patient care ready','realistic clinical timing','this is a validated proficiency score','treatment recommendation','debt-free','zero risk')

def canonical(v:Any)->str:
 if isinstance(v,float):raise ValueError('floating point forbidden in change summary')
 if isinstance(v,list):return '['+','.join(canonical(x) for x in v)+']'
 if isinstance(v,dict):return '{'+','.join(json.dumps(str(k),ensure_ascii=False)+':'+canonical(v[k]) for k in sorted(v))+'}'
 return json.dumps(v,ensure_ascii=False,separators=(',',':'))
def sha(v:Any)->str:return hashlib.sha256(canonical(v).encode()).hexdigest()
def safe(repo:Path,v:Any,label:str)->Path:
 if not isinstance(v,str) or not v or '\x00' in v or '\\' in v:raise ValueError(f'unsafe repository path:{label}')
 p=PurePosixPath(v)
 if p.is_absolute() or any(x in {'','.','..'} or ':' in x or x.endswith((' ','.')) for x in p.parts):raise ValueError(f'unsafe repository path:{label}')
 c=repo.joinpath(*p.parts);r=c.resolve(strict=False)
 if r!=repo and repo not in r.parents:raise ValueError(f'repository path escapes root:{label}')
 return c
def load(p:Path)->dict[str,Any]:
 if p.is_symlink() or not p.is_file():raise ValueError(f'required regular JSON file missing:{p}')
 v=json.loads(p.read_text(encoding='utf-8'))
 if not isinstance(v,dict):raise ValueError('change summary JSON object required')
 return v
def validate(v:dict[str,Any])->list[str]:
 errors=[];b=dict(v);b.pop('summary_sha256',None)
 if v.get('summary_sha256')!=sha(b):errors.append('plain-language summary self hash differs')
 if v.get('required_heading_order')!=list(COMPILED_HEADINGS):errors.append('plain-language heading order differs from compiled floor')
 sections=v.get('sections')
 if not isinstance(sections,dict):errors.append('plain-language section map missing');sections={}
 for key in SECTION_KEYS:
  items=sections.get(key)
  if not isinstance(items,list) or not items:errors.append(f'plain-language section missing:{key}');continue
  for item in items:
   if not isinstance(item,str) or len(item.strip())<20:errors.append(f'plain-language statement too short:{key}')
 text=' '.join(str(item).lower() for items in sections.values() if isinstance(items,list) for item in items)
 for phrase in FORBIDDEN:
  if phrase in text:errors.append(f'unsupported plain-language claim:{phrase}')
 boundaries=v.get('authority_boundaries') or {}
 expected={'direct_patient_care':'PROHIBITED','clinical_decision_support':'PROHIBITED','operational_timing':'NOT_CALIBRATED','scoring_validity':'SOURCE_CONFORMANCE_ONLY_NOT_PSYCHOMETRIC','patient_care_authority':'NONE'}
 for k,val in expected.items():
  if boundaries.get(k)!=val:errors.append(f'plain-language authority boundary differs:{k}')
 return errors
def render(v:dict[str,Any])->str:
 lines=[f"# {v['release_label']}",'',f"Summary identity: `{v['summary_id']}`",'', 'This document explains the user-facing effect of the release. It does not replace the underlying assurance evidence.','']
 sections=v['sections']
 for heading,key in zip(COMPILED_HEADINGS,SECTION_KEYS):
  lines.extend([f'## {heading}',''])
  lines.extend(f'- {item}' for item in sections[key]);lines.append('')
 lines.extend(['## Permanent authority boundary','', '- Healthcare simulation and training are permitted only within the validated scope.', '- Direct patient care is prohibited.', '- Clinical decision support is prohibited.', '- Patient-care authority is none.', '- Operational timing is not calibrated.', '- Scoring remains source-conformance only and is not a validated proficiency measure.',''])
 return '\n'.join(lines)
def atomic(p:Path,text:str)->None:
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+'.tmp');t.write_text(text,encoding='utf-8',newline='\n');t.replace(p)
def main()->int:
 a=argparse.ArgumentParser();a.add_argument('--repo',default='.');a.add_argument('--check',action='store_true');a.add_argument('--json-output',default='reports/plain-language-change-summary.json');args=a.parse_args();repo=Path(args.repo).resolve();errors=[];mismatches=[]
 try:
  v=load(safe(repo,CONFIG,'config'));errors=validate(v);expected=render(v);out=safe(repo,v.get('output_path'),'output_path')
  if not errors:
   if args.check:
    if not out.is_file() or out.is_symlink() or out.read_text(encoding='utf-8')!=expected:mismatches.append(v.get('output_path'))
   else:atomic(out,expected)
 except Exception as exc:errors.append(str(exc));v={}
 classification='PASS' if not errors and not mismatches else 'FAIL';report={'schema_version':'1.0.0','classification':classification,'status':classification,'mode':'check' if args.check else 'write','summary_id':v.get('summary_id'),'output_path':v.get('output_path'),'headings':len(COMPILED_HEADINGS),'sections':len(SECTION_KEYS),'mismatches':mismatches,'errors':errors}
 try:atomic(safe(repo,args.json_output,'json_output'),json.dumps(report,indent=2,sort_keys=True)+'\n')
 except Exception:pass
 print(json.dumps(report,indent=2,sort_keys=True));return 0 if classification=='PASS' else 3
if __name__=='__main__':raise SystemExit(main())
