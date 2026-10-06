#!/usr/bin/env python3
"""Adversarial tests for the healthcare simulation quality source contract."""
from __future__ import annotations
import argparse,json,shutil,tempfile
from pathlib import Path
from typing import Callable
from release_result import EXPECTED_REJECTION,FAIL,PASS,case_result,exit_code,suite_classification
from release_simulation_quality import validate

Mutator=Callable[[Path],None]
def edit(repo:Path,rel:str,fn:Callable[[dict],None]):
 p=repo/rel; v=json.loads(p.read_text()); fn(v); p.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n")

def run(root:Path)->dict:
 cases=[
  ("baseline",None,None),
  ("debrief_domain_disabled",lambda r:edit(r,"config/release/SIMULATION_QUALITY_PROFILE.json",lambda d:d["required_domains"]["debriefing"].__setitem__("required",False)),"simulation quality domain disabled:debriefing"),
  ("strength_three_weakened",lambda r:edit(r,"config/release/SIMULATION_QUALITY_PROFILE.json",lambda d:d["minimum_engine_evidence"].__setitem__("required_strength_three_coverage_ratio",0.8)),"strength-three coverage weakened"),
  ("dead_end_allowed",lambda r:edit(r,"config/release/SIMULATION_QUALITY_PROFILE.json",lambda d:d["minimum_engine_evidence"].__setitem__("reachable_active_dead_ends",1)),"reachable dead ends permitted"),
  ("manual_pilot_removed",lambda r:edit(r,"config/release/SIMULATION_QUALITY_PROFILE.json",lambda d:d["manual_validation"].__setitem__("facilitator_pilot","OPTIONAL")),"manual validation boundary missing:facilitator_pilot"),
  ("prebrief_removed_from_ui",lambda r:(r/"src/pages/ResearchScenarioLabPage.tsx").write_text((r/"src/pages/ResearchScenarioLabPage.tsx").read_text().replace("Prebrief and objectives","Brief")),"scenario laboratory experience marker missing:Prebrief and objectives"),
  ("learner_high_risk_reintroduced",lambda r:(r/"src/pages/FacilityDecisionSessionPage.tsx").write_text((r/"src/pages/FacilityDecisionSessionPage.tsx").read_text()+"\nconst regression = selectedAction.high_risk;\n"),"restricted high_risk field leaked"),
  ("error_focus_removed",lambda r:(r/"src/pages/FacilityDecisionSessionPage.tsx").write_text((r/"src/pages/FacilityDecisionSessionPage.tsx").read_text().replace("errorSummary.current?.focus()","undefined")),"learner experience marker missing:errorSummary.current?.focus()"),
 ]
 results=[]
 for cid,mut,needle in cases:
  with tempfile.TemporaryDirectory(prefix="asklepios-quality-") as td:
   repo=Path(td)/"repo"; shutil.copytree(root,repo,ignore=shutil.ignore_patterns(".git","node_modules",".asklepios","dist"));
   if mut: mut(repo)
   observed=validate(repo); errs=observed.get("errors",[])
   if mut is None: ok=observed.get("classification")==PASS; cls=PASS if ok else FAIL
   else: ok=observed.get("classification")==FAIL and any(needle in e for e in errs); cls=EXPECTED_REJECTION if ok else FAIL
   results.append(case_result(cid,cls,errors=[] if ok else errs,required_error=needle,observed_classification=observed.get("classification")))
 cls=suite_classification(results); return {"schema_version":"1.0.0","classification":cls,"status":cls,"cases":len(results),"results":results,"errors":[] if cls==PASS else ["simulation quality mutation suite failed"]}

def main():
 p=argparse.ArgumentParser();p.add_argument("--repo",type=Path,default=Path("."));p.add_argument("--json-output",type=Path,default=Path("reports/simulation-quality-mutations.json"));a=p.parse_args();r=run(a.repo.resolve());(a.repo.resolve()/a.json_output).parent.mkdir(parents=True,exist_ok=True);(a.repo.resolve()/a.json_output).write_text(json.dumps(r,indent=2,sort_keys=True)+"\n");print(json.dumps(r,indent=2,sort_keys=True));return exit_code(r["classification"])
if __name__=="__main__":raise SystemExit(main())
