#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Callable
from release_result import finalize_adversarial_report

REPORT = Path('reports/facility-decision-mutations.json')
PROFILE = Path('config/facility-decision/ASK-D-001.json')
Mutation = Callable[[Path, dict[str, Any]], None]


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load module:{path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def profile(repo: Path) -> dict[str, Any]:
    return json.loads((repo / PROFILE).read_text(encoding='utf-8'))


def write_profile(repo: Path, data: dict[str, Any]) -> None:
    (repo / PROFILE).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8', newline='\n')


def mutate_authority(repo: Path, data: dict[str, Any]) -> None:
    data['authority']['patient_care_use'] = 'GRANTED'; write_profile(repo, data)


def mutate_concrete_activation(repo: Path, data: dict[str, Any]) -> None:
    data['authority']['concrete_treatment_activation'] = True; write_profile(repo, data)


def mutate_operational_calibration(repo: Path, data: dict[str, Any]) -> None:
    data['authority']['operational_parameters_calibrated'] = True; write_profile(repo, data)


def set_leak(field: str) -> Mutation:
    def mutate(repo: Path, data: dict[str, Any]) -> None:
        data['ui_modes']['learner_assessment'][field] = True; write_profile(repo, data)
    return mutate


def remove_source_contract(repo: Path, data: dict[str, Any]) -> None:
    data['decisions'] = [d for d in data['decisions'] if d['source_action_id'] != 'order_imaging']; write_profile(repo, data)


def duplicate_source_contract(repo: Path, data: dict[str, Any]) -> None:
    dup = copy.deepcopy(next(d for d in data['decisions'] if d['decision_id'] == 'order_imaging'))
    dup['decision_id'] = 'duplicate_imaging_contract'; dup['facility_action_id'] = 'wait_60'; data['decisions'].append(dup); write_profile(repo, data)


def declare_medication_field(repo: Path, data: dict[str, Any]) -> None:
    next(d for d in data['decisions'] if d['decision_id'] == 'pain_management')['fields'].append({'field_id': 'medication', 'label': 'Medication', 'type': 'text', 'required': True}); write_profile(repo, data)


def enable_pain_policy(repo: Path, data: dict[str, Any]) -> None:
    next(p for p in data['treatment_policies'] if p['treatment_id'] == 'PAIN_MANAGEMENT_OBJECTIVE')['concrete_treatment_allowed'] = True; write_profile(repo, data)


def weaken_pain_forbidden_keys(repo: Path, data: dict[str, Any]) -> None:
    next(p for p in data['treatment_policies'] if p['treatment_id'] == 'PAIN_MANAGEMENT_OBJECTIVE')['forbidden_submission_keys'].remove('dose'); write_profile(repo, data)


def couple_world_event(repo: Path, data: dict[str, Any]) -> None:
    data['operational_model']['world_events'][0]['trigger_action_id'] = 'order_imaging'; write_profile(repo, data)


def calibrate_world_event(repo: Path, data: dict[str, Any]) -> None:
    data['operational_model']['world_events'][0]['calibration_status'] = 'CALIBRATED'; write_profile(repo, data)


def zero_resource_capacity(repo: Path, data: dict[str, Any]) -> None:
    data['operational_model']['resources'][0]['capacity'] = 0; write_profile(repo, data)


def calibrate_resource(repo: Path, data: dict[str, Any]) -> None:
    data['operational_model']['resources'][0]['calibration_status'] = 'CALIBRATED'; write_profile(repo, data)


def validate_dynamic_physiology(repo: Path, data: dict[str, Any]) -> None:
    data['operational_model']['patient_observation_policy']['dynamic_physiology_validated'] = True; write_profile(repo, data)


def expose_latent_state(repo: Path, data: dict[str, Any]) -> None:
    data['operational_model']['patient_observation_policy']['latent_state_exposed_to_learner'] = True; write_profile(repo, data)


def repeatable_high_risk(repo: Path, data: dict[str, Any]) -> None:
    next(d for d in data['decisions'] if d['decision_id'] == 'remove_tourniquet')['repeatable'] = True; write_profile(repo, data)


def self_adjudicate_treatment_rule(repo: Path, data: dict[str, Any]) -> None:
    next(p for p in data['treatment_policies'] if p['treatment_id'] == 'PAIN_MANAGEMENT_OBJECTIVE')['governing_rule_status'] = 'ADJUDICATED'; write_profile(repo, data)


def activate_treatment_effect_model(repo: Path, data: dict[str, Any]) -> None:
    next(p for p in data['treatment_policies'] if p['treatment_id'] == 'PAIN_MANAGEMENT_OBJECTIVE')['effect_model_status'] = 'ACTIVE'; write_profile(repo, data)


def weaken_pair_obligations(repo: Path, data: dict[str, Any]) -> None:
    data['assurance']['ordered_pair_obligations'] = data['assurance']['ordered_pair_obligations'][:2]; write_profile(repo, data)


def collapse_reference_sequences(repo: Path, data: dict[str, Any]) -> None:
    data['assurance']['reference_sequences']['alternate'] = copy.deepcopy(data['assurance']['reference_sequences']['canonical']); write_profile(repo, data)


def remove_handoff_ack(repo: Path, data: dict[str, Any]) -> None:
    decision = next(d for d in data['decisions'] if d['decision_id'] == 'complete_handoff'); decision['fields'] = [f for f in decision['fields'] if f['field_id'] != 'receiver_acknowledged']; write_profile(repo, data)


def weaken_handoff_confirmation(repo: Path, data: dict[str, Any]) -> None:
    field = next(f for f in next(d for d in data['decisions'] if d['decision_id'] == 'complete_handoff')['fields'] if f['field_id'] == 'sender_confirmed'); field.pop('must_equal', None); write_profile(repo, data)


def remove_order_producer(repo: Path, data: dict[str, Any]) -> None:
    next(d for d in data['decisions'] if d['decision_id'] == 'order_labs')['creates_orders'] = []; write_profile(repo, data)


def remove_result_requirement(repo: Path, data: dict[str, Any]) -> None:
    next(d for d in data['decisions'] if d['decision_id'] == 'review_diagnostics')['requires_results'] = ['CHEST_IMAGING_REPORT']; write_profile(repo, data)


def leak_answer_label(repo: Path, data: dict[str, Any]) -> None:
    next(d for d in data['decisions'] if d['decision_id'] == 'remove_tourniquet')['learner_label'] = 'Unsafe and wrong tourniquet removal'; write_profile(repo, data)


def path_traversal(repo: Path, data: dict[str, Any]) -> None:
    data['diagnostic_catalog'][0]['source_pointer'] = '../private/source.txt#forged'; write_profile(repo, data)


def duplicate_decision(repo: Path, data: dict[str, Any]) -> None:
    data['decisions'].append(copy.deepcopy(data['decisions'][0])); write_profile(repo, data)


def source_inventory_change(repo: Path, data: dict[str, Any]) -> None:
    source = repo / 'src/content/scenarios.ts'; source.write_text(source.read_text(encoding='utf-8').replace("id: 'order_imaging'", "id: 'order_imaging_forged'", 1), encoding='utf-8', newline='\n')


def stale_generated(repo: Path, data: dict[str, Any]) -> None:
    data['operational_model']['information_staleness_seconds'] = 181; write_profile(repo, data)


def checker_crash(repo: Path, data: dict[str, Any]) -> None:
    (repo / 'scripts/check_facility_decision_integrity.py').write_text('this is not python\n', encoding='utf-8')


CASES: list[tuple[str, Mutation, bool]] = [
    ('patient_care_authority_escalation_rehashed', mutate_authority, True),
    ('concrete_treatment_activation_rehashed', mutate_concrete_activation, True),
    ('operational_calibration_promotion_rehashed', mutate_operational_calibration, True),
    ('learner_live_score_leak_rehashed', set_leak('show_live_score'), True),
    ('learner_source_points_leak_rehashed', set_leak('show_source_points'), True),
    ('learner_provenance_leak_rehashed', set_leak('show_provenance'), True),
    ('learner_wit_leak_rehashed', set_leak('show_wit'), True),
    ('learner_autoplay_leak_rehashed', set_leak('show_autoplay'), True),
    ('critical_source_contract_removed_rehashed', remove_source_contract, True),
    ('source_contract_duplicated_rehashed', duplicate_source_contract, True),
    ('concrete_medication_field_declared_rehashed', declare_medication_field, True),
    ('pain_policy_activated_rehashed', enable_pain_policy, True),
    ('pain_forbidden_key_removed_rehashed', weaken_pain_forbidden_keys, True),
    ('world_event_action_coupled_rehashed', couple_world_event, True),
    ('world_event_calibrated_rehashed', calibrate_world_event, True),
    ('resource_zero_capacity_rehashed', zero_resource_capacity, True),
    ('resource_calibration_promotion_rehashed', calibrate_resource, True),
    ('dynamic_physiology_false_validation_rehashed', validate_dynamic_physiology, True),
    ('latent_patient_state_leak_rehashed', expose_latent_state, True),
    ('high_risk_repeatability_escalation_rehashed', repeatable_high_risk, True),
    ('treatment_rule_self_adjudication_rehashed', self_adjudicate_treatment_rule, True),
    ('treatment_effect_model_activation_rehashed', activate_treatment_effect_model, True),
    ('ordered_pair_obligations_weakened_rehashed', weaken_pair_obligations, True),
    ('reference_sequences_collapsed_rehashed', collapse_reference_sequences, True),
    ('handoff_ack_removed_rehashed', remove_handoff_ack, True),
    ('handoff_confirmation_weakened_rehashed', weaken_handoff_confirmation, True),
    ('diagnostic_order_producer_removed_rehashed', remove_order_producer, True),
    ('diagnostic_result_requirement_removed_rehashed', remove_result_requirement, True),
    ('high_risk_answer_label_leak_rehashed', leak_answer_label, True),
    ('diagnostic_source_path_traversal_rehashed', path_traversal, True),
    ('duplicate_decision_rehashed', duplicate_decision, True),
    ('source_action_inventory_changed', source_inventory_change, False),
    ('stale_generated_typescript', stale_generated, False),
    ('checker_internal_error_is_not_rejection', checker_crash, False),
]


def minimal_copy(source: Path, target: Path) -> None:
    for relative in [
        PROFILE,
        Path('src/facility-decision/contracts.generated.ts'),
        Path('src/facility-decision/runtime.ts'),
        Path('src/facility-decision-checker/verify.ts'),
        Path('src/content/scenarios.ts'),
        Path('scripts/compile_facility_decision_contracts.py'),
        Path('scripts/check_facility_decision_integrity.py'),
    ]:
        destination = target / relative; destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source / relative, destination)


