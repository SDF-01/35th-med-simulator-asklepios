#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from release_result import finalize_adversarial_report
from typing import Any, Callable

ROOT = Path.cwd()
SPEC = importlib.util.spec_from_file_location(
    'promotion', ROOT / 'scripts/check_facility_decision_evidence_promotion.py'
)
assert SPEC and SPEC.loader
promotion = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(promotion)

REGISTRY_REL = Path('config/facility-decision/EVIDENCE_PROMOTION_REGISTRY.json')
BASE = json.loads((ROOT / REGISTRY_REL).read_text(encoding='utf-8'))
CASES: list[dict[str, Any]] = []


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')


def prepare(value: dict[str, Any]) -> Path:
    temp = Path(tempfile.mkdtemp(prefix='asklepios-evidence-promotion-'))
    for rel in (
        'config/facility-decision/ASK-D-001.json',
        'config/facility-decision/VALIDITY_BOUNDARIES.json',
    ):
        src = ROOT / rel
        dst = temp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    write_json(temp / REGISTRY_REL, value)
    return temp


def row_by_id(rows: list[dict[str, Any]], field: str, value: str) -> dict[str, Any]:
    return next(row for row in rows if row.get(field) == value)


def run(case_id: str, mutate: Callable[[dict[str, Any]], None], expected_pass: bool) -> None:
    value = copy.deepcopy(BASE)
    temp: Path | None = None
    try:
        mutate(value)
        temp = prepare(value)
        result = promotion.validate(temp)
        observed = result['status'] == 'PASS'
        CASES.append({
            'case_id': case_id,
            'expected_pass': expected_pass,
            'observed_pass': observed,
            'pass': observed == expected_pass,
            'checker_errors': result['errors'],
        })
    except Exception as exc:
        CASES.append({
            'case_id': case_id,
            'expected_pass': expected_pass,
            'observed_pass': False,
            'pass': False,
            'checker_errors': [f'INTERNAL_ERROR:{type(exc).__name__}:{exc}'],
        })
    finally:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)


def noop(_: dict[str, Any]) -> None:
    return


def source_mutator(source_id: str, fn: Callable[[dict[str, Any]], None]):
    def wrapped(value: dict[str, Any]) -> None:
        fn(row_by_id(value['source_candidates'], 'source_id', source_id))
    return wrapped


def claim_mutator(claim_id: str, fn: Callable[[dict[str, Any]], None]):
    def wrapped(value: dict[str, Any]) -> None:
        fn(row_by_id(value['claim_records'], 'claim_id', claim_id))
    return wrapped


def treatment_mutator(treatment_id: str, fn: Callable[[dict[str, Any]], None]):
    def wrapped(value: dict[str, Any]) -> None:
        fn(row_by_id(value['treatment_slots'], 'treatment_id', treatment_id))
    return wrapped


def span_mutator(span_id: str, fn: Callable[[dict[str, Any]], None]):
    def wrapped(value: dict[str, Any]) -> None:
        fn(row_by_id(value['span_candidates'], 'span_candidate_id', span_id))
    return wrapped


def calibration_mutator(parameter_id: str, fn: Callable[[dict[str, Any]], None]):
    def wrapped(value: dict[str, Any]) -> None:
        fn(row_by_id(value['calibration_slots'], 'parameter_id', parameter_id))
    return wrapped


SOURCE = 'jts-wartime-thoracic-injury-2018-12-26'
CLAIM = 'ask-d-001-hidden-finding-pneumothorax'
TREATMENT = 'pain_management'
SPAN = 'thoracic-injury-receiving-assessment-domains'
PARAMETER = 'second_casualty_inbound_seconds'

run('baseline', noop, True)

