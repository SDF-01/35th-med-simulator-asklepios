#!/usr/bin/env python3
"""Mutation tests for simulation clock and clinical timing boundaries."""
from __future__ import annotations
import argparse,json,shutil,tempfile
from pathlib import Path
from typing import Callable
from release_result import EXPECTED_REJECTION,FAIL,PASS,case_result,exit_code,suite_classification
from release_simulation_timing import validate

Mut=Callable[[Path],None]
def edit(r:Path,p:str,fn:Callable[[dict],None]):
 q=r/p;v=json.loads(q.read_text());fn(v);q.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n")
def runtime_report():
 return {'schema_version':'1.0.0','classification':'PASS','status':'PASS','clinical_timing_calibrated':False,'canonical':{'event_count':1,'completed_at_seconds':255,'triggering_action_id':None,'preceding_action_id':'order_imaging','early_fire':False,'fired_system_events_count':1},'alternate':{'event_count':1,'completed_at_seconds':255,'triggering_action_id':None,'preceding_action_id':'monitor_vitals','early_fire':False,'fired_system_events_count':1},'action_identity_independent':True,'response_time':{'iterations':1000,'p50_ms':1.0,'p95_ms':3.0,'p99_ms':6.0,'max_ms':8.0,'budgets_ms':{'p50':25.0,'p95':100.0,'p99':250.0}},'errors':[]}

def run(root:Path)->dict:
 cases:[tuple[str,Mut|None,str|None]]=[
  ('baseline',None,None),
  ('clinical_timing_promoted',lambda r:edit(r,'config/release/SIMULATION_TIMING_POLICY.json',lambda d:d['clock_domains']['real_world_clinical_operational_timing'].__setitem__('status','CALIBRATED')),'clinical operational timing was promoted'),
  ('facility_241_mismatch',lambda r:edit(r,'config/facility-arrival/ASK-D-001.json',lambda d:next(e for e in d['events'] if e['event_id']=='second_casualty_inbound')['trigger'].__setitem__('at_elapsed_seconds',241)),'facility timed event binding differs'),
  ('action_trigger_regression',lambda r:edit(r,'config/facility-arrival/ASK-D-001.json',lambda d:next(e for e in d['events'] if e['event_id']=='second_casualty_inbound').__setitem__('trigger',{'kind':'after_action','action_id':'order_imaging'})),'facility timed event binding differs'),
  ('runtime_early_fire',lambda r:edit(r,'reports/simulation-timing-runtime.json',lambda d:(d['canonical'].__setitem__('completed_at_seconds',239),d['canonical'].__setitem__('early_fire',True))),'canonical clock event fired early'),
  ('runtime_duplicate_fire',lambda r:edit(r,'reports/simulation-timing-runtime.json',lambda d:d['alternate'].__setitem__('event_count',2)),'alternate clock event did not fire exactly once'),
  ('runtime_action_coupled',lambda r:edit(r,'reports/simulation-timing-runtime.json',lambda d:(d['alternate'].__setitem__('preceding_action_id','order_imaging'),d.__setitem__('action_identity_independent',False))),'runtime event remained action-coupled'),
  ('runtime_system_event_action_bound',lambda r:edit(r,'reports/simulation-timing-runtime.json',lambda d:(d['canonical'].__setitem__('triggering_action_id','order_imaging'),d.__setitem__('action_identity_independent',False))),'runtime system event retained an action identity'),
  ('runtime_schedule_drift',lambda r:edit(r,'reports/simulation-timing-runtime.json',lambda d:d['alternate'].__setitem__('completed_at_seconds',256)),'runtime event time differs across valid orderings'),
  ('runtime_p95_budget_exceeded',lambda r:edit(r,'reports/simulation-timing-runtime.json',lambda d:d['response_time'].__setitem__('p95_ms',101.0)),'runtime p95 budget exceeded'),
  ('runtime_clinical_promotion',lambda r:edit(r,'reports/simulation-timing-runtime.json',lambda d:d.__setitem__('clinical_timing_calibrated',True)),'runtime report promoted clinical timing'),
  ('graph_clinical_promotion',lambda r:edit(r,'config/release/RELEASE_GRAPH.json',lambda d:d['truth_boundaries'].__setitem__('clinical_operational_timing','CALIBRATED')),'graph clinical timing boundary differs'),
  ('protocol_clinical_promotion',lambda r:edit(r,'config/release/OPERATIONAL_TIMING_CALIBRATION_PROTOCOL.json',lambda d:d.__setitem__('current_status','CALIBRATED')),'operational timing calibration protocol was promoted'),
  ('protocol_single_site_shortcut',lambda r:edit(r,'config/release/OPERATIONAL_TIMING_CALIBRATION_PROTOCOL.json',lambda d:d['required_study_design'].__setitem__('versioned_multisite_dataset',False)),'operational timing study-design requirement disabled:versioned_multisite_dataset'),
  ('protocol_auto_promotion',lambda r:edit(r,'config/release/OPERATIONAL_TIMING_CALIBRATION_PROTOCOL.json',lambda d:d['promotion_rules'].__setitem__('automatic_promotion_permitted',True)),'automatic clinical timing promotion enabled'),
 ]
 results=[]
 for cid,mut,needle in cases:
  with tempfile.TemporaryDirectory(prefix='asklepios-timing-') as td:
   repo=Path(td)/'repo';shutil.copytree(root,repo,ignore=shutil.ignore_patterns('.git','node_modules','.asklepios','dist'))
   (repo/'reports').mkdir(exist_ok=True);(repo/'reports/simulation-timing-runtime.json').write_text(json.dumps(runtime_report(),indent=2,sort_keys=True)+"\n")
   if mut:mut(repo)
   obs=validate(repo,'final');errs=obs.get('errors',[])
   if mut is None:ok=obs.get('classification')==PASS;cls=PASS if ok else FAIL
   else:ok=obs.get('classification')==FAIL and any(needle in e for e in errs);cls=EXPECTED_REJECTION if ok else FAIL
   results.append(case_result(cid,cls,errors=[] if ok else errs,required_error=needle,observed_classification=obs.get('classification')))
 cls=suite_classification(results);return {'schema_version':'1.0.0','classification':cls,'status':cls,'cases':len(results),'results':results,'errors':[] if cls==PASS else ['simulation timing mutation suite failed']}

def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=Path('.'));p.add_argument('--json-output',type=Path,default=Path('reports/simulation-timing-mutations.json'));a=p.parse_args();r=run(a.repo.resolve());(a.repo.resolve()/a.json_output).parent.mkdir(parents=True,exist_ok=True);(a.repo.resolve()/a.json_output).write_text(json.dumps(r,indent=2,sort_keys=True)+"\n");print(json.dumps(r,indent=2,sort_keys=True));return exit_code(r['classification'])
if __name__=='__main__':raise SystemExit(main())
