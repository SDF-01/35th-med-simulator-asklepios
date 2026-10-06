#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REGISTRY = Path('config/facility-decision/EVIDENCE_PROMOTION_REGISTRY.json')
PROFILE = Path('config/facility-decision/ASK-D-001.json')
BOUNDARIES = Path('config/facility-decision/VALIDITY_BOUNDARIES.json')
REPORT = Path('reports/facility-decision-evidence-promotion.json')

CLAIM_STATES = [
    'DISCOVERED',
    'OFFICIAL_DOCUMENT_LOCATED',
    'IDENTITY_VERIFIED',
    'SPAN_LOCATED',
    'SPAN_BOUND',
    'APPLICABILITY_REVIEWED',
    'CONTRADICTION_CLEARED',
    'SUPERSESSION_CLEARED',
    'INDEPENDENTLY_ATTESTED',
    'ADMITTED',
]
CALIBRATION_STATES = [
    'EXERCISE_ASSUMPTION', 'DATASET_BOUND', 'MODEL_FIT', 'HOLDOUT_PASSED',
    'UNCERTAINTY_BOUND', 'DRIFT_RULE_DEFINED', 'CALIBRATED',
]
OFFICIAL_INDEX = 'https://jts.health.mil/index.cfm/CPGs/cpgs'
ALLOWED_OFFICIAL_HOSTS = {'jts.health.mil', 'books.allogy.com'}
ALLOWED_ALIAS_HOSTS = {'deployedmedicine.com'}
LOCATOR_KINDS = {
    'OFFICIAL_JTS_INDEX_AND_DOCUMENT_FIRST_PAGE',
    'OFFICIAL_JTS_INDEX_AND_ALLOGY_GUIDELINE',
}

