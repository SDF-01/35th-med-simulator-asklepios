#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shutil, subprocess, sys, tempfile
from pathlib import Path
from release_result import finalize_adversarial_report
FILES=['src/App.tsx','src/pages/FacilityDecisionIntegrityPage.tsx','src/pages/FacilityDecisionSessionPage.tsx','examples/facility-decision/learner-projection.json','examples/facility-decision/teaching-projection.json','examples/facility-decision/instructor-projection.json','examples/facility-decision/demo-projection.json','scripts/check_facility_decision_role_boundaries.py']
def run(repo):
 c=subprocess.run([sys.executable,'scripts/check_facility_decision_role_boundaries.py','--repo','.','--json-output','reports/role.json'],cwd=repo,text=True,capture_output=True);p=None
 try:p=json.loads(c.stdout)
 except:pass
 return c.returncode,p
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',default='.');ap.add_argument('--json-output',default='reports/facility-decision-role-boundary-mutations.json');a=ap.parse_args();src=Path(a.repo).resolve();results=[];errors=[]
 cases=[
 ('baseline',None,True),
 ('learner_route_to_instructor',lambda r:(r/'src/App.tsx').write_text((r/'src/App.tsx').read_text().replace('<FacilityDecisionLearnerPage />','<FacilityDecisionInstructorPage />'),encoding='utf-8'),False),
 ('overview_mode_switcher',lambda r:(r/'src/pages/FacilityDecisionIntegrityPage.tsx').write_text((r/'src/pages/FacilityDecisionIntegrityPage.tsx').read_text()+"\n// useState<FacilityDecisionUiMode> setMode(\n",encoding='utf-8'),False),
 ('session_query_escalator',lambda r:(r/'src/pages/FacilityDecisionSessionPage.tsx').write_text((r/'src/pages/FacilityDecisionSessionPage.tsx').read_text()+"\n// useSearchParams role escalator\n",encoding='utf-8'),False),
 ('learner_score_leak',lambda r:mut_json(r/'examples/facility-decision/learner-projection.json','normalized_source_score_bps',10000),False),
 ('learner_provenance_leak',lambda r:mut_json(r/'examples/facility-decision/learner-projection.json','source_binding',{}),False),
 ('learner_high_risk_judgment_leak',lambda r:mut_action(r/'examples/facility-decision/learner-projection.json','discharge_without_workup','high_risk',True),False),
 ('learner_high_risk_category_leak',lambda r:mut_action(r/'examples/facility-decision/learner-projection.json','discharge_without_workup','category','high_risk_disposition'),False),
 ('learner_validation_answer_leak',lambda r:mut_field(r/'examples/facility-decision/learner-projection.json','discharge_without_workup','deliberate_confirmation','must_equal',True),False),
 ('instructor_demo_escalation',lambda r:mut_json(r/'examples/facility-decision/instructor-projection.json','demo',{'autoplay_available':True}),False),
 ('missing_server_limit',lambda r:(r/'src/pages/FacilityDecisionIntegrityPage.tsx').write_text((r/'src/pages/FacilityDecisionIntegrityPage.tsx').read_text().replace('authenticated server boundary','future authorization layer'),encoding='utf-8'),False),
 ]
 for cid,mut,expect in cases:
  with tempfile.TemporaryDirectory(prefix='asklepios-role-') as td:
   r=Path(td)/'repo'
   for f in FILES:
    d=r/f;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src/f,d)
   if mut:mut(r)
   rc,p=run(r);observed=rc==0;passed=observed==expect
   if not passed:errors.append(f'{cid}:expected={expect}:observed={observed}')
   results.append({'case_id':cid,'expected_pass':expect,'observed_pass':observed,'pass':passed,'checker_errors':p.get('errors',[]) if isinstance(p,dict) else ['checker_internal_error']})
 report={'schema_version':'1.0.0','status':'PASS' if not errors else 'FAIL','cases':len(results),'attacks':len(results)-1,'results':results,'errors':errors};report=finalize_adversarial_report(report,baseline_case_ids=("baseline",));out=src/a.json_output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps(report,indent=2,sort_keys=True));return 0 if not errors else 1
def mut_action(path, decision_id, key, val):
 d=json.loads(path.read_text())
 action=next(item for item in d['actions'] if item['decision_id']==decision_id)
 action[key]=val
 path.write_text(json.dumps(d,indent=2)+'\n')
def mut_field(path, decision_id, field_id, key, val):
 d=json.loads(path.read_text())
 action=next(item for item in d['actions'] if item['decision_id']==decision_id)
 field=next(item for item in action['fields'] if item['field_id']==field_id)
 field[key]=val
 path.write_text(json.dumps(d,indent=2)+'\n')
def mut_json(path,key,val):
 d=json.loads(path.read_text());d[key]=val;path.write_text(json.dumps(d,indent=2)+'\n')
if __name__=='__main__':raise SystemExit(main())
