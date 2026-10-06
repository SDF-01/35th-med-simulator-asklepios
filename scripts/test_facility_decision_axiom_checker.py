#!/usr/bin/env python3
from __future__ import annotations
import copy, importlib.util, json, tempfile
from pathlib import Path
from release_result import finalize_adversarial_report

ROOT=Path.cwd()
spec=importlib.util.spec_from_file_location('checker',ROOT/'scripts/check_facility_decision_axioms.py')
assert spec and spec.loader
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
manifest=json.loads((ROOT/'formal/FACILITY_DECISION_INTEGRITY_TRUST_MANIFEST.json').read_text())
base='\n'.join(f"'{name}' does not depend on any axioms" for name in checker.EXPECTED_THEOREMS)+'\n'
cases=[]
def run(cid,text,mf,expected):
 r=checker.validate(text,mf); observed=r['status']=='PASS'; cases.append({'case_id':cid,'pass':observed==expected,'checker_status':r['status'],'errors':r['errors']})
run('exact_zero_axiom_log',base,manifest,True)
run('propext_rejected',base.replace('does not depend on any axioms','depends on axioms: [propext]',1),manifest,False)
run('missing_theorem_rejected','\n'.join(base.splitlines()[1:])+'\n',manifest,False)
run('duplicate_theorem_rejected',base+base.splitlines()[0]+'\n',manifest,False)
run('unexpected_theorem_rejected',base+"'ScenarioContracts.unreviewed_decision_theorem' does not depend on any axioms\n",manifest,False)
run('sorry_axiom_rejected',base.replace('does not depend on any axioms','depends on axioms: [sorryAx]',1),manifest,False)
wide=copy.deepcopy(manifest);wide['per_theorem_axioms'][checker.EXPECTED_THEOREMS[0]]=['propext'];run('manifest_self_widening_rejected',base,wide,False)
renamed=copy.deepcopy(manifest);renamed['module']='ScenarioContracts.Other';run('manifest_module_rewrite_rejected',base,renamed,False)
run('malformed_line_rejected',base.splitlines()[0].replace("' "," ")+' malformed\n'+'\n'.join(base.splitlines()[1:])+'\n',manifest,False)
failed=[x['case_id'] for x in cases if not x['pass']]
report={'schema_version':'1.0.0','status':'PASS' if not failed else 'FAIL','cases':len(cases),'errors':failed,'results':cases}
report=finalize_adversarial_report(report,baseline_case_ids=('exact_zero_axiom_log',))
print(json.dumps(report,indent=2));raise SystemExit(0 if not failed else 3)