EXPECTED_SOURCES: dict[str, dict[str, Any]] = {
    'jts-wartime-thoracic-injury-2018-12-26': {
        'title': 'Wartime Thoracic Injury',
        'version_date': '2018-12-26',
        'document_title_verified': 'Wartime Thoracic Injury',
        'document_version_verified': '2018-12-26',
        'expected_page_count': 31,
        'document_format': 'application/pdf',
        'candidate_for': ['thoracic_assessment', 'future_thoracic_treatment'],
    },
    'jts-pain-anxiety-delirium-2021-04-26': {
        'title': 'Pain, Anxiety and Delirium',
        'version_date': '2021-04-26',
        'document_title_verified': 'Pain, Anxiety and Delirium',
        'document_version_verified': '2021-04-26',
        'expected_page_count': 27,
        'document_format': 'application/pdf',
        'candidate_for': ['pain_management'],
        'rapid_update_date': '2025-03-27',
    },
    'jts-deployed-trauma-radiology-2017-05-13': {
        'title': 'Radiology: Imaging Trauma Patients in a Deployed Setting',
        'version_date': '2017-05-13',
        'document_title_verified': 'Radiology: Imaging Trauma Patients in a Deployed Setting',
        'document_version_verified': '2017-05-13',
        'expected_page_count': 11,
        'document_format': 'application/pdf',
        'candidate_for': ['chest_imaging_workflow'],
    },
    'jts-interfacility-transport-2025-12-12': {
        'title': 'Interfacility Transport of Patients Between Medical Treatment Facilities',
        'version_date': '2025-12-12',
        'document_title_verified': 'Interfacility Transport of Patients Between Medical Treatment Facilities',
        'document_version_verified': '2025-12-12',
        'expected_page_count': 19,
        'document_format': 'application/pdf',
        'candidate_for': ['disposition', 'closed_loop_transfer'],
    },
    'jts-tccc-guidelines-2026-05-01': {
        'title': 'Tactical Combat Casualty Care Guidelines',
        'version_date': '2026-05-01',
        'document_title_verified': 'TCCC Guidelines',
        'document_version_verified': '2026-05-01',
        'expected_page_count': None,
        'document_format': 'official_dynamic_guideline',
        'candidate_for': ['field_device_history', 'tourniquet_context_only'],
        'care_phase_limitation': 'PREHOSPITAL_SOURCE_REQUIRES_FACILITY_APPLICABILITY_REVIEW',
    },
    'jts-documentation-combat-casualty-care-2020-09-18': {
        'title': 'Documentation Requirements for Combat Casualty Care',
        'version_date': '2020-09-18',
        'document_title_verified': 'Documentation Requirements for Combat Casualty Care',
        'document_version_verified': '2020-09-18',
        'expected_page_count': 8,
        'document_format': 'application/pdf',
        'candidate_for': ['documentation', 'handoff_content'],
    },
}
EXPECTED_CLAIM_IDS = {
    'ask-d-001-hidden-finding-pneumothorax',
    'ask-d-001-hidden-finding-elevated-lactate',
}
EXPECTED_TREATMENTS: dict[str, list[str]] = {
    'pain_management': ['jts-pain-anxiety-delirium-2021-04-26'],
    'tourniquet_management': ['jts-tccc-guidelines-2026-05-01'],
}
EXPECTED_SPANS: dict[str, dict[str, Any]] = {
    'thoracic-injury-receiving-assessment-domains': {
        'source_id': 'jts-wartime-thoracic-injury-2018-12-26',
        'target': 'decision.receiving_primary_assessment',
        'page_number_1_based': 4,
        'section_heading': 'Diagnosis of Thoracic Injuries',
        'applicability_status': 'NOT_REVIEWED',
    },
    'deployed-imaging-trauma-workflow': {
        'source_id': 'jts-deployed-trauma-radiology-2017-05-13',
        'target': 'diagnostic_order.CHEST_IMAGING',
        'page_number_1_based': 2,
        'section_heading': 'Background / Imaging Evaluation',
        'applicability_status': 'NOT_REVIEWED',
    },
    'interfacility-stabilization-risk-mitigation': {
        'source_id': 'jts-interfacility-transport-2025-12-12',
        'target': 'decision.disposition_and_transfer',
        'page_number_1_based': 4,
        'section_heading': 'Patient Stabilization',
        'applicability_status': 'NOT_REVIEWED',
    },
    'interfacility-document-delivery': {
        'source_id': 'jts-interfacility-transport-2025-12-12',
        'target': 'handoff.transport_documentation',
        'page_number_1_based': 14,
        'section_heading': 'Documentation of Care',
        'applicability_status': 'NOT_REVIEWED',
    },
    'combat-casualty-documentation-continuity': {
        'source_id': 'jts-documentation-combat-casualty-care-2020-09-18',
        'target': 'decision.documentation_and_handoff',
        'page_number_1_based': 2,
        'section_heading': 'Background / Patient Care Documentation Guidelines',
        'applicability_status': 'NOT_REVIEWED',
    },
    'tccc-tourniquet-history-context': {
        'source_id': 'jts-tccc-guidelines-2026-05-01',
        'target': 'patient_history.field_tourniquet',
        'page_number_1_based': None,
        'section_heading': 'Tactical Field Care / Circulation / Tourniquet Reassessment',
        'applicability_status': 'PREHOSPITAL_SOURCE_REQUIRES_FACILITY_REVIEW',
    },
    'pain-role-three-emphasis': {
        'source_id': 'jts-pain-anxiety-delirium-2021-04-26',
        'target': 'treatment_slot.pain_management',
        'page_number_1_based': 1,
        'section_heading': 'Document Scope',
        'applicability_status': 'NOT_REVIEWED',
    },
}
EXPECTED_CALIBRATION = {
    'second_casualty_inbound_seconds': 240,
    'information_staleness_seconds': 180,
    'chest_imaging_service_seconds': 180,
    'laboratory_service_seconds': 180,
    'higher_level_care_coordination_seconds': 60,
}
ALLOWED_MODEL_FAMILIES = {
    'NONHOMOGENEOUS_POISSON_OR_EMPIRICAL_HAZARD',
    'POLICY_THRESHOLD_WITH_EMPIRICAL_SENSITIVITY_ANALYSIS',
    'SEMI_MARKOV_DURATION_OR_EMPIRICAL_SURVIVAL',
    'QUEUEING_NETWORK_SERVICE_TIME',
}
PROHIBITED_CONCRETE_KEYS = {
    'drug', 'drug_name', 'medication', 'medication_name', 'dose', 'dose_unit',
    'route', 'procedure', 'procedure_code', 'device_setting',
    'distribution_parameters', 'empirical_distribution', 'causal_effect',
    'quoted_text', 'verbatim_text', 'source_text', 'licensed_text',
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def walk(value: Any, prefix: str = ''):
    if isinstance(value, dict):
        for key, child in value.items():
            path = f'{prefix}.{key}' if prefix else key
            yield path, key, child
            yield from walk(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f'{prefix}[{index}]')


def safe_repo_pointer(value: str) -> bool:
    return (
        value.startswith('src/content/scenarios.ts#ASK-D-001.')
        and '\\' not in value
        and '..' not in value.split('#', 1)[0].split('/')
        and not value.startswith('/')
        and not re.match(r'^[A-Za-z]:', value)
    )


def valid_https_url(value: Any, allowed_hosts: set[str]) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == 'https' and parsed.hostname in allowed_hosts and bool(parsed.path)


def valid_utc_timestamp(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r'20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value) is not None


def profile_values(profile: dict[str, Any]) -> dict[str, int]:
    operational = profile.get('operational_model', {})
    resources = {row.get('resource_id'): row for row in operational.get('resources', [])}
    events = operational.get('world_events', [])
    event = next((row for row in events if row.get('event_id') == 'second_casualty_inbound'), {})
    return {
        'second_casualty_inbound_seconds': event.get('at_elapsed_seconds'),
        'information_staleness_seconds': operational.get('information_staleness_seconds'),
        'chest_imaging_service_seconds': resources.get('CHEST_IMAGING_SERVICE', {}).get('service_duration_seconds'),
        'laboratory_service_seconds': resources.get('LABORATORY_SERVICE', {}).get('service_duration_seconds'),
        'higher_level_care_coordination_seconds': resources.get('HIGHER_LEVEL_CARE_COORDINATION', {}).get('service_duration_seconds'),
    }


def validate(repo: Path) -> dict[str, Any]:
    errors: list[str] = []
    checks = 0

    def check(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    paths = [repo / REGISTRY, repo / PROFILE, repo / BOUNDARIES]
    for path in paths:
        check(path.is_file(), f'missing:{path.relative_to(repo).as_posix()}')
        check(not path.is_symlink(), f'symlink forbidden:{path.relative_to(repo).as_posix()}')
    if errors:
        return {'schema_version': '1.1.0', 'status': 'FAIL', 'checks': checks, 'errors': sorted(set(errors))}

    registry = load(repo / REGISTRY)
    profile = load(repo / PROFILE)
    boundaries = load(repo / BOUNDARIES)
    policy = registry.get('policy', {})

    check(registry.get('schema_version') == '1.1.0', 'registry schema differs')
    check(registry.get('release_id') == 'ASK-FACILITY-DECISION-RC3-6A', 'registry release differs')
    check(policy.get('claim_state_order') == CLAIM_STATES, 'claim state order differs')
    check(policy.get('calibration_state_order') == CALIBRATION_STATES, 'calibration state order differs')
    check(policy.get('independent_actor_required') is True, 'independent actor policy disabled')
    check(policy.get('monotonic_promotion_only') is True, 'monotonic promotion policy disabled')
    check(policy.get('treatment_activation_requires_claim_state') == 'ADMITTED', 'treatment activation threshold differs')
    check(policy.get('calibrated_parameter_requires_state') == 'CALIBRATED', 'calibration threshold differs')
    check('byte SHA-256' in str(policy.get('source_identity_rule')), 'source identity rule weakened')
    check('normalized exact-span digest' in str(policy.get('span_binding_rule')), 'span binding rule weakened')

    source_rows = registry.get('source_candidates', [])
    source_ids = [row.get('source_id') for row in source_rows]
    check(set(source_ids) == set(EXPECTED_SOURCES) and len(source_ids) == len(EXPECTED_SOURCES), 'source candidate inventory differs')
    check(len(source_ids) == len(set(source_ids)), 'duplicate source candidate')
    source_map = {row.get('source_id'): row for row in source_rows}
    for source_id, expected in EXPECTED_SOURCES.items():
        row = source_map.get(source_id, {})
        for field, value in expected.items():
            check(row.get(field) == value, f'source metadata differs:{source_id}:{field}')
        check(row.get('official_index_url') == OFFICIAL_INDEX, f'source index differs:{source_id}')
        check(valid_https_url(row.get('official_document_url'), ALLOWED_OFFICIAL_HOSTS), f'official document URL invalid:{source_id}')
        alias = row.get('official_pdf_alias_url')
        check(alias is None or valid_https_url(alias, ALLOWED_ALIAS_HOSTS), f'official alias URL invalid:{source_id}')
        check(row.get('claim_state') == 'OFFICIAL_DOCUMENT_LOCATED', f'source candidate state differs:{source_id}')
        check(row.get('exact_document_sha256') is None, f'unverified source digest declared:{source_id}')
        check(row.get('exact_locator') is None, f'unverified source locator declared:{source_id}')
        check(row.get('applicability_status') == 'NOT_REVIEWED', f'source applicability promoted:{source_id}')
        check(row.get('contradiction_status') == 'NOT_SEARCHED', f'source contradiction promoted:{source_id}')
        check(row.get('supersession_status') == 'NOT_CHECKED', f'source supersession promoted:{source_id}')
        check(row.get('clinical_authority') == 'NOT_GRANTED', f'source authority escalated:{source_id}')
        check(row.get('locator_evidence_kind') in LOCATOR_KINDS, f'locator evidence kind invalid:{source_id}')
        check(valid_utc_timestamp(row.get('locator_verified_at_utc')), f'locator timestamp invalid:{source_id}')
        check(row.get('identity_verification_status') == 'PENDING_BYTE_HASH', f'identity status differs:{source_id}')
        check(row.get('independent_identity_verifier_id') is None, f'unbound identity verifier declared:{source_id}')
        check(isinstance(row.get('candidate_for'), list) and row.get('candidate_for'), f'source use inventory empty:{source_id}')

    claims = registry.get('claim_records', [])
    claim_ids = [row.get('claim_id') for row in claims]
    check(set(claim_ids) == EXPECTED_CLAIM_IDS and len(claim_ids) == len(EXPECTED_CLAIM_IDS), 'claim inventory differs')
    check(len(claim_ids) == len(set(claim_ids)), 'duplicate claim record')
    for row in claims:
        claim_id = row.get('claim_id')
        check(row.get('source_kind') == 'REPOSITORY_TEMPLATE', f'claim source kind differs:{claim_id}')
        check(row.get('source_id') == 'ASK-D-001', f'claim source ID differs:{claim_id}')
        check(isinstance(row.get('atomic_claim'), str) and len(row.get('atomic_claim', '')) >= 30, f'claim is not atomic text:{claim_id}')
        check(safe_repo_pointer(str(row.get('source_locator', ''))), f'claim source path unsafe:{claim_id}')
        check(row.get('claim_state') == 'IDENTITY_VERIFIED', f'claim state escalated:{claim_id}')
        check(row.get('entailment_label') == 'NOT_ADJUDICATED', f'claim entailment self-certified:{claim_id}')
        check(row.get('applicability_status') == 'TEMPLATE_ONLY', f'claim applicability escalated:{claim_id}')
        check(row.get('contradiction_status') == 'NOT_SEARCHED', f'claim contradiction self-cleared:{claim_id}')
        check(row.get('supersession_status') == 'NOT_APPLICABLE_TO_TEMPLATE_IDENTITY', f'claim supersession state differs:{claim_id}')
        check(row.get('admitted_as_clinical_rule') is False, f'claim admitted as clinical rule:{claim_id}')
        verifier = row.get('independent_verifier_id')
        check(verifier is None or verifier != row.get('producer_id'), f'claim self-attested:{claim_id}')

    treatments = registry.get('treatment_slots', [])
    treatment_ids = [row.get('treatment_id') for row in treatments]
    check(set(treatment_ids) == set(EXPECTED_TREATMENTS) and len(treatment_ids) == len(EXPECTED_TREATMENTS), 'treatment slot inventory differs')
    for row in treatments:
        treatment_id = row.get('treatment_id')
        refs = row.get('candidate_source_ids', [])
        check(refs == EXPECTED_TREATMENTS.get(treatment_id), f'treatment source candidates differ:{treatment_id}')
        check(all(source_id in source_map for source_id in refs), f'treatment references unknown source:{treatment_id}')
        check(row.get('claim_state') == 'OFFICIAL_DOCUMENT_LOCATED', f'treatment claim state differs:{treatment_id}')
        check(row.get('identity_verification_status') == 'PENDING_BYTE_HASH', f'treatment identity status differs:{treatment_id}')
        check(row.get('activation_allowed') is False, f'treatment activated:{treatment_id}')
        check(row.get('effect_model_allowed') is False, f'treatment effect activated:{treatment_id}')
        check(row.get('concrete_fields') is None, f'concrete treatment content declared:{treatment_id}')
        check(row.get('independent_verifier_id') is None, f'unbound treatment verifier declared:{treatment_id}')

    spans = registry.get('span_candidates', [])
    span_ids = [row.get('span_candidate_id') for row in spans]
    check(set(span_ids) == set(EXPECTED_SPANS) and len(span_ids) == len(EXPECTED_SPANS), 'span candidate inventory differs')
    check(len(span_ids) == len(set(span_ids)), 'duplicate span candidate')
    span_map = {row.get('span_candidate_id'): row for row in spans}
    for span_id, expected in EXPECTED_SPANS.items():
        row = span_map.get(span_id, {})
        for field, value in expected.items():
            check(row.get(field) == value, f'span metadata differs:{span_id}:{field}')
        check(row.get('source_id') in source_map, f'span source unknown:{span_id}')
        check(isinstance(row.get('atomic_claim_candidate'), str) and len(row.get('atomic_claim_candidate', '')) >= 30, f'span claim candidate invalid:{span_id}')
        check(row.get('span_state') == 'LOCATED_NOT_BYTE_BOUND', f'span state differs:{span_id}')
        check(row.get('claim_state') == 'OFFICIAL_DOCUMENT_LOCATED', f'span claim state differs:{span_id}')
        check(row.get('exact_span_sha256') is None, f'unverified span digest declared:{span_id}')
        check(row.get('clinical_authority') == 'NOT_GRANTED', f'span authority escalated:{span_id}')
        page = row.get('page_number_1_based')
        check(page is None or (isinstance(page, int) and page > 0), f'span page invalid:{span_id}')

    calibration = registry.get('calibration_slots', [])
    parameter_ids = [row.get('parameter_id') for row in calibration]
    check(set(parameter_ids) == set(EXPECTED_CALIBRATION) and len(parameter_ids) == len(EXPECTED_CALIBRATION), 'calibration slot inventory differs')
    observed_values = profile_values(profile)
    for row in calibration:
        parameter_id = row.get('parameter_id')
        check(row.get('deterministic_exercise_value') == EXPECTED_CALIBRATION.get(parameter_id), f'calibration deterministic value differs:{parameter_id}')
        check(observed_values.get(parameter_id) == EXPECTED_CALIBRATION.get(parameter_id), f'profile/calibration value mismatch:{parameter_id}')
        check(row.get('unit') == 'seconds', f'calibration unit differs:{parameter_id}')
        check(row.get('candidate_model_family') in ALLOWED_MODEL_FAMILIES, f'unreviewed model family:{parameter_id}')
        check(row.get('calibration_state') == 'EXERCISE_ASSUMPTION', f'calibration state promoted:{parameter_id}')
        for field in ('dataset_identity', 'fit_artifact_sha256', 'holdout_metrics', 'uncertainty_interval', 'drift_rule'):
            check(row.get(field) is None, f'unsupported calibration evidence declared:{parameter_id}:{field}')
        check(row.get('calibrated') is False, f'parameter falsely calibrated:{parameter_id}')

    for path, key, value in walk(registry):
        if key in PROHIBITED_CONCRETE_KEYS:
            check(False, f'prohibited concrete or empirical field:{path}')
        if key.endswith('_sha256') and value is not None:
            check(re.fullmatch(r'[0-9a-f]{64}', str(value)) is not None, f'malformed digest:{path}')

    domains = boundaries.get('domains', {})
    check(domains.get('operational_calibration', {}).get('status') == 'NOT_CALIBRATED', 'validity calibration boundary differs')
    check(domains.get('treatment_legitimacy', {}).get('status') == 'BLOCKED_NO_ADJUDICATED_CONCRETE_TREATMENT', 'validity treatment boundary differs')
    check(domains.get('claim_entailment', {}).get('status') == 'IDENTITY_PROVENANCE_ONLY', 'validity claim boundary differs')

    report = {
        'schema_version': '1.1.0',
        'status': 'PASS' if not errors else 'FAIL',
        'checks': checks,
        'source_candidates': len(source_rows),
        'located_official_documents': sum(1 for row in source_rows if row.get('claim_state') == 'OFFICIAL_DOCUMENT_LOCATED'),
        'identity_verified_official_documents': sum(1 for row in source_rows if row.get('claim_state') == 'IDENTITY_VERIFIED'),
        'span_candidates': len(spans),
        'byte_bound_spans': sum(1 for row in spans if row.get('span_state') == 'SPAN_BOUND'),
        'claim_records': len(claims),
        'treatment_slots': len(treatments),
        'calibration_slots': len(calibration),
        'admitted_clinical_rules': sum(1 for row in claims if row.get('admitted_as_clinical_rule')),
        'activated_treatments': sum(1 for row in treatments if row.get('activation_allowed')),
        'calibrated_parameters': sum(1 for row in calibration if row.get('calibrated')),
        'errors': sorted(set(errors)),
        'truth_boundary': 'Official-document discovery and locator review do not establish byte identity, span binding, applicability, entailment, treatment authority, or calibration.',
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
