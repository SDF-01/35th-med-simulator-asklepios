#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPORT = Path('reports/facility-decision-scientific-admission.json')
PROFILE = Path('config/facility-decision/ASK-D-001.json')
BOUNDARIES = Path('config/facility-decision/VALIDITY_BOUNDARIES.json')
PROVENANCE_BUILDER = Path('scripts/build_facility_decision_provenance.py')
ACCESSIBILITY_PROTOCOL = Path('docs/FACILITY_DECISION_ACCESSIBILITY_PROTOCOL.md')
PUBLIC_TEXT_PATHS = (
    Path('README.md'),
    Path('examples/facility-decision/README.md'),
    Path('docs/FACILITY_DECISION_VALIDITY_BOUNDARIES.md'),
)

EXPECTED_STATUS = {
    'operational_calibration': 'NOT_CALIBRATED',
    'treatment_legitimacy': 'BLOCKED_NO_ADJUDICATED_CONCRETE_TREATMENT',
    'human_team_behavior': 'STRUCTURAL_ONLY_NOT_CALIBRATED',
    'patient_dynamics': 'SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY',
    'claim_entailment': 'IDENTITY_PROVENANCE_ONLY',
    'causal_aar': 'SEQUENCE_RECONSTRUCTION_ONLY',
    'executable_formal_refinement': 'SAMPLED_DIFFERENTIAL_PLUS_FORMAL_MODEL',
    'accessibility': 'AUTOMATED_SOURCE_GATES_PASS_MANUAL_VALIDATION_REQUIRED',
    'production_operations': 'REPRODUCIBLE_BUILD_AND_SIGNED_PROVENANCE_PENDING',
}

UNSUPPORTED_CONCRETE_KEYS = {
    'medication', 'medication_name', 'drug', 'drug_name', 'dose', 'dose_unit',
    'route', 'procedure', 'procedure_code', 'device_setting', 'remove_now',
    'conversion_time', 'replacement_device',
}
CALIBRATION_ONLY_KEYS = {
    'empirical_distribution', 'distribution_parameters', 'sample_size',
    'confidence_interval', 'calibration_dataset', 'held_out_metrics',
    'observed_probability', 'calibrated_probability',
}
HUMAN_CALIBRATION_KEYS = {
    'compliance_probability', 'message_loss_probability', 'response_probability',
    'behavioral_distribution', 'policy_accuracy', 'memory_error_rate',
}

CRITICAL_REQUIREMENTS = {
    'operational_calibration': {'versioned_dataset_identity', 'held_out_evaluation', 'uncertainty_interval', 'drift_monitoring_rule'},
    'treatment_legitimacy': {'exact_source_span_and_version', 'provider_scope_binding', 'patient_specific_eligibility', 'independent_attestation'},
    'human_team_behavior': {'versioned_behavioral_dataset', 'held_out_policy_evaluation', 'uncertainty_and_drift_monitoring'},
    'patient_dynamics': {'intervention_transition_model', 'held_out_trajectory_validation', 'uncertainty_envelope', 'safety_invariants'},
    'claim_entailment': {'atomic_claim', 'exact_source_span', 'contradiction_search', 'supersession_search', 'independent_attestation'},
    'causal_aar': {'structural_causal_model', 'identification_assumptions', 'same_exogenous_state_counterfactual_replay', 'sensitivity_analysis'},
    'executable_formal_refinement': {'formal_transition_semantics', 'total_refinement_relation', 'proof_for_all_reachable_transitions', 'independent_kernel_acceptance'},
    'accessibility': {'manual_keyboard_protocol', 'screen_reader_protocol', 'representative_user_validation', 'documented_residual_risk'},
    'production_operations': {'two_build_reproducibility', 'artifact_signature', 'canary_and_rollback', 'telemetry_and_incident_replay'},
}

