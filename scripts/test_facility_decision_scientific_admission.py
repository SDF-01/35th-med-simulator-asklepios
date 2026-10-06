#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from release_result import finalize_adversarial_report

ROOT = Path.cwd()
SPEC = importlib.util.spec_from_file_location('scientific', ROOT / 'scripts/check_facility_decision_scientific_admission.py')
assert SPEC and SPEC.loader
scientific = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scientific)

CASES: list[dict] = []


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')


def prepare() -> Path:
    temp = Path(tempfile.mkdtemp(prefix='asklepios-scientific-admission-'))
    for rel in (
        'config/facility-decision/ASK-D-001.json',
        'config/facility-decision/VALIDITY_BOUNDARIES.json',
        'config/facility-decision/EVIDENCE_PROMOTION_REGISTRY.json',
        'scripts/build_facility_decision_provenance.py',
        'docs/FACILITY_DECISION_ACCESSIBILITY_PROTOCOL.md',
        'docs/FACILITY_DECISION_VALIDITY_BOUNDARIES.md',
        'examples/facility-decision/README.md',
        'README.md',
        'reports/facility-decision-differential.json',
        'formal/ScenarioContracts/FacilityDecisionIntegrity.lean',
        'formal/FACILITY_DECISION_INTEGRITY_TRUST_MANIFEST.json',
    ):
        src = ROOT / rel
        dst = temp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return temp


def run_case(case_id: str, mutator, expected_pass: bool) -> None:
    temp = prepare()
    try:
        mutator(temp)
        result = scientific.validate(temp)
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
        shutil.rmtree(temp, ignore_errors=True)


def no_change(_: Path) -> None:
    return


def profile_mutator(fn):
    def wrapped(root: Path):
        path = root / 'config/facility-decision/ASK-D-001.json'
        value = json.loads(path.read_text())
        fn(value)
        write_json(path, value)
    return wrapped


def boundary_mutator(fn):
    def wrapped(root: Path):
        path = root / 'config/facility-decision/VALIDITY_BOUNDARIES.json'
        value = json.loads(path.read_text())
        fn(value)
        write_json(path, value)
    return wrapped


def append_text(relative: str, text: str):
    def wrapped(root: Path):
        path = root / relative
        path.write_text(path.read_text(encoding='utf-8') + text, encoding='utf-8', newline='\n')
    return wrapped


def replace_text(relative: str, old: str, new: str):
    def wrapped(root: Path):
        path = root / relative
        content = path.read_text(encoding='utf-8')
        if old not in content:
            raise RuntimeError(f'mutation marker missing:{relative}:{old}')
        path.write_text(content.replace(old, new, 1), encoding='utf-8', newline='\n')
    return wrapped


run_case('baseline', no_change, True)
run_case('resource_calibration_promotion', profile_mutator(lambda p: p['operational_model']['resources'][0].__setitem__('calibration_status', 'CALIBRATED')), False)
run_case('empirical_distribution_without_registry', profile_mutator(lambda p: p['operational_model']['resources'][0].__setitem__('empirical_distribution', {'mean': 10})), False)
run_case('concrete_treatment_activation', profile_mutator(lambda p: p['treatment_policies'][0].__setitem__('concrete_treatment_allowed', True)), False)
run_case('treatment_rule_self_adjudication', profile_mutator(lambda p: p['treatment_policies'][0].__setitem__('governing_rule_status', 'ADJUDICATED')), False)
run_case('concrete_dose_field', profile_mutator(lambda p: p['decisions'][0]['fields'].append({'field_id': 'dose', 'label': 'Dose', 'type': 'number', 'required': True})), False)
run_case('dynamic_physiology_promotion', profile_mutator(lambda p: p['operational_model']['patient_observation_policy'].__setitem__('dynamic_physiology_validated', True)), False)
run_case('latent_state_exposure', profile_mutator(lambda p: p['operational_model']['patient_observation_policy'].__setitem__('latent_state_exposed_to_learner', True)), False)
run_case('human_probability_without_calibration', profile_mutator(lambda p: p['decisions'][0].__setitem__('compliance_probability', 0.8)), False)
run_case('diagnostic_entailment_self_certified', profile_mutator(lambda p: p['diagnostic_catalog'][0].__setitem__('entailment_status', 'SUPPORTS')), False)
run_case('diagnostic_source_escape', profile_mutator(lambda p: p['diagnostic_catalog'][0].__setitem__('source_pointer', '../../private/source.txt#x')), False)
run_case('causal_claim_injection', append_text('examples/facility-decision/README.md', '\nThis learner decision caused the outcome.\n'), False)
run_case('manual_accessibility_boundary_removed', replace_text('docs/FACILITY_DECISION_ACCESSIBILITY_PROTOCOL.md', 'MANUAL_ACCESSIBILITY_VALIDATION_REQUIRED', 'COMPLETE'), False)
run_case('signed_provenance_false_claim', replace_text('scripts/build_facility_decision_provenance.py', "'signature_status': 'UNSIGNED'", "'signature_status': 'SIGNED'"), False)
run_case('treatment_attestation_requirement_removed', boundary_mutator(lambda b: b['domains']['treatment_legitimacy']['activation_requirements'].remove('independent_attestation')), False)
run_case('calibration_holdout_requirement_removed', boundary_mutator(lambda b: b['domains']['operational_calibration']['activation_requirements'].remove('held_out_evaluation')), False)
run_case('patient_care_authority_escalation', profile_mutator(lambda p: p['authority'].__setitem__('patient_care_use', 'AUTHORIZED')), False)

failed = [row['case_id'] for row in CASES if not row['pass']]
report = {
    'schema_version': '1.0.0',
    'status': 'PASS' if not failed else 'FAIL',
    'cases': len(CASES),
    'attacks': len(CASES) - 1,
    'accepted_escalations': sum(1 for row in CASES[1:] if row['observed_pass']),
    'internal_errors': sum(1 for row in CASES if any(str(err).startswith('INTERNAL_ERROR:') for err in row['checker_errors'])),
    'errors': failed,
    'results': CASES,
}
report = finalize_adversarial_report(report, baseline_case_ids=('baseline',))
out = ROOT / 'reports/facility-decision-scientific-admission-mutations.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
print(json.dumps(report, indent=2, sort_keys=True))
raise SystemExit(0 if not failed else 3)
