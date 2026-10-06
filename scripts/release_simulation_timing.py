#!/usr/bin/env python3
"""Validate simulation clock semantics separately from clinical timing claims."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
from release_graph_core import load_graph,read_json,write_json
from release_policy_common import load_release_json
from release_result import FAIL,INTERNAL_ERROR,PASS,exit_code

POLICY='config/release/SIMULATION_TIMING_POLICY.json'
CALIBRATION_PROTOCOL='config/release/OPERATIONAL_TIMING_CALIBRATION_PROTOCOL.json'
SOURCE_OUTPUT=Path('reports/simulation-timing-policy.json')
FINAL_OUTPUT=Path('reports/simulation-timing-assurance.json')
RUNTIME='reports/simulation-timing-runtime.json'

def validate(root:Path,mode:str)->dict[str,Any]:
 root=root.resolve();errors=[];checks=0
 def req(cond:bool,msg:str):
  nonlocal checks;checks+=1
  if not cond:errors.append(msg)
 try:
  policy=load_release_json(root,POLICY,errors);protocol=load_release_json(root,CALIBRATION_PROTOCOL,errors);graph=load_graph(root)
  if policy is None:raise ValueError('timing policy missing')
  if protocol is None:raise ValueError('operational timing calibration protocol missing')
  req(policy.get('schema_version')=='1.0.0','timing policy schema differs')
  domains=policy.get('clock_domains',{})
  logical=domains.get('simulation_logical_clock',{})
  req(logical.get('status')=='VALIDATED_FOR_DETERMINISTIC_SIMULATION','simulation logical clock status differs')
  req(logical.get('semantics')=='monotonic_discrete_logical_time','simulation clock semantics differ')
  req(logical.get('early_fire_tolerance_seconds')==0,'early-fire tolerance weakened')
  req(logical.get('duplicate_fire_tolerance')==0,'duplicate-fire tolerance weakened')
  req(logical.get('action_identity_independence_required') is True,'action-identity independence disabled')
  clinical=domains.get('real_world_clinical_operational_timing',{})
  req(clinical.get('status')=='NOT_CALIBRATED','clinical operational timing was promoted')
  req(clinical.get('transferability')=='NOT_ESTABLISHED','clinical timing transferability was promoted')
  req(len(clinical.get('required_before_promotion',[]))>=7,'clinical timing promotion evidence weakened')
  req(protocol.get('schema_version')=='1.0.0','operational timing calibration protocol schema differs')
  req(protocol.get('current_status')=='NOT_CALIBRATED','operational timing calibration protocol was promoted')
  req(protocol.get('current_transferability')=='NOT_ESTABLISHED','operational timing transferability was promoted')
  req(protocol.get('scope')=='FUTURE_REAL_WORLD_CLINICAL_TIMING_TRANSFER_CLAIMS','operational timing protocol scope differs')
  req(protocol.get('simulation_release_dependency')=='NOT_REQUIRED_FOR_PRODUCTION_HEALTHCARE_SIMULATION_SOFTWARE_READINESS','clinical timing was made a simulation release dependency')
  req(len(protocol.get('prohibited_shortcuts',[]))>=6,'operational timing shortcut prohibition weakened')
  design=protocol.get('required_study_design',{})
  for key in ('prospective_protocol','versioned_multisite_dataset','independent_holdout','temporal_holdout','site_level_holdout','predefined_inclusion_exclusion','missingness_analysis','data_quality_audit','independent_sme_approval'):
   req(design.get(key) is True,f'operational timing study-design requirement disabled:{key}')
  req(len(protocol.get('required_dataset_manifest',[]))>=9,'operational timing dataset manifest weakened')
  req(len(protocol.get('required_estimands',[]))>=6,'operational timing estimand inventory weakened')
  uncertainty=protocol.get('required_uncertainty',{})
  req(uncertainty.get('confidence_level')==0.95,'operational timing confidence level differs')
  req(uncertainty.get('cluster_by_site') is True,'operational timing site clustering disabled')
  validation=protocol.get('required_validation',{})
  for key in ('held_out_calibration_error','coverage_of_prediction_intervals','sensitivity_to_missingness','sensitivity_to_outliers','distribution_shift_analysis','external_reproduction'):
   req(validation.get(key) is True,f'operational timing validation requirement disabled:{key}')
  promotion=protocol.get('promotion_rules',{})
  req(promotion.get('automatic_promotion_permitted') is False,'automatic clinical timing promotion enabled')
  req(promotion.get('independent_review_complete') is True,'independent clinical timing review requirement disabled')
  perf=domains.get('software_response_time',{})
  req(perf.get('status')=='ENGINEERING_BUDGET_REQUIRES_RUNTIME_EVIDENCE','response-time evidence boundary differs')
  req(perf.get('measurement_clock')=='monotonic_high_resolution_clock','response-time clock differs')
  req(isinstance(perf.get('warmup_iterations'),int) and perf['warmup_iterations']>=100,'timing warmup weakened')
  req(isinstance(perf.get('measured_iterations'),int) and perf['measured_iterations']>=1000,'timing sample weakened')
  budgets=perf.get('budgets_ms',{})
  req(0 < budgets.get('p50',0) <= budgets.get('p95',0) <= budgets.get('p99',0),'response-time budgets invalid')
  timed=policy.get('timed_events',[]);req(len(timed)==1,'timed event registry differs')
  record=timed[0] if timed else {}
  req(record.get('event_id')=='second_casualty_inbound','timed event identity differs')
  req(record.get('exercise_due_seconds')==240,'timed event due value differs')
  req(record.get('simulation_status')=='EXERCISE_SCHEDULE_ENGINE_VALIDATED','simulation schedule status differs')
  req(record.get('clinical_calibration_status')=='NOT_CALIBRATED','timed event clinically promoted')
  req(record.get('must_be_action_independent') is True,'timed event action independence removed')
  req(record.get('must_fire_once') is True,'timed event exactly-once requirement removed')
  facility=read_json(root/'config/facility-arrival/ASK-D-001.json')
  event=next((e for e in facility.get('events',[]) if e.get('event_id')=='second_casualty_inbound'),None)
  req(event is not None,'facility timed event missing')
  req((event or {}).get('trigger')=={'kind':'elapsed_time_due','at_elapsed_seconds':240},'facility timed event binding differs')
  params=facility.get('parameters',{})
  req(params.get('diagnostic_delay_seconds',{}).get('value')==180,'diagnostic exercise delay differs')
  req(params.get('diagnostic_delay_seconds',{}).get('calibration_status')=='NOT_CALIBRATED','diagnostic delay clinically promoted')
  req(params.get('timeout_seconds',{}).get('value')==1200,'source timeout differs')
  decision=read_json(root/'config/facility-decision/ASK-D-001.json')
  world=decision.get('operational_model',{}).get('world_events',[])
  decision_event=next((e for e in world if e.get('event_id')=='second_casualty_inbound'),None)
  req(decision_event is not None,'decision timing record missing')
  req((decision_event or {}).get('at_elapsed_seconds')==240,'facility and decision event times disagree')
  req((decision_event or {}).get('calibration_status')=='NOT_CALIBRATED','decision timing clinically promoted')
  truth=graph.get('truth_boundaries',{})
  req(truth.get('simulation_logical_timing')=='VALIDATED_FOR_DETERMINISTIC_SIMULATION','graph simulation timing boundary differs')
  req(truth.get('clinical_operational_timing')=='NOT_CALIBRATED','graph clinical timing boundary differs')
  req(truth.get('operational_timing')=='NOT_CALIBRATED','legacy graph timing boundary changed')
  runtime_summary=None
  if mode=='final':
   runtime=read_json(root/RUNTIME);runtime_summary=runtime
   req(str(runtime.get('classification',runtime.get('status')))=='PASS','simulation timing runtime report not PASS')
   req(runtime.get('clinical_timing_calibrated') is False,'runtime report promoted clinical timing')
   for name in ('canonical','alternate'):
    item=runtime.get(name,{})
    req(item.get('event_count')==1,f'{name} clock event did not fire exactly once')
    req(item.get('fired_system_events_count')==1,f'{name} final event count differs')
    req(item.get('early_fire') is False,f'{name} clock event fired early')
    req(isinstance(item.get('completed_at_seconds'),int) and item['completed_at_seconds']>=240,f'{name} clock event time invalid')
   req(runtime.get('action_identity_independent') is True,'runtime event remained action-coupled')
   canonical_runtime=runtime.get('canonical',{})
   alternate_runtime=runtime.get('alternate',{})
   req(canonical_runtime.get('triggering_action_id') is None and alternate_runtime.get('triggering_action_id') is None,'runtime system event retained an action identity')
   req(isinstance(canonical_runtime.get('preceding_action_id'),str) and isinstance(alternate_runtime.get('preceding_action_id'),str),'runtime preceding action evidence missing')
   req(canonical_runtime.get('preceding_action_id')!=alternate_runtime.get('preceding_action_id'),'runtime action identity comparison failed')
   req(canonical_runtime.get('completed_at_seconds')==alternate_runtime.get('completed_at_seconds'),'runtime event time differs across valid orderings')
   response=runtime.get('response_time',{})
   req(response.get('iterations',0)>=perf.get('measured_iterations',1000),'runtime benchmark sample too small')
   req(response.get('p50_ms',float('inf'))<=budgets.get('p50',0),'runtime p50 budget exceeded')
   req(response.get('p95_ms',float('inf'))<=budgets.get('p95',0),'runtime p95 budget exceeded')
   req(response.get('p99_ms',float('inf'))<=budgets.get('p99',0),'runtime p99 budget exceeded')
  classification=PASS if not errors else FAIL
  runtime_pass = mode=='final' and classification==PASS
  logical_status = 'VALIDATED_FOR_DETERMINISTIC_SIMULATION' if classification==PASS else 'NOT_ESTABLISHED'
  return {
   'schema_version':'1.0.0',
   'classification':classification,
   'status':classification,
   'mode':mode,
   'checks':checks,
   'simulation_logical_clock':logical_status,
   'simulation_logical_timing':logical_status,
   'software_response_time_evidence':'PASS' if runtime_pass else 'REQUIRES_RUNTIME_EVIDENCE',
   'response_time_budgets_met':runtime_pass,
   'clinical_operational_timing':'NOT_CALIBRATED',
   'clinical_timing_transferability':'NOT_ESTABLISHED',
   'clinical_timing_calibrated':False,
   'clinical_timing_calibration_protocol':CALIBRATION_PROTOCOL,
   'runtime_report':RUNTIME if runtime_summary else None,
   'errors':sorted(set(errors)),
  }
 except Exception as exc:
  return {'schema_version':'1.0.0','classification':INTERNAL_ERROR,'status':INTERNAL_ERROR,'mode':mode,'checks':checks,'errors':sorted(set(errors+[f'{type(exc).__name__}:{exc}']))}

def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=Path('.'));p.add_argument('--mode',choices=['source','final'],default='source');p.add_argument('--json-output',type=Path);a=p.parse_args();root=a.repo.resolve();report=validate(root,a.mode);out=a.json_output or (FINAL_OUTPUT if a.mode=='final' else SOURCE_OUTPUT);write_json(root/out,report);print(json.dumps(report,indent=2,sort_keys=True));return exit_code(report['classification'])
if __name__=='__main__':raise SystemExit(main())
