#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

PROFILE = Path('config/facility-decision/ASK-D-001.json')
GENERATED = Path('src/facility-decision/contracts.generated.ts')
SOURCE = Path('src/content/scenarios.ts')
DEFAULT_REPORT = Path('reports/facility-decision-integrity-python.json')

CRITICAL_IMPORTANT = {
    'primary_assessment', 'order_imaging', 'order_labs',
    'differential', 'monitor_vitals', 'escalation',
}
LEARNER_FALSE_FIELDS = {
    'show_live_score', 'show_source_points', 'show_source_origin',
    'show_provenance', 'show_wit', 'show_autoplay',
    'show_completed_replay', 'show_correctness_labels',
    'show_disabled_reasons',
}
REQUIRED_HANDOFF_FIELDS = {
    'sender_identity', 'receiver_identity', 'situation', 'background',
    'assessment_and_uncertainty', 'actions_and_response', 'pending_tasks',
    'recommendation', 'contingency', 'receiver_acknowledged',
    'questions_offered', 'sender_confirmed',
}
CONCRETE_TREATMENT_KEYS = {
    'medication', 'medication_name', 'dose', 'dose_unit', 'route',
    'procedure', 'procedure_code', 'device_setting',
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_source_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b'\xef\xbb\xbf'):
        raise ValueError('UTF-8 BOM forbidden')
    text = raw.decode('utf-8')
    return text.replace('\r\n', '\n').replace('\r', '\n')


def safe_repo_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        return False
    pure = PurePosixPath(value)
    return not pure.is_absolute() and '..' not in pure.parts and all(part not in ('', '.') for part in pure.parts)


def ask_d001_block(text: str) -> str:
    marker = "const askD001: Scenario = {"
    start = text.find(marker)
    if start < 0:
        raise ValueError('ASK-D-001 declaration missing')
    end = text.find("\n};\n\nexport const scenariosById", start)
    if end < 0:
        raise ValueError('ASK-D-001 declaration boundary missing')
    return text[start:end + 3]