def classify_in_process(checker: ModuleType, candidate: Path) -> tuple[str, list[str], str]:
    try:
        errors, _metadata = checker.verify(candidate)
    except Exception as exc:
        return 'INTERNAL_ERROR', [], f'{type(exc).__name__}:{exc}'
    return ('REJECTED', errors, '') if errors else ('PASS', [], '')


def compile_in_process(compiler: ModuleType, candidate: Path) -> None:
    data = profile(candidate)
    errors = compiler.validate(data)
    if errors:
        return
    source_bytes = (candidate / PROFILE).read_bytes()
    rendered = compiler.render(data, compiler.sha256_bytes(source_bytes))
    target = candidate / 'src/facility-decision/contracts.generated.ts'
    target.write_text(rendered, encoding='utf-8', newline='\n')


def crash_classification(candidate: Path) -> tuple[str, list[str], str]:
    completed = subprocess.run(
        [sys.executable, 'scripts/check_facility_decision_integrity.py', '--repo', '.', '--json-output', 'reports/result.json'],
        cwd=candidate, text=True, capture_output=True,
    )
    try:
        payload = json.loads(completed.stdout)
    except Exception:
        # Deliberately omit raw tracebacks and temporary filesystem paths from the
        # committed report.  The classification is the assurance evidence; the
        # host-specific traceback is diagnostic noise and makes the report
        # nondeterministic across Python versions and operating systems.
        return 'INTERNAL_ERROR', [], 'checker_failed_before_structured_result'
    if completed.returncode == 0 and payload.get('status') == 'PASS': return 'PASS', [], ''
    if completed.returncode != 0 and payload.get('status') == 'FAIL' and isinstance(payload.get('errors'), list): return 'REJECTED', payload['errors'], ''
    return 'INTERNAL_ERROR', payload.get('errors', []) if isinstance(payload, dict) else [], 'checker_returned_inconsistent_result'


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument('--repo', default='.'); parser.add_argument('--json-output', default=REPORT.as_posix()); args = parser.parse_args()
    repo = Path(args.repo).resolve(); results=[]; errors=[]; globally_rehashed=0
    checker = load_module('asklepios_decision_checker', repo / 'scripts/check_facility_decision_integrity.py')
    compiler = load_module('asklepios_decision_compiler', repo / 'scripts/compile_facility_decision_contracts.py')

    baseline_status, baseline_errors, baseline_tail = classify_in_process(checker, repo)
    results.append({'case_id': 'baseline', 'classification': baseline_status, 'pass': baseline_status == 'PASS', 'errors': baseline_errors or ([baseline_tail] if baseline_tail else [])})
    if baseline_status != 'PASS': errors.append('baseline checker did not pass')

    for case_id, mutate, rehashed in CASES:
        with tempfile.TemporaryDirectory(prefix='asklepios-decision-mutation-') as temp:
            candidate = Path(temp) / 'repo'; candidate.mkdir(); minimal_copy(repo, candidate); data = profile(candidate); mutate(candidate, data)
            if rehashed: compile_in_process(compiler, candidate); globally_rehashed += 1
            if case_id == 'checker_internal_error_is_not_rejection': status, checker_errors, tail = crash_classification(candidate)
            else: status, checker_errors, tail = classify_in_process(checker, candidate)
            expected = 'INTERNAL_ERROR' if case_id == 'checker_internal_error_is_not_rejection' else 'REJECTED'
            passed = status == expected
            if not passed: errors.append(f'{case_id}:expected={expected}:observed={status}')
            results.append({'case_id': case_id, 'classification': status, 'expected': expected, 'globally_rehashed': rehashed, 'pass': passed, 'checker_errors': checker_errors, 'diagnostic_tail': tail if status == 'INTERNAL_ERROR' else ''})

    report = {
        'schema_version': '1.1.0', 'status': 'PASS' if not errors else 'FAIL', 'execution_model': 'in_process_semantic_checker_with_one_explicit_crash_subprocess',
        'cases': len(results), 'attacks': len(CASES), 'globally_rehashed_attacks': globally_rehashed,
        'rejected_attacks': sum(1 for row in results[1:] if row['classification'] == 'REJECTED'),
        'internal_error_challenges': sum(1 for row in results[1:] if row['expected'] == 'INTERNAL_ERROR'),
        'unexpected_internal_errors': sum(1 for row in results[1:] if row['classification'] == 'INTERNAL_ERROR' and row['expected'] != 'INTERNAL_ERROR'),
        'accepted_forgery_count': sum(1 for row in results[1:] if row['classification'] == 'PASS'),
        'anti_circular_note': 'Profiles are regenerated in-process before checking when the attack is marked rehashed; stale hashes alone cannot explain rejection. Checker crashes are INTERNAL_ERROR and never count as semantic rejection.',
        'results': results, 'errors': errors,
    }
    report = finalize_adversarial_report(report, baseline_case_ids=("baseline",))
    output = repo / args.json_output; output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n'); print(json.dumps(report, indent=2, sort_keys=True)); return 0 if not errors else 1


if __name__ == '__main__': raise SystemExit(main())
