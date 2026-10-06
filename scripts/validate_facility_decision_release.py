#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPORT = Path('reports/facility-decision-release.json')
EXPECTED_MUTATIONS = {
    'patient_care_authority_escalation_rehashed', 'concrete_treatment_activation_rehashed',
    'operational_calibration_promotion_rehashed', 'learner_live_score_leak_rehashed',
    'learner_source_points_leak_rehashed', 'learner_provenance_leak_rehashed',
    'learner_wit_leak_rehashed', 'learner_autoplay_leak_rehashed',
    'critical_source_contract_removed_rehashed', 'source_contract_duplicated_rehashed',
    'concrete_medication_field_declared_rehashed', 'pain_policy_activated_rehashed',
    'pain_forbidden_key_removed_rehashed', 'world_event_action_coupled_rehashed',
    'world_event_calibrated_rehashed', 'resource_zero_capacity_rehashed',
    'resource_calibration_promotion_rehashed', 'dynamic_physiology_false_validation_rehashed',
    'latent_patient_state_leak_rehashed', 'high_risk_repeatability_escalation_rehashed',
    'treatment_rule_self_adjudication_rehashed', 'treatment_effect_model_activation_rehashed',
    'ordered_pair_obligations_weakened_rehashed', 'reference_sequences_collapsed_rehashed',
    'handoff_ack_removed_rehashed', 'handoff_confirmation_weakened_rehashed',
    'diagnostic_order_producer_removed_rehashed', 'diagnostic_result_requirement_removed_rehashed',
    'high_risk_answer_label_leak_rehashed', 'diagnostic_source_path_traversal_rehashed',
    'duplicate_decision_rehashed', 'source_action_inventory_changed', 'stale_generated_typescript',
    'checker_internal_error_is_not_rejection',
}
EXPECTED_ROLE_ROUTES = {
    '/examples/facility-decision': 'FacilityDecisionIntegrityPage',
    '/examples/facility-decision/learner': 'FacilityDecisionLearnerPage',
    '/examples/facility-decision/teaching': 'FacilityDecisionTeachingPage',
    '/examples/facility-decision/instructor': 'FacilityDecisionInstructorPage',
    '/examples/facility-decision/demo': 'FacilityDecisionDemoPage',
}
REQUIRED_REPORTS = {
    'integrity': Path('reports/facility-decision-integrity-python.json'),
    'mutations': Path('reports/facility-decision-mutations.json'),
    'sequence': Path('reports/facility-decision-sequence-assurance.json'),
    'states': Path('reports/facility-decision-state-exploration.json'),
    'differential': Path('reports/facility-decision-differential.json'),
    'artifacts_python': Path('reports/facility-decision-artifacts-python.json'),
    'artifacts_node': Path('reports/facility-decision-artifacts-node.json'),
    'artifact_mutations': Path('reports/facility-decision-artifact-mutations.json'),
    'roles': Path('reports/facility-decision-role-boundaries.json'),
    'role_mutations': Path('reports/facility-decision-role-boundary-mutations.json'),
    'accessibility': Path('reports/facility-decision-accessibility.json'),
    'accessibility_mutations': Path('reports/facility-decision-accessibility-mutations.json'),
    'validity': Path('reports/facility-decision-validity-boundaries.json'),
    'validity_mutations': Path('reports/facility-decision-validity-boundary-mutations.json'),
    'scientific_admission': Path('reports/facility-decision-scientific-admission.json'),
    'scientific_admission_mutations': Path('reports/facility-decision-scientific-admission-mutations.json'),
    'evidence_promotion': Path('reports/facility-decision-evidence-promotion.json'),
    'evidence_promotion_mutations': Path('reports/facility-decision-evidence-promotion-mutations.json'),
    'formal_static': Path('reports/facility-decision-formal-static.json'),
    'release_static': Path('reports/facility-decision-release-static.json'),
    'release_static_mutations': Path('reports/facility-decision-release-static-mutations.json'),
}
LIVE_REPORTS = {
    'axiom': Path('reports/facility-decision-axiom-check.json'),
    'reproducibility': Path('reports/facility-decision-build-reproducibility.json'),
    'provenance': Path('reports/facility-decision-build-provenance.json'),
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def walk_keys(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--mode', choices=['source-preflight','release'], default='release')
    parser.add_argument('--json-output', default=REPORT.as_posix())
    args=parser.parse_args()
    repo=Path(args.repo).resolve(); errors=[]; checks=0
    def check(condition: bool, message: str):
        nonlocal checks; checks += 1
        if not condition: errors.append(message)

    profile_path=repo/'config/facility-decision/ASK-D-001.json'
    boundary_path=repo/'config/facility-decision/VALIDITY_BOUNDARIES.json'
    facility_spec_path=repo/'config/facility-arrival/ASK-D-001.json'
    manifest_path=repo/'examples/facility-decision/manifest.json'
    reference_path=repo/'examples/facility-decision/reference-session.json'
    alternate_path=repo/'examples/facility-decision/alternate-session.json'
    for path in (profile_path,boundary_path,facility_spec_path,manifest_path,reference_path,alternate_path,repo/'package-lock.json',repo/'lean-toolchain',repo/'lake-manifest.json'):
        check(path.is_file(), f'missing:{path.relative_to(repo).as_posix()}')
    profile=load(profile_path) if profile_path.is_file() else {}
    boundary=load(boundary_path) if boundary_path.is_file() else {}
    facility_spec=load(facility_spec_path) if facility_spec_path.is_file() else {}
    manifest=load(manifest_path) if manifest_path.is_file() else {}
    reference=load(reference_path) if reference_path.is_file() else {}
    alternate=load(alternate_path) if alternate_path.is_file() else {}

    facility_events={event.get('event_id'): event for event in facility_spec.get('events',[]) if isinstance(event,dict)}
    second_event=facility_events.get('second_casualty_inbound',{})
    check(second_event.get('trigger')=={'kind':'elapsed_time_due','at_elapsed_seconds':240},'second-casualty event is not the reviewed clock-driven trigger')
    decision_events={event.get('event_id'): event for event in profile.get('operational_model',{}).get('world_events',[]) if isinstance(event,dict)}
    decision_second=decision_events.get('second_casualty_inbound',{})
    check(decision_second.get('at_elapsed_seconds')==240,'decision world-event time differs')
    check(decision_second.get('calibration_status')=='NOT_CALIBRATED','decision world-event falsely calibrated')
    for label,session in (('canonical',reference),('alternate',alternate)):
        event_rows=[row for row in session.get('facility_session',{}).get('transitions',[]) if row.get('event_id')=='second_casualty_inbound']
        check(len(event_rows)==1,f'{label} second-casualty event count differs')
        if len(event_rows)==1:
            row=event_rows[0]
            check(row.get('completed_at_seconds',-1)>=240,f'{label} second-casualty event fired before clock due')
            check(row.get('action_id') is None and row.get('command_id') is None,f'{label} second-casualty event is learner-action coupled')

    authority=profile.get('authority',{})
    check(authority.get('patient_care_use')=='PROHIBITED','patient-care authority escalated')
    check(authority.get('concrete_treatment_activation') is False,'concrete treatment activated')
    check(authority.get('operational_parameters_calibrated') is False,'operational parameters falsely calibrated')
    for policy in profile.get('treatment_policies',[]):
        check(policy.get('concrete_treatment_allowed') is False,f'treatment activated:{policy.get("treatment_id")}')
        check(policy.get('governing_rule_status')=='NOT_ADJUDICATED',f'treatment self-adjudicated:{policy.get("treatment_id")}')
        check(policy.get('effect_model_status')=='BLOCKED',f'treatment effect activated:{policy.get("treatment_id")}')
    check(boundary.get('patient_care_use')=='PROHIBITED','validity boundary patient-care status')
    check(manifest.get('release_id')=='ASK-FACILITY-DECISION-RC3-6A','manifest release identity')
    for name,meta in manifest.get('files',{}).items():
        path=repo/'examples/facility-decision'/name
        check(path.is_file(),f'manifest file missing:{name}')
        if path.is_file():
            check(path.stat().st_size==meta.get('bytes'),f'manifest byte count:{name}')
            check(sha(path)==meta.get('sha256'),f'manifest hash:{name}')
    for name in ('learner-projection.json','teaching-projection.json'):
        path=repo/'examples/facility-decision'/name
        if path.is_file():
            keys=set(walk_keys(load(path)))
            forbidden={'normalized_source_score_bps','source_binding','facility_certificate','wit_observations','autoplay_available','completed_replay_available','branch_controls'}
            check(not keys.intersection(forbidden),f'learner projection leakage:{name}:{sorted(keys.intersection(forbidden))}')

    reports={}
    for key,rel in REQUIRED_REPORTS.items():
        path=repo/rel; check(path.is_file(),f'missing report:{rel.as_posix()}')
        if path.is_file():
            try: reports[key]=load(path)
            except Exception as exc: errors.append(f'invalid report:{rel.as_posix()}:{type(exc).__name__}')
    for key,data in reports.items(): check(data.get('status')=='PASS',f'report not PASS:{key}')
    if 'integrity' in reports:
        check(reports['integrity'].get('checks',0)>=150,'integrity check count weakened')
        check(reports['integrity'].get('source_actions_bound')==6,'source action coverage differs')
    if 'mutations' in reports:
        rows=reports['mutations'].get('results',[])
        ids={row.get('case_id') for row in rows[1:]}
        check(ids==EXPECTED_MUTATIONS,'semantic mutation inventory differs')
        check(reports['mutations'].get('accepted_forgery_count')==0,'semantic forgery accepted')
        check(reports['mutations'].get('unexpected_internal_errors')==0,'unexpected mutation checker error')
        check(reports['mutations'].get('globally_rehashed_attacks',0)>=30,'rehashed mutation coverage weakened')
    if 'sequence' in reports:
        check(reports['sequence'].get('covered_ordered_pairs')==reports['sequence'].get('required_ordered_pairs')==11,'ordered pair coverage differs')
        check(reports['sequence'].get('covered_ordered_triples')==reports['sequence'].get('required_ordered_triples')==5,'ordered triple coverage differs')
        check(reports['sequence'].get('successful_completion_traces',0)>=4,'valid sequence diversity weakened')
    if 'states' in reports:
        check(reports['states'].get('reachable_active_dead_ends')==0,'reachable active dead end')
        check(reports['states'].get('state_limit_reached') is False,'state exploration truncated')
        check(reports['states'].get('semantic_states',0)>=50_000,'state exploration unexpectedly small')
        check(set(reports['states'].get('named_terminal_witnesses',{}))=={'completed_canonical','completed_alternate','failed_discharge','failed_tourniquet','timeout'},'terminal witnesses differ')
    if 'differential' in reports:
        check(reports['differential'].get('fixtures_observed')==reports['differential'].get('fixtures_declared')==300,'differential fixture count differs')
        check(reports['differential'].get('errors')==[],'differential errors')
    if 'roles' in reports: check(reports['roles'].get('role_routes')==EXPECTED_ROLE_ROUTES,'role route inventory differs')
    if 'accessibility' in reports:
        check(reports['accessibility'].get('automated_source_status')=='PASS','accessibility source gate')
        check(reports['accessibility'].get('manual_accessibility_validation')=='REQUIRED_NOT_EXECUTED','manual accessibility truth boundary')
        check(reports['accessibility'].get('wcag_conformance_claim')=='NOT_MADE','unsupported WCAG claim')
    if 'validity' in reports:
        check(reports['validity'].get('checks',0)>=130,'validity boundary coverage weakened')
    if 'validity_mutations' in reports:
        check(reports['validity_mutations'].get('accepted_escalations')==0,'validity escalation accepted')
        check(reports['validity_mutations'].get('internal_errors')==0,'validity checker internal error')
    if 'scientific_admission' in reports:
        check(reports['scientific_admission'].get('checks',0)>=800,'scientific admission coverage weakened')
        check(reports['scientific_admission'].get('errors')==[],'scientific admission errors')
    if 'scientific_admission_mutations' in reports:
        check(reports['scientific_admission_mutations'].get('accepted_escalations')==0,'scientific claim escalation accepted')
        check(reports['scientific_admission_mutations'].get('internal_errors')==0,'scientific admission checker internal error')
        check(reports['scientific_admission_mutations'].get('attacks',0)>=16,'scientific admission attack inventory weakened')
    if 'evidence_promotion' in reports:
        check(reports['evidence_promotion'].get('admitted_clinical_rules') == 0, 'clinical rule admitted without completed promotion')
        check(reports['evidence_promotion'].get('activated_treatments') == 0, 'treatment activated without completed promotion')
        check(reports['evidence_promotion'].get('calibrated_parameters') == 0, 'parameter calibrated without completed promotion')
        check(reports['evidence_promotion'].get('located_official_documents', 0) >= 6, 'official source discovery inventory weakened')
        check(reports['evidence_promotion'].get('byte_bound_spans') == 0, 'span binding state unexpectedly promoted')
    if 'evidence_promotion_mutations' in reports:
        check(reports['evidence_promotion_mutations'].get('accepted_attacks') == 0, 'evidence promotion attack accepted')
        check(reports['evidence_promotion_mutations'].get('internal_errors') == 0, 'evidence promotion checker internal error')
        check(reports['evidence_promotion_mutations'].get('attacks', 0) >= 47, 'evidence promotion attack inventory weakened')
    if 'release_static' in reports:
        check(reports['release_static'].get('checks',0)>=60,'release static coverage weakened')
    if 'release_static_mutations' in reports:
        check(reports['release_static_mutations'].get('accepted_mutations')==0,'release policy mutation accepted')
        check(reports['release_static_mutations'].get('internal_errors')==0,'release static checker internal error')

    live={}
    if args.mode=='release':
        for key,rel in LIVE_REPORTS.items():
            path=repo/rel; check(path.is_file(),f'missing live report:{rel.as_posix()}')
            if path.is_file():
                try: live[key]=load(path)
                except Exception as exc: errors.append(f'invalid live report:{rel.as_posix()}:{type(exc).__name__}')
        if 'axiom' in live:
            check(live['axiom'].get('status')=='PASS','axiom audit failed')
            check(live['axiom'].get('theorems_expected')==live['axiom'].get('theorems_observed')==17,'formal theorem inventory differs')
            check(live['axiom'].get('errors')==[],'formal axiom errors')
        if 'reproducibility' in live:
            check(live['reproducibility'].get('status')=='PASS','build reproducibility failed')
            check(live['reproducibility'].get('files_compared',0)>0,'no build outputs compared')
            check(live['reproducibility'].get('errors')==[],'build reproducibility errors')
        if 'provenance' in live:
            verification=live['provenance'].get('asklepios_verification',{})
            check(verification.get('status')=='PASS','build provenance generation failed')
            check(verification.get('signature_status')=='UNSIGNED','unexpected signature state')
            check(verification.get('claim_scope')=='BUILD_IDENTITY_ONLY','provenance claim scope differs')
            check(live['provenance'].get('predicateType')=='https://slsa.dev/provenance/v1','provenance predicate differs')
            check(bool(live['provenance'].get('subject')),'provenance subjects missing')
    else:
        for rel in LIVE_REPORTS.values():
            check(not (repo/rel).is_symlink(),f'live report symlink forbidden:{rel.as_posix()}')

    status='PASS' if not errors and args.mode=='release' else ('READY_FOR_LIVE_GATES' if not errors else 'FAIL')
    report={
        'schema_version':'1.0.0','status':status,'mode':args.mode,'checks':checks,
        'release_id':'ASK-FACILITY-DECISION-RC3-6A','errors':sorted(set(errors)),
        'open_limits':{
            'operational_calibration':'NOT_CALIBRATED',
            'treatment_legitimacy':'NO_CONCRETE_TREATMENT_ADMITTED',
            'human_team_behavior':'STRUCTURAL_ONLY',
            'patient_dynamics':'SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY',
            'claim_entailment':'IDENTITY_PROVENANCE_ONLY',
            'causal_aar':'SEQUENCE_RECONSTRUCTION_ONLY',
            'executable_formal_refinement':'SAMPLED_DIFFERENTIAL_PLUS_FORMAL_MODEL',
            'manual_accessibility_validation':'REQUIRED',
            'signed_provenance':'PENDING',
        },
    }
    output=repo/args.json_output; output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n'); print(json.dumps(report,indent=2,sort_keys=True)); return 0 if status in {'PASS','READY_FOR_LIVE_GATES'} else 3


if __name__=='__main__': raise SystemExit(main())