def action_ids_by_priority(block: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for priority in ('critical', 'important', 'optional', 'unsafe'):
        match = re.search(rf"\n\s{{4}}{priority}: \[(.*?)\n\s{{4}}\],", block, re.S)
        if not match:
            raise ValueError(f'priority block missing:{priority}')
        result[priority] = set(re.findall(r"\bid:\s*'([^']+)'", match.group(1)))
    return result


def verify(repo: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    checks = 0
    def check(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    for path in (PROFILE, GENERATED, SOURCE):
        check((repo / path).is_file(), f'missing:{path.as_posix()}')
    if errors:
        return sorted(set(errors)), {'checks': checks}

    try:
        profile = json.loads((repo / PROFILE).read_text(encoding='utf-8'))
    except Exception as exc:
        return [f'profile JSON invalid:{type(exc).__name__}'], {'checks': checks}
    try:
        source_text = canonical_source_text(repo / SOURCE)
        source_block = ask_d001_block(source_text)
        source_actions = action_ids_by_priority(source_block)
    except Exception as exc:
        return [f'source parse failed:{exc}'], {'checks': checks}

    check(profile.get('schema_version') == '1.0.0', 'profile schema differs')
    check(profile.get('source_scenario_id') == 'ASK-D-001', 'source scenario differs')
    authority = profile.get('authority', {})
    check(authority.get('patient_care_use') == 'PROHIBITED', 'patient-care use escalated')
    check(authority.get('concrete_treatment_activation') is False, 'concrete treatment activated')
    check(authority.get('operational_parameters_calibrated') is False, 'operational parameters falsely calibrated')

    decisions = profile.get('decisions', [])
    decision_ids = [item.get('decision_id') for item in decisions if isinstance(item, dict)]
    check(len(decision_ids) == len(set(decision_ids)), 'duplicate decision IDs')
    check(all(isinstance(item, str) and item for item in decision_ids), 'invalid decision ID')
    decision_map = {item['decision_id']: item for item in decisions if isinstance(item, dict) and isinstance(item.get('decision_id'), str)}
    bound = [item.get('source_action_id') for item in decisions if isinstance(item, dict) and item.get('source_action_id') in CRITICAL_IMPORTANT]
    check(set(bound) == CRITICAL_IMPORTANT, 'critical/important source contract coverage differs')
    check(len(bound) == len(CRITICAL_IMPORTANT), 'critical/important source action duplicated')
    check((source_actions['critical'] | source_actions['important']) == CRITICAL_IMPORTANT, 'source critical/important inventory differs')

    for did, decision in decision_map.items():
        checks += 1
        if not decision.get('fields'):
            errors.append(f'decision fields missing:{did}')
        field_ids = {field.get('field_id') for field in decision.get('fields', []) if isinstance(field, dict)}
        if decision.get('treatment_policy_id') and field_ids.intersection(CONCRETE_TREATMENT_KEYS):
            errors.append(f'concrete treatment field declared:{did}')
        for predecessor in decision.get('prerequisites', []):
            check(predecessor in decision_map, f'unknown prerequisite:{did}:{predecessor}')
        if decision.get('source_action_id') is not None:
            check(decision.get('source_action_id') in set().union(*source_actions.values()), f'unknown source action:{did}')
        if decision.get('high_risk'):
            fields = {field.get('field_id') for field in decision.get('fields', []) if isinstance(field, dict)}
            check({'rationale', 'deliberate_confirmation'}.issubset(fields), f'high-risk confirmation incomplete:{did}')
            check(not re.search(r'unsafe|wrong|fail', str(decision.get('learner_label', '')), re.I), f'answer-label leakage:{did}')
        check(isinstance(decision.get('repeatable'), bool), f'repeatable flag missing:{did}')
        if decision.get('repeatable') is True:
            check(did == 'wait_60', f'unreviewed repeatable decision:{did}')
    repeatable_ids = sorted(did for did, decision in decision_map.items() if decision.get('repeatable') is True)
    check(repeatable_ids == ['wait_60'], 'repeatable decision inventory differs')

    learner = profile.get('ui_modes', {}).get('learner_assessment', {})
    for field in LEARNER_FALSE_FIELDS:
        check(learner.get(field) is False, f'learner answer leakage:{field}')
    check(profile.get('dimension_policy', {}).get('learner_live_display') is False, 'dimension scoring shown live')
    check(profile.get('dimension_policy', {}).get('single_composite_score_is_clinical_validity') is False, 'single score falsely treated as validity')

    policies = {item.get('treatment_id'): item for item in profile.get('treatment_policies', []) if isinstance(item, dict)}
    check(set(policies) == {'PAIN_MANAGEMENT_OBJECTIVE', 'TOURNIQUET_MODIFICATION'}, 'treatment policy inventory differs')
    for pid, policy in policies.items():
        check(policy.get('concrete_treatment_allowed') is False, f'concrete treatment enabled:{pid}')
        check(policy.get('governing_rule_status') == 'NOT_ADJUDICATED', f'treatment rule self-adjudicated:{pid}')
        check(policy.get('effect_model_status') == 'BLOCKED', f'treatment effect model activated:{pid}')
        check(bool(policy.get('activation_requirements_for_future_concrete_content')), f'treatment activation requirements missing:{pid}')
    check(CONCRETE_TREATMENT_KEYS.issubset(set(policies['PAIN_MANAGEMENT_OBJECTIVE'].get('forbidden_submission_keys', []))), 'pain policy concrete fields not fully blocked')

    handoff = decision_map.get('complete_handoff', {})
    handoff_fields = {field.get('field_id') for field in handoff.get('fields', []) if isinstance(field, dict)}
    check(REQUIRED_HANDOFF_FIELDS.issubset(handoff_fields), 'closed-loop handoff fields incomplete')
    for field_id in ('receiver_acknowledged', 'questions_offered', 'sender_confirmed'):
        field = next((item for item in handoff.get('fields', []) if item.get('field_id') == field_id), {})
        check(field.get('must_equal') is True, f'handoff closure not required:{field_id}')

    diagnostics = profile.get('diagnostic_catalog', [])
    order_codes = {item.get('order_code') for item in diagnostics}
    result_ids = {item.get('result_id') for item in diagnostics}
    check(order_codes == {'CHEST_IMAGING', 'LACTATE'}, 'diagnostic order inventory differs')
    check(result_ids == {'CHEST_IMAGING_REPORT', 'LACTATE_RESULT'}, 'diagnostic result inventory differs')
    resources = {item.get('resource_id'): item for item in profile.get('operational_model', {}).get('resources', []) if isinstance(item, dict)}
    check(set(resources) == {'CHEST_IMAGING_SERVICE', 'LABORATORY_SERVICE', 'HIGHER_LEVEL_CARE_COORDINATION'}, 'operational resource inventory differs')
    for rid, resource in resources.items():
        check(isinstance(resource.get('capacity'), int) and resource.get('capacity', 0) >= 1, f'resource capacity invalid:{rid}')
        check(resource.get('queue_policy') == 'FIFO', f'resource queue policy differs:{rid}')
        check(resource.get('calibration_status') == 'NOT_CALIBRATED', f'resource falsely calibrated:{rid}')
        check(isinstance(resource.get('service_duration_seconds'), int) and resource.get('service_duration_seconds', 0) > 0, f'resource duration invalid:{rid}')
    for item in diagnostics:
        check(bool(item.get('source_pointer')), f'diagnostic source pointer missing:{item.get("result_id")}')
        check(safe_repo_path(str(item.get('source_pointer', '')).split('#')[0]), f'diagnostic source path unsafe:{item.get("result_id")}')
        check(item.get('resource_id') in resources, f'diagnostic resource missing:{item.get("result_id")}')
    order_producers = {code: [] for code in order_codes}
    for did, decision in decision_map.items():
        for code in decision.get('creates_orders', []):
            if code in order_producers:
                order_producers[code].append(did)
    for code, producers in order_producers.items():
        check(len(producers) == 1, f'diagnostic order producer count differs:{code}:{len(producers)}')
    review = decision_map.get('review_diagnostics', {})
    check(set(review.get('requires_results', [])) == result_ids, 'result-review contract does not require every exact result')

    world = profile.get('operational_model', {})
    events = world.get('world_events', [])
    check(len(events) == 1, 'world event inventory differs')
    for event in events:
        check(event.get('calibration_status') == 'NOT_CALIBRATED', f'world event falsely calibrated:{event.get("event_id")}')
        check('trigger_action_id' not in event, f'world event coupled to learner action:{event.get("event_id")}')
    confirm = decision_map.get('confirm_surge_roles', {})
    check(confirm.get('required_world_events') == ['second_casualty_inbound'], 'surge response is not bound to independent world event')
    observation_policy = world.get('patient_observation_policy', {})
    check(observation_policy.get('mode') == 'SOURCE_BOUND_OBSERVATIONS_ONLY', 'patient observation mode differs')
    check(observation_policy.get('dynamic_physiology_validated') is False, 'dynamic physiology falsely validated')
    check(observation_policy.get('latent_state_exposed_to_learner') is False, 'latent patient state exposed')

    assurance = profile.get('assurance', {})
    sequences = assurance.get('reference_sequences', {})
    check(set(sequences) == {'canonical', 'alternate'}, 'reference sequence inventory differs')
    check(sequences.get('canonical') != sequences.get('alternate'), 'reference sequences not distinct')
    for name, sequence in sequences.items():
        check(bool(sequence) and sequence[-1] == 'complete_handoff', f'reference sequence incomplete:{name}')
        check(all(item in decision_map for item in sequence), f'reference sequence unknown decision:{name}')
    check(len(assurance.get('ordered_pair_obligations', [])) >= 10, 'ordered pair obligations weakened')
    check(len(assurance.get('ordered_triple_obligations', [])) >= 5, 'ordered triple obligations weakened')
    bounds = assurance.get('bounded_exploration', {})
    check(bounds.get('max_decision_depth') == 20, 'bounded exploration depth differs')
    check(bounds.get('max_repeatable_waits') == 20, 'repeatable wait bound differs')
    check(set(bounds.get('required_terminal_witnesses', [])) == {'completed_canonical','completed_alternate','failed_discharge','failed_tourniquet','timeout'}, 'terminal witness inventory differs')

    generated_text = (repo / GENERATED).read_text(encoding='utf-8')
    source_sha = sha256_bytes((repo / PROFILE).read_bytes())
    check(f"FACILITY_DECISION_PROFILE_SOURCE_SHA256 = '{source_sha}'" in generated_text, 'generated source digest differs')
    check(generated_text.startswith('// Generated by scripts/compile_facility_decision_contracts.py.'), 'generated file ownership marker missing')
    check('as const satisfies FacilityDecisionProfile' in generated_text, 'generated TypeScript contract marker missing')

    runtime_text = (repo / 'src/facility-decision/runtime.ts').read_text(encoding='utf-8')
    checker_text = (repo / 'src/facility-decision-checker/verify.ts').read_text(encoding='utf-8')
    check('concrete_treatment_field_forbidden' in runtime_text, 'runtime concrete-treatment rejection missing')
    check('result without matching order' in runtime_text, 'runtime order-result integrity missing')
    check('decision record predecessor mismatch' in runtime_text, 'runtime decision-chain integrity missing')
    check('resource capacity exceeded' in runtime_text, 'runtime resource-capacity integrity missing')
    check('handoff transferred without complete closed loop' in runtime_text, 'runtime handoff integrity missing')
    check('learner leakage:' in runtime_text, 'runtime learner leakage audit missing')
    check('verifyFacilityDecisionSession' in checker_text, 'independent checker entry missing')
    check('../facility-decision/runtime' not in checker_text, 'independent checker imports producer runtime')

    metadata = {
        'checks': checks,
        'profile_id': profile.get('profile_id'),
        'decisions': len(decisions),
        'source_actions_bound': len(bound),
        'diagnostics': len(diagnostics),
        'treatment_policies': len(policies),
        'profile_sha256': sha256_bytes((repo / PROFILE).read_bytes()),
        'generated_sha256': sha256_bytes((repo / GENERATED).read_bytes()),
        'source_block_sha256': sha256_bytes(source_block.encode('utf-8')),
    }
    return sorted(set(errors)), metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--json-output', default=DEFAULT_REPORT.as_posix())
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    errors, metadata = verify(repo)
    report = {
        'schema_version': '1.0.0',
        'status': 'PASS' if not errors else 'FAIL',
        **metadata,
        'errors': errors,
    }
    output = repo / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