CAUSAL_FORBIDDEN = (
    re.compile(r'(?i)\b(?:this|the)\s+(?:learner\s+)?(?:decision|action)\s+caused\s+(?:the|this)\s+outcome\b'),
    re.compile(r'(?i)\bcausal effect (?:is|was|has been) (?:proven|established|validated)\b'),
    re.compile(r'(?i)\bwould have prevented the outcome\b'),
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def walk(value: Any, prefix: str = ''):
    if isinstance(value, dict):
        for key, child in value.items():
            current = f'{prefix}.{key}' if prefix else key
            yield current, key, child
            yield from walk(child, current)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            current = f'{prefix}[{index}]'
            yield from walk(child, current)


def validate(repo: Path) -> dict[str, Any]:
    errors: list[str] = []
    checks = 0
    domain_checks: dict[str, int] = {name: 0 for name in EXPECTED_STATUS}

    def check(condition: bool, message: str, domain: str) -> None:
        nonlocal checks
        checks += 1
        domain_checks[domain] += 1
        if not condition:
            errors.append(message)

    profile_path = repo / PROFILE
    boundary_path = repo / BOUNDARIES
    for path in (profile_path, boundary_path, repo / PROVENANCE_BUILDER, repo / ACCESSIBILITY_PROTOCOL):
        checks += 1
        if not path.is_file():
            errors.append(f'missing:{path.relative_to(repo).as_posix()}')
    if errors:
        return {
            'schema_version': '1.0.0', 'status': 'FAIL', 'checks': checks,
            'domain_checks': domain_checks, 'errors': sorted(set(errors)),
        }

    profile = load_json(profile_path)
    boundaries = load_json(boundary_path)
    domains = boundaries.get('domains', {})
    for domain, expected in EXPECTED_STATUS.items():
        check(domain in domains, f'validity domain missing:{domain}', domain)
        check(domains.get(domain, {}).get('status') == expected, f'validity status differs:{domain}', domain)
        requirements = domains.get(domain, {}).get('activation_requirements')
        check(isinstance(requirements, list) and len(requirements) >= 5, f'activation requirements insufficient:{domain}', domain)
        requirement_set = set(requirements) if isinstance(requirements, list) else set()
        for required in CRITICAL_REQUIREMENTS[domain]:
            check(required in requirement_set, f'critical activation requirement missing:{domain}:{required}', domain)

    authority = profile.get('authority', {})
    check(authority.get('patient_care_use') == 'PROHIBITED', 'patient-care authority escalated', 'treatment_legitimacy')
    check(authority.get('concrete_treatment_activation') is False, 'concrete treatment activation enabled', 'treatment_legitimacy')
    check(authority.get('operational_parameters_calibrated') is False, 'operational parameters falsely calibrated', 'operational_calibration')

    operational = profile.get('operational_model', {})
    check(operational.get('information_staleness_calibration_status') == 'NOT_CALIBRATED', 'information staleness falsely calibrated', 'operational_calibration')
    resources = operational.get('resources', [])
    check(isinstance(resources, list) and len(resources) >= 3, 'operational resource inventory incomplete', 'operational_calibration')
    for resource in resources:
        rid = resource.get('resource_id', '<unknown>')
        check(resource.get('calibration_status') == 'NOT_CALIBRATED', f'resource falsely calibrated:{rid}', 'operational_calibration')
        check(isinstance(resource.get('capacity'), int) and resource.get('capacity', 0) > 0, f'resource capacity invalid:{rid}', 'operational_calibration')
        check(resource.get('queue_policy') in {'FIFO'}, f'unreviewed resource queue policy:{rid}', 'operational_calibration')
    for event in operational.get('world_events', []):
        eid = event.get('event_id', '<unknown>')
        check(event.get('calibration_status') == 'NOT_CALIBRATED', f'world event falsely calibrated:{eid}', 'operational_calibration')
        check('trigger_decision_id' not in event and 'trigger_action_id' not in event, f'world event action-coupled:{eid}', 'operational_calibration')
    for path, key, _ in walk(operational):
        check(key not in CALIBRATION_ONLY_KEYS, f'undeclared empirical calibration field:{path}', 'operational_calibration')

    patient = operational.get('patient_observation_policy', {})
    check(patient.get('mode') == 'SOURCE_BOUND_OBSERVATIONS_ONLY', 'patient observation mode escalated', 'patient_dynamics')
    check(patient.get('dynamic_physiology_validated') is False, 'dynamic physiology falsely validated', 'patient_dynamics')
    check(patient.get('latent_state_exposed_to_learner') is False, 'latent patient state exposed', 'patient_dynamics')

    policies = profile.get('treatment_policies', [])
    check(isinstance(policies, list) and len(policies) == 2, 'treatment policy inventory differs', 'treatment_legitimacy')
    for policy in policies:
        tid = policy.get('treatment_id', '<unknown>')
        check(policy.get('concrete_treatment_allowed') is False, f'concrete treatment admitted:{tid}', 'treatment_legitimacy')
        check(policy.get('governing_rule_status') == 'NOT_ADJUDICATED', f'treatment rule self-adjudicated:{tid}', 'treatment_legitimacy')
        check(policy.get('effect_model_status') == 'BLOCKED', f'treatment effect model activated:{tid}', 'treatment_legitimacy')
        requirements = set(policy.get('activation_requirements_for_future_concrete_content', []))
        check('exact_governing_source_locator' in requirements, f'exact source requirement missing:{tid}', 'treatment_legitimacy')
        check('provider_scope_binding' in requirements, f'provider scope requirement missing:{tid}', 'treatment_legitimacy')
        forbidden = set(policy.get('forbidden_submission_keys', []))
        check(bool(forbidden), f'forbidden treatment field inventory empty:{tid}', 'treatment_legitimacy')
    for path, key, value in walk(profile.get('decisions', [])):
        if key in UNSUPPORTED_CONCRETE_KEYS:
            check(False, f'concrete treatment field declared:{path}', 'treatment_legitimacy')
        if key == 'field_id' and str(value) in UNSUPPORTED_CONCRETE_KEYS:
            check(False, f'concrete treatment field declared:{path}:{value}', 'treatment_legitimacy')
        if key in HUMAN_CALIBRATION_KEYS:
            check(False, f'undeclared human-behavior calibration field:{path}', 'human_team_behavior')
        if key in {'entailment_status', 'support_status', 'adjudication_status'} and str(value).upper() in {'SUPPORTS', 'ADJUDICATED', 'VERIFIED'}:
            check(False, f'unadjudicated claim promoted:{path}', 'claim_entailment')

    diagnostics = profile.get('diagnostic_catalog', [])
    check(isinstance(diagnostics, list) and len(diagnostics) == 2, 'diagnostic catalog differs', 'claim_entailment')
    for item in diagnostics:
        result_id = item.get('result_id', '<unknown>')
        pointer = item.get('source_pointer', '')
        check(isinstance(pointer, str) and pointer.startswith('src/content/scenarios.ts#ASK-D-001.'), f'diagnostic source pointer outside protected template:{result_id}', 'claim_entailment')
        check(item.get('result_granularity') in {'SOURCE_DIAGNOSIS_SUMMARY_ONLY', 'SOURCE_QUALITATIVE_SUMMARY_ONLY'}, f'diagnostic result granularity escalated:{result_id}', 'claim_entailment')
        check(isinstance(item.get('limitation'), str) and len(item.get('limitation', '')) >= 20, f'diagnostic limitation missing:{result_id}', 'claim_entailment')
        check('entailment_status' not in item, f'diagnostic entailment self-certified:{result_id}', 'claim_entailment')

    profile_keys = [(path, key) for path, key, _ in walk(profile)]
    for path, key in profile_keys:
        check(key not in HUMAN_CALIBRATION_KEYS, f'undeclared human-behavior calibration field:{path}', 'human_team_behavior')
    ui_modes = profile.get('ui_modes', {})
    check(set(ui_modes) == {'learner_assessment', 'learner_teaching', 'instructor', 'stakeholder_demo'}, 'role projection inventory differs', 'human_team_behavior')
    learner = ui_modes.get('learner_assessment', {})
    for key in ('show_live_score', 'show_source_points', 'show_source_origin', 'show_provenance', 'show_wit', 'show_autoplay', 'show_completed_replay', 'show_correctness_labels'):
        check(learner.get(key) is False, f'learner answer/evaluator leakage:{key}', 'human_team_behavior')

    for rel in PUBLIC_TEXT_PATHS:
        path = repo / rel
        check(path.is_file(), f'public validity text missing:{rel.as_posix()}', 'causal_aar')
        if path.is_file():
            text = path.read_text(encoding='utf-8')
            for pattern in CAUSAL_FORBIDDEN:
                check(pattern.search(text) is None, f'unsupported causal claim:{rel.as_posix()}:{pattern.pattern}', 'causal_aar')

    accessibility = (repo / ACCESSIBILITY_PROTOCOL).read_text(encoding='utf-8')
    check('MANUAL_ACCESSIBILITY_VALIDATION_REQUIRED' in accessibility, 'manual accessibility boundary missing', 'accessibility')
    check('must not claim WCAG 2.2 AA conformance' in accessibility, 'unsupported WCAG boundary missing', 'accessibility')

    provenance_builder = (repo / PROVENANCE_BUILDER).read_text(encoding='utf-8')
    check("'signature_status': 'UNSIGNED'" in provenance_builder, 'provenance builder signature state differs', 'production_operations')
    check("'claim_scope': 'BUILD_IDENTITY_ONLY'" in provenance_builder, 'provenance claim scope differs', 'production_operations')
    check('SIGNED_PROVENANCE' not in provenance_builder, 'unsigned builder claims signed provenance', 'production_operations')

    differential_path = repo / 'reports/facility-decision-differential.json'
    check(differential_path.is_file(), 'differential report missing', 'executable_formal_refinement')
    if differential_path.is_file():
        differential = load_json(differential_path)
        check(differential.get('status') == 'PASS', 'differential report not PASS', 'executable_formal_refinement')
        check(differential.get('fixtures_observed') == differential.get('fixtures_declared') == 300, 'differential sample differs', 'executable_formal_refinement')
    check((repo / 'formal/ScenarioContracts/FacilityDecisionIntegrity.lean').is_file(), 'formal model missing', 'executable_formal_refinement')
    check((repo / 'formal/FACILITY_DECISION_INTEGRITY_TRUST_MANIFEST.json').is_file(), 'formal trust manifest missing', 'executable_formal_refinement')

    report = {
        'schema_version': '1.0.0',
        'status': 'PASS' if not errors else 'FAIL',
        'checks': checks,
        'domain_checks': domain_checks,
        'domain_statuses': {name: domains.get(name, {}).get('status') for name in EXPECTED_STATUS},
        'errors': sorted(set(errors)),
        'truth_boundary': 'Software assurance does not promote scientific, clinical, causal, accessibility, or deployment claims.',
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--json-output', default=REPORT.as_posix())
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    report = validate(repo)
    output = repo / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['status'] == 'PASS' else 3


if __name__ == '__main__':
    raise SystemExit(main())