# Source discovery and identity boundary.
run('source_authority_escalation', source_mutator(SOURCE, lambda r: r.__setitem__('clinical_authority', 'GRANTED')), False)
run('source_direct_admission', source_mutator(SOURCE, lambda r: r.__setitem__('claim_state', 'ADMITTED')), False)
run('source_state_demotion', source_mutator(SOURCE, lambda r: r.__setitem__('claim_state', 'DISCOVERED')), False)
run('source_identity_without_hash', source_mutator(SOURCE, lambda r: r.__setitem__('claim_state', 'IDENTITY_VERIFIED')), False)
run('source_hash_without_identity', source_mutator(SOURCE, lambda r: r.__setitem__('exact_document_sha256', '0' * 64)), False)
run('source_malformed_hash', source_mutator(SOURCE, lambda r: r.__setitem__('exact_document_sha256', 'not-a-hash')), False)
run('source_locator_without_span_binding', source_mutator(SOURCE, lambda r: r.__setitem__('exact_locator', 'Section 1')), False)
run('source_official_url_host_escape', source_mutator(SOURCE, lambda r: r.__setitem__('official_document_url', 'https://example.com/fake.pdf')), False)
run('source_official_url_downgrade', source_mutator(SOURCE, lambda r: r.__setitem__('official_document_url', 'http://jts.health.mil/fake.pdf')), False)
run('source_verified_title_drift', source_mutator(SOURCE, lambda r: r.__setitem__('document_title_verified', 'Different title')), False)
run('source_locator_evidence_removed', source_mutator(SOURCE, lambda r: r.pop('locator_evidence_kind')), False)
run('source_locator_timestamp_invalid', source_mutator(SOURCE, lambda r: r.__setitem__('locator_verified_at_utc', 'yesterday')), False)
run('source_identity_status_promotion', source_mutator(SOURCE, lambda r: r.__setitem__('identity_verification_status', 'VERIFIED')), False)
run('source_identity_verifier_premature', source_mutator(SOURCE, lambda r: r.__setitem__('independent_identity_verifier_id', 'reviewer-a')), False)
run('tccc_care_phase_limit_removed', source_mutator('jts-tccc-guidelines-2026-05-01', lambda r: r.pop('care_phase_limitation')), False)

# Template identity claims remain non-entailing and non-authoritative.
run('claim_entailment_self_certified', claim_mutator(CLAIM, lambda r: r.__setitem__('entailment_label', 'SUPPORTS')), False)
run('claim_direct_admission', claim_mutator(CLAIM, lambda r: r.__setitem__('admitted_as_clinical_rule', True)), False)
run('claim_state_jump', claim_mutator(CLAIM, lambda r: r.__setitem__('claim_state', 'ADMITTED')), False)
run('claim_self_attestation', claim_mutator(CLAIM, lambda r: r.__setitem__('independent_verifier_id', r['producer_id'])), False)
run('claim_source_path_escape', claim_mutator(CLAIM, lambda r: r.__setitem__('source_locator', '../private/source')), False)
run('claim_contradiction_self_clearance', claim_mutator(CLAIM, lambda r: r.__setitem__('contradiction_status', 'CLEAR')), False)
run('claim_supersession_drift', claim_mutator(CLAIM, lambda r: r.__setitem__('supersession_status', 'CURRENT')), False)

# Treatment candidates can be located, but not activated or interpreted as treatment rules.
run('treatment_activation', treatment_mutator(TREATMENT, lambda r: r.__setitem__('activation_allowed', True)), False)
run('treatment_effect_activation', treatment_mutator(TREATMENT, lambda r: r.__setitem__('effect_model_allowed', True)), False)
run('concrete_medication_insertion', treatment_mutator(TREATMENT, lambda r: r.__setitem__('drug', 'invented')), False)
run('unknown_treatment_source', treatment_mutator(TREATMENT, lambda r: r.__setitem__('candidate_source_ids', ['unknown'])), False)
run('treatment_direct_admission', treatment_mutator(TREATMENT, lambda r: r.__setitem__('claim_state', 'ADMITTED')), False)
run('treatment_identity_promotion_without_hash', treatment_mutator(TREATMENT, lambda r: r.__setitem__('identity_verification_status', 'VERIFIED')), False)
run('treatment_verifier_premature', treatment_mutator(TREATMENT, lambda r: r.__setitem__('independent_verifier_id', 'reviewer-a')), False)

