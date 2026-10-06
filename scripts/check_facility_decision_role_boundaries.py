#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from pathlib import Path

REPORT=Path('reports/facility-decision-role-boundaries.json')
APP=Path('src/App.tsx'); OVERVIEW=Path('src/pages/FacilityDecisionIntegrityPage.tsx'); SESSION=Path('src/pages/FacilityDecisionSessionPage.tsx')
EXPECTED={
 '/examples/facility-decision':'FacilityDecisionIntegrityPage',
 '/examples/facility-decision/learner':'FacilityDecisionLearnerPage',
 '/examples/facility-decision/teaching':'FacilityDecisionTeachingPage',
 '/examples/facility-decision/instructor':'FacilityDecisionInstructorPage',
 '/examples/facility-decision/demo':'FacilityDecisionDemoPage',
}
RESTRICTED={'normalized_source_score_bps','source_binding','facility_certificate','wit_observations','profile_authority','source_action_id','source_origin','autoplay_available','completed_replay_available','branch_controls','high_risk','must_equal','required_values'}

def walk(value):
 if isinstance(value,dict):
  for k,v in value.items(): yield k; yield from walk(v)
 elif isinstance(value,list):
  for v in value: yield from walk(v)

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--repo',default='.');ap.add_argument('--json-output',default=REPORT.as_posix());a=ap.parse_args();repo=Path(a.repo).resolve();errors=[];checks=0
 def check(c,m):
  nonlocal checks;checks+=1
  if not c:errors.append(m)
 for p in (APP,OVERVIEW,SESSION):check((repo/p).is_file(),f'missing:{p}')
 if not errors:
  app=(repo/APP).read_text();overview=(repo/OVERVIEW).read_text();session=(repo/SESSION).read_text()
  route_matches=re.findall(r'<Route\s+path="([^"]+)"\s+element=\{<([A-Za-z0-9_]+)',app)
  route_map={p:c for p,c in route_matches}
  for p,c in EXPECTED.items():check(route_map.get(p)==c,f'role route differs:{p}:{route_map.get(p)}')
  check(sum(1 for p,_ in route_matches if p.startswith('/examples/facility-decision'))==len(EXPECTED),'facility decision route inventory differs')
  check('useState<FacilityDecisionUiMode>' not in overview and 'setMode(' not in overview,'overview contains client-side mode switcher')
  check('FacilityDecisionSessionPage mode=' not in overview,'overview directly instantiates privileged session')
  expected_exports={
   'FacilityDecisionLearnerPage':'learner_assessment','FacilityDecisionTeachingPage':'learner_teaching',
   'FacilityDecisionInstructorPage':'instructor','FacilityDecisionDemoPage':'stakeholder_demo'}
  for name,mode in expected_exports.items():
   pattern=rf'export function {name}\(\) \{{\s*return <FacilityDecisionSessionPage mode="{mode}" />;\s*\}}'
   check(re.search(pattern,session,re.S) is not None,f'fixed role component differs:{name}')
  check('setMode(' not in session and 'mode switch' not in session.lower(),'session page contains role escalator')
  check('useSearchParams' not in session and 'location.search' not in session,'session role selectable from URL query')
  for file_name in ('learner-projection.json','teaching-projection.json'):
   p=repo/'examples/facility-decision'/file_name;check(p.is_file(),f'missing projection:{file_name}')
   if p.is_file():
    data=json.loads(p.read_text());observed=set(walk(data));leak=sorted(observed&RESTRICTED);check(not leak,f'learner projection leaks:{file_name}:{leak}')
    for action in data.get('actions', []):
     check(not str(action.get('category', '')).startswith('high_risk_'), f'learner action category leaks answer label:{file_name}:{action.get("decision_id")}')
     check('high_risk' not in action, f'learner action leaks high-risk judgment:{file_name}:{action.get("decision_id")}')
     for field in action.get('fields', []):
      check('must_equal' not in field and 'required_values' not in field, f'learner field leaks validation answer:{file_name}:{action.get("decision_id")}:{field.get("field_id")}')
  instructor=json.loads((repo/'examples/facility-decision/instructor-projection.json').read_text());demo=json.loads((repo/'examples/facility-decision/demo-projection.json').read_text())
  check(isinstance(instructor.get('instructor'),dict) and 'demo' not in instructor,'instructor projection boundary differs')
  check(isinstance(demo.get('instructor'),dict) and isinstance(demo.get('demo'),dict),'demo projection boundary differs')
  check('authenticated server boundary' in overview.lower(),'server authorization limitation not disclosed')
 report={'schema_version':'1.0.0','status':'PASS' if not errors else 'FAIL','checks':checks,'role_routes':EXPECTED,'errors':sorted(set(errors))}
 out=repo/a.json_output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps(report,indent=2,sort_keys=True));return 0 if not errors else 1
if __name__=='__main__':raise SystemExit(main())
