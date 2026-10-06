#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

BOUNDARY = Path('config/facility-decision/VALIDITY_BOUNDARIES.json')
PROFILE = Path('config/facility-decision/ASK-D-001.json')
REPORT = Path('reports/facility-decision-validity-boundaries.json')

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

MIN_REQUIREMENTS = {
    'operational_calibration': {
        'versioned_dataset_identity', 'held_out_evaluation', 'uncertainty_interval', 'drift_monitoring_rule'
    },
    'treatment_legitimacy': {
        'atomic_governing_claim', 'exact_source_span_and_version', 'provider_scope_binding',
        'patient_specific_eligibility', 'contraindication_logic', 'independent_attestation'
    },
    'human_team_behavior': {
        'role_specific_observation_model', 'message_delivery_and_acknowledgement_model',
        'bounded_memory_model', 'versioned_behavioral_dataset', 'held_out_policy_evaluation'
    },
    'patient_dynamics': {
        'declared_latent_state', 'observation_model', 'intervention_transition_model',
        'held_out_trajectory_validation', 'uncertainty_envelope', 'safety_invariants'
    },
    'claim_entailment': {
        'atomic_claim', 'exact_source_span', 'support_refute_insufficient_or_conflicting_label',
        'contradiction_search', 'supersession_search', 'independent_attestation'
    },
    'causal_aar': {
        'structural_causal_model', 'declared_exogenous_variables', 'identification_assumptions',
        'same_exogenous_state_counterfactual_replay', 'sensitivity_analysis'
    },
    'executable_formal_refinement': {
        'formal_transition_semantics', 'serialization_correspondence', 'total_refinement_relation',
        'proof_for_all_reachable_transitions', 'independent_kernel_acceptance'
    },
    'accessibility': {
        'manual_keyboard_protocol', 'screen_reader_protocol', 'contrast_and_reflow_review',
        'representative_user_validation', 'documented_residual_risk'
    },
    'production_operations': {
        'exact_commit_and_dependency_identity', 'two_build_reproducibility', 'slsa_shaped_provenance',
        'artifact_signature', 'sbom', 'canary_and_rollback', 'telemetry_and_incident_replay'
    },
}

FORBIDDEN_RELEASE_PHRASES = {
    'this learner decision caused the outcome',
    'clinically validated treatment recommendation',
    'validated continuous physiology',
    'wcag 2.2 aa compliant',
    'fully equivalent to the lean model',
    'empirically calibrated facility timing',
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--json-output', default=REPORT.as_posix())
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    errors: list[str] = []
    checks = 0

    def check(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    boundary_path = repo / BOUNDARY
    profile_path = repo / PROFILE
    check(boundary_path.is_file(), f'missing:{BOUNDARY.as_posix()}')
    check(profile_path.is_file(), f'missing:{PROFILE.as_posix()}')
    boundary: dict[str, Any] = load(boundary_path) if boundary_path.is_file() else {}
    profile: dict[str, Any] = load(profile_path) if profile_path.is_file() else {}

    check(boundary.get('schema_version') == '1.0.0', 'boundary schema version')
    check(boundary.get('release_id') == 'ASK-FACILITY-DECISION-RC3-6A', 'release identity')
    check(boundary.get('intended_use') == 'production_training_reference', 'intended use')
    check(boundary.get('patient_care_use') == 'PROHIBITED', 'boundary patient-care use')

    domains = boundary.get('domains')
    check(isinstance(domains, dict), 'domain map missing')
    domains = domains if isinstance(domains, dict) else {}
    check(set(domains) == set(EXPECTED_STATUS), 'validity domain inventory differs')
    for domain_id, expected_status in EXPECTED_STATUS.items():
        domain = domains.get(domain_id, {})
        check(isinstance(domain, dict), f'domain malformed:{domain_id}')
        if not isinstance(domain, dict):
            continue
        check(domain.get('status') == expected_status, f'status escalation or drift:{domain_id}')
        check(isinstance(domain.get('allowed_claim'), str) and len(domain.get('allowed_claim', '')) >= 20,
              f'allowed claim incomplete:{domain_id}')
        forbidden = domain.get('forbidden_claims')
        check(isinstance(forbidden, list) and len(forbidden) >= 2 and all(isinstance(x, str) and x for x in forbidden),
              f'forbidden claim inventory incomplete:{domain_id}')
        requirements = domain.get('activation_requirements')
        check(isinstance(requirements, list) and len(requirements) == len(set(requirements or [])),
              f'activation requirements malformed:{domain_id}')
        req_set = set(requirements or [])
        for required in MIN_REQUIREMENTS[domain_id]:
            check(required in req_set, f'activation requirement removed:{domain_id}:{required}')

    authority = profile.get('authority', {})
    operational = profile.get('operational_model', {})
    check(authority.get('patient_care_use') == 'PROHIBITED', 'profile patient-care use escalated')
    check(authority.get('concrete_treatment_activation') is False, 'concrete treatment activated')
    check(authority.get('operational_parameters_calibrated') is False, 'operational calibration falsely promoted')
    check(operational.get('information_staleness_calibration_status') == 'NOT_CALIBRATED', 'staleness calibration promoted')
    for item in operational.get('resources', []):
        check(item.get('calibration_status') == 'NOT_CALIBRATED', f'resource calibration promoted:{item.get("resource_id")}')
    for item in operational.get('world_events', []):
        check(item.get('calibration_status') == 'NOT_CALIBRATED', f'event calibration promoted:{item.get("event_id")}')
    observation = operational.get('patient_observation_policy', {})
    check(observation.get('dynamic_physiology_validated') is False, 'dynamic physiology falsely validated')
    check(observation.get('latent_state_exposed_to_learner') is False, 'latent patient state exposed')
    for policy in profile.get('treatment_policies', []):
        check(policy.get('concrete_treatment_allowed') is False, f'treatment activated:{policy.get("treatment_id")}')
        check(policy.get('governing_rule_status') == 'NOT_ADJUDICATED', f'treatment self-adjudicated:{policy.get("treatment_id")}')
        check(policy.get('effect_model_status') == 'BLOCKED', f'treatment effect activated:{policy.get("treatment_id")}')

    scan_paths = [
        Path('README.md'),
        Path('examples/facility-decision/README.md'),
        Path('docs/FACILITY_DECISION_ACCESSIBILITY_PROTOCOL.md'),
    ]
    for rel in scan_paths:
        path = repo / rel
        check(path.is_file(), f'missing public statement file:{rel.as_posix()}')
        if path.is_file():
            text = path.read_text(encoding='utf-8').lower()
            for phrase in FORBIDDEN_RELEASE_PHRASES:
                check(phrase not in text, f'unsupported public claim:{rel.as_posix()}:{phrase}')

    report = {
        'schema_version': '1.0.0',
        'status': 'PASS' if not errors else 'FAIL',
        'checks': checks,
        'release_id': boundary.get('release_id'),
        'domain_statuses': {key: domains.get(key, {}).get('status') for key in sorted(EXPECTED_STATUS)},
        'boundary_sha256': sha256(boundary_path) if boundary_path.is_file() else None,
        'profile_sha256': sha256(profile_path) if profile_path.is_file() else None,
        'errors': sorted(set(errors)),
    }
    output = repo / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 3


if __name__ == '__main__':
    raise SystemExit(main())