# Located span candidates are not byte-bound or adjudicated claims.
run('span_direct_binding', span_mutator(SPAN, lambda r: r.__setitem__('span_state', 'SPAN_BOUND')), False)
run('span_digest_without_binding', span_mutator(SPAN, lambda r: r.__setitem__('exact_span_sha256', '0' * 64)), False)
run('span_direct_admission', span_mutator(SPAN, lambda r: r.__setitem__('claim_state', 'ADMITTED')), False)
run('span_unknown_source', span_mutator(SPAN, lambda r: r.__setitem__('source_id', 'unknown')), False)
run('span_applicability_self_review', span_mutator(SPAN, lambda r: r.__setitem__('applicability_status', 'APPLICABLE')), False)
run('span_authority_escalation', span_mutator(SPAN, lambda r: r.__setitem__('clinical_authority', 'GRANTED')), False)
run('span_page_invalid', span_mutator(SPAN, lambda r: r.__setitem__('page_number_1_based', 0)), False)

# Calibration remains an exercise assumption until all required evidence exists.
run('calibration_direct_promotion', calibration_mutator(PARAMETER, lambda r: r.__setitem__('calibration_state', 'CALIBRATED')), False)
run('calibration_boolean_escalation', calibration_mutator(PARAMETER, lambda r: r.__setitem__('calibrated', True)), False)
run('calibration_distribution_insertion', calibration_mutator(PARAMETER, lambda r: r.__setitem__('distribution_parameters', {'mean': 1})), False)
run('calibration_dataset_without_state', calibration_mutator(PARAMETER, lambda r: r.__setitem__('dataset_identity', 'unbound-dataset')), False)
run('calibration_value_diverges_from_profile', calibration_mutator(PARAMETER, lambda r: r.__setitem__('deterministic_exercise_value', 241)), False)
run('unreviewed_model_family', calibration_mutator(PARAMETER, lambda r: r.__setitem__('candidate_model_family', 'MAGIC_MODEL')), False)

# The state machine and independence requirements cannot be weakened in-place.
run('claim_state_order_weakened', lambda v: v['policy'].__setitem__('claim_state_order', ['DISCOVERED', 'ADMITTED']), False)
run('independent_actor_requirement_removed', lambda v: v['policy'].__setitem__('independent_actor_required', False), False)
run('source_identity_rule_weakened', lambda v: v['policy'].__setitem__('source_identity_rule', 'URL is enough'), False)
run('span_binding_rule_weakened', lambda v: v['policy'].__setitem__('span_binding_rule', 'Page number is enough'), False)
run('registry_schema_downgrade', lambda v: v.__setitem__('schema_version', '1.0.0'), False)

failed = [row['case_id'] for row in CASES if not row['pass']]
attack_rows = CASES[1:]
report = {
    'schema_version': '1.1.0',
    'status': 'PASS' if not failed else 'FAIL',
    'cases': len(CASES),
    'attacks': len(attack_rows),
    'accepted_attacks': sum(1 for row in attack_rows if row['observed_pass']),
    'internal_errors': sum(
        1 for row in CASES
        if any(str(error).startswith('INTERNAL_ERROR:') for error in row['checker_errors'])
    ),
    'errors': failed,
    'results': CASES,
    'anti_circular_note': 'The checker evaluates semantic state transitions and required evidence fields; URL discovery, hashes, and state labels cannot promote themselves.',
}
report = finalize_adversarial_report(report, baseline_case_ids=('baseline',))
out = ROOT / 'reports/facility-decision-evidence-promotion-mutations.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
print(json.dumps(report, indent=2, sort_keys=True))
raise SystemExit(0 if report['status'] == 'PASS' else 3)
