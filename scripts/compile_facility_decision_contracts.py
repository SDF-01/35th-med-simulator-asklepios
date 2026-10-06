#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

SOURCE = Path('config/facility-decision/ASK-D-001.json')
TARGET = Path('src/facility-decision/contracts.generated.ts')
REPORT = Path('reports/facility-decision-contract-compiler.json')

EXPECTED_SOURCE_ACTIONS = {
    'primary_assessment', 'order_imaging', 'order_labs',
    'differential', 'monitor_vitals', 'escalation',
}
REQUIRED_UI_MODES = {'learner_assessment', 'learner_teaching', 'instructor', 'stakeholder_demo'}
FORBIDDEN_CLINICAL_KEYS = {
    'medication', 'medication_name', 'dose', 'dose_unit', 'route',
    'procedure', 'procedure_code', 'device_setting',
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def reject_unsafe_numbers(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            errors.append(f'nonfinite number:{path}')
        else:
            errors.append(f'floating point forbidden:{path}')
    elif isinstance(value, int) and abs(value) > 9_007_199_254_740_991:
        errors.append(f'unsafe integer:{path}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_unsafe_numbers(item, f'{path}[{index}]', errors)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                errors.append(f'non-string key:{path}')
                continue
            reject_unsafe_numbers(item, f'{path}.{key}', errors)


def validate(profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    reject_unsafe_numbers(profile, '$', errors)
    if profile.get('schema_version') != '1.0.0':
        errors.append('schema_version differs')
    if profile.get('source_scenario_id') != 'ASK-D-001':
        errors.append('source_scenario_id differs')
    authority = profile.get('authority')
    if not isinstance(authority, dict):
        errors.append('authority missing')
    else:
        if authority.get('patient_care_use') != 'PROHIBITED':
            errors.append('patient-care authority escalation')
        if authority.get('concrete_treatment_activation') is not False:
            errors.append('concrete treatment activation must be false')
        if authority.get('operational_parameters_calibrated') is not False:
            errors.append('uncalibrated operational parameters promoted')
    ui_modes = profile.get('ui_modes')
    if not isinstance(ui_modes, dict) or set(ui_modes) != REQUIRED_UI_MODES:
        errors.append('ui mode inventory differs')
    else:
        learner = ui_modes.get('learner_assessment', {})
        for field in [
            'show_live_score', 'show_source_points', 'show_source_origin',
            'show_provenance', 'show_wit', 'show_autoplay',
            'show_completed_replay', 'show_correctness_labels',
            'show_disabled_reasons',
        ]:
            if learner.get(field) is not False:
                errors.append(f'learner assessment leakage:{field}')
    decisions = profile.get('decisions')
    if not isinstance(decisions, list) or not decisions:
        errors.append('decisions missing')
        decisions = []
    decision_ids: set[str] = set()
    action_ids: set[str] = set()
    mapped_source_actions: set[str] = set()
    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            errors.append(f'decision not object:{index}')
            continue
        did = decision.get('decision_id')
        action = decision.get('facility_action_id')
        if not isinstance(did, str) or not did:
            errors.append(f'decision id missing:{index}')
        elif did in decision_ids:
            errors.append(f'duplicate decision id:{did}')
        else:
            decision_ids.add(did)
        if not isinstance(action, str) or not action:
            errors.append(f'facility action missing:{did}')
        elif action in action_ids:
            errors.append(f'duplicate facility action mapping:{action}')
        else:
            action_ids.add(action)
        source_action = decision.get('source_action_id')
        if isinstance(source_action, str):
            mapped_source_actions.add(source_action)
        fields = decision.get('fields')
        if not isinstance(fields, list) or not fields:
            errors.append(f'decision fields missing:{did}')
            fields = []
        field_ids: set[str] = set()
        for field in fields:
            if not isinstance(field, dict):
                errors.append(f'field not object:{did}')
                continue
            fid = field.get('field_id')
            if not isinstance(fid, str) or not fid:
                errors.append(f'field id missing:{did}')
            elif fid in field_ids:
                errors.append(f'duplicate field id:{did}:{fid}')
            else:
                field_ids.add(fid)
            if field.get('type') not in {'text', 'boolean', 'choice', 'multi_choice', 'list'}:
                errors.append(f'field type invalid:{did}:{fid}')
        if decision.get('high_risk') is True:
            if 'deliberate_confirmation' not in field_ids or 'rationale' not in field_ids:
                errors.append(f'high-risk confirmation incomplete:{did}')
        if not isinstance(decision.get('repeatable'), bool):
            errors.append(f'repeatable flag missing:{did}')
        if decision.get('repeatable') is True and did != 'wait_60':
            errors.append(f'unreviewed repeatable decision:{did}')
        treatment_policy = decision.get('treatment_policy_id')
        if treatment_policy is not None and not isinstance(treatment_policy, str):
            errors.append(f'treatment policy invalid:{did}')
        if treatment_policy is not None and any(fid in FORBIDDEN_CLINICAL_KEYS for fid in field_ids):
            errors.append(f'concrete treatment field declared:{did}')
        if source_action is None and decision.get('governing_source', {}).get('authority_class') == 'INHERITED_TEMPLATE':
            errors.append(f'operational decision falsely claims inherited clinical authority:{did}')
    missing_source_actions = EXPECTED_SOURCE_ACTIONS - mapped_source_actions
    if missing_source_actions:
        errors.append('critical/important source contracts missing:' + ','.join(sorted(missing_source_actions)))
    known_decisions = decision_ids
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        did = decision.get('decision_id', '?')
        for prerequisite in decision.get('prerequisites', []):
            if prerequisite not in known_decisions:
                errors.append(f'unknown decision prerequisite:{did}:{prerequisite}')
    treatment_policies = profile.get('treatment_policies')
    if not isinstance(treatment_policies, list) or not treatment_policies:
        errors.append('treatment policies missing')
        treatment_policies = []
    policy_ids: set[str] = set()
    for policy in treatment_policies:
        if not isinstance(policy, dict):
            errors.append('treatment policy not object')
            continue
        pid = policy.get('treatment_id')
        if not isinstance(pid, str) or not pid:
            errors.append('treatment id missing')
            continue
        if pid in policy_ids:
            errors.append(f'duplicate treatment policy:{pid}')
        policy_ids.add(pid)
        if policy.get('concrete_treatment_allowed') is not False:
            errors.append(f'concrete treatment enabled:{pid}')
        if policy.get('governing_rule_status') != 'NOT_ADJUDICATED':
            errors.append(f'treatment governing rule self-adjudicated:{pid}')
        if policy.get('effect_model_status') != 'BLOCKED':
            errors.append(f'treatment effect model activated:{pid}')
        forbidden = set(policy.get('forbidden_submission_keys', []))
        if not forbidden:
            errors.append(f'treatment forbidden keys missing:{pid}')
        if pid == 'PAIN_MANAGEMENT_OBJECTIVE' and not FORBIDDEN_CLINICAL_KEYS.issubset(forbidden):
            errors.append('pain policy does not block every concrete treatment field')
    for decision in decisions:
        if isinstance(decision, dict) and decision.get('treatment_policy_id') not in (None, *policy_ids):
            errors.append(f'unknown treatment policy:{decision.get("decision_id")}')
    diagnostics = profile.get('diagnostic_catalog')
    if not isinstance(diagnostics, list) or not diagnostics:
        errors.append('diagnostic catalog missing')
        diagnostics = []
    result_ids: set[str] = set()
    order_codes: set[str] = set()
    diagnostic_resource_ids: set[str] = set()
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, dict):
            errors.append('diagnostic not object')
            continue
        result_id = diagnostic.get('result_id')
        order_code = diagnostic.get('order_code')
        if not isinstance(result_id, str) or not result_id:
            errors.append('diagnostic result id missing')
        elif result_id in result_ids:
            errors.append(f'duplicate result id:{result_id}')
        else:
            result_ids.add(result_id)
        if not isinstance(order_code, str) or not order_code:
            errors.append('diagnostic order code missing')
        else:
            order_codes.add(order_code)
        if not diagnostic.get('source_pointer'):
            errors.append(f'diagnostic source pointer missing:{result_id}')
        resource_id = diagnostic.get('resource_id')
        if not isinstance(resource_id, str) or not resource_id:
            errors.append(f'diagnostic resource missing:{result_id}')
        else:
            diagnostic_resource_ids.add(resource_id)
    order_producers: dict[str, list[str]] = {code: [] for code in order_codes}
    result_consumers: dict[str, list[str]] = {rid: [] for rid in result_ids}
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        did = decision.get('decision_id', '?')
        for order_code in decision.get('creates_orders', []):
            if order_code not in order_codes:
                errors.append(f'unknown created order:{did}:{order_code}')
            else:
                order_producers[order_code].append(str(did))
        for result_id in decision.get('requires_results', []):
            if result_id not in result_ids:
                errors.append(f'unknown required result:{did}:{result_id}')
            else:
                result_consumers[result_id].append(str(did))
    for code, producers in order_producers.items():
        if len(producers) != 1:
            errors.append(f'diagnostic order producer count differs:{code}:{len(producers)}')
    for result_id, consumers in result_consumers.items():
        if not consumers:
            errors.append(f'diagnostic result has no consuming decision:{result_id}')
    world = profile.get('operational_model')
    if not isinstance(world, dict):
        errors.append('operational model missing')
    else:
        events = world.get('world_events')
        if not isinstance(events, list) or not events:
            errors.append('world event schedule missing')
        else:
            event_ids: set[str] = set()
            for event in events:
                event_id = event.get('event_id')
                if not isinstance(event_id, str) or not event_id:
                    errors.append('world event id missing')
                elif event_id in event_ids:
                    errors.append(f'duplicate world event:{event_id}')
                else:
                    event_ids.add(event_id)
                if event.get('calibration_status') != 'NOT_CALIBRATED':
                    errors.append(f'world event falsely calibrated:{event_id}')
                if 'trigger_action_id' in event:
                    errors.append(f'exogenous event tied to learner action:{event_id}')
                if not isinstance(event.get('at_elapsed_seconds'), int) or event.get('at_elapsed_seconds', -1) < 0:
                    errors.append(f'world event time invalid:{event_id}')
        resources = world.get('resources')
        resource_ids: set[str] = set()
        if not isinstance(resources, list) or not resources:
            errors.append('operational resources missing')
        else:
            for resource in resources:
                if not isinstance(resource, dict):
                    errors.append('resource not object')
                    continue
                rid = resource.get('resource_id')
                if not isinstance(rid, str) or not rid:
                    errors.append('resource id missing')
                    continue
                if rid in resource_ids:
                    errors.append(f'duplicate resource:{rid}')
                resource_ids.add(rid)
                if not isinstance(resource.get('capacity'), int) or resource.get('capacity', 0) < 1:
                    errors.append(f'resource capacity invalid:{rid}')
                if resource.get('queue_policy') != 'FIFO':
                    errors.append(f'resource queue policy differs:{rid}')
                if not isinstance(resource.get('service_duration_seconds'), int) or resource.get('service_duration_seconds', 0) < 1:
                    errors.append(f'resource service duration invalid:{rid}')
                if resource.get('calibration_status') != 'NOT_CALIBRATED':
                    errors.append(f'resource falsely calibrated:{rid}')
        for rid in sorted(diagnostic_resource_ids - resource_ids):
            errors.append(f'diagnostic resource undefined:{rid}')
        patient_policy = world.get('patient_observation_policy')
        if not isinstance(patient_policy, dict):
            errors.append('patient observation policy missing')
        else:
            if patient_policy.get('mode') != 'SOURCE_BOUND_OBSERVATIONS_ONLY':
                errors.append('patient observation mode differs')
            if patient_policy.get('dynamic_physiology_validated') is not False:
                errors.append('dynamic physiology falsely validated')
            if patient_policy.get('latent_state_exposed_to_learner') is not False:
                errors.append('latent state exposure enabled')
    assurance = profile.get('assurance')
    if not isinstance(assurance, dict):
        errors.append('assurance obligations missing')
    else:
        sequences = assurance.get('reference_sequences')
        if not isinstance(sequences, dict) or set(sequences) != {'canonical', 'alternate'}:
            errors.append('reference sequence inventory differs')
        else:
            for name, sequence in sequences.items():
                if not isinstance(sequence, list) or not sequence:
                    errors.append(f'reference sequence missing:{name}')
                    continue
                for decision_id in sequence:
                    if decision_id not in decision_ids:
                        errors.append(f'reference sequence unknown decision:{name}:{decision_id}')
                if sequence[-1] != 'complete_handoff':
                    errors.append(f'reference sequence does not close handoff:{name}')
            if sequences.get('canonical') == sequences.get('alternate'):
                errors.append('reference sequences are not materially distinct')
        pairs = assurance.get('ordered_pair_obligations')
        triples = assurance.get('ordered_triple_obligations')
        if not isinstance(pairs, list) or len(pairs) < 10:
            errors.append('ordered pair obligations weakened')
        if not isinstance(triples, list) or len(triples) < 5:
            errors.append('ordered triple obligations weakened')
        for group_name, obligations, size in [('pair', pairs if isinstance(pairs, list) else [], 2), ('triple', triples if isinstance(triples, list) else [], 3)]:
            for obligation in obligations:
                if not isinstance(obligation, list) or len(obligation) != size or any(item not in decision_ids for item in obligation):
                    errors.append(f'invalid ordered {group_name} obligation')
        bounds = assurance.get('bounded_exploration')
        if not isinstance(bounds, dict):
            errors.append('bounded exploration policy missing')
        else:
            if bounds.get('max_decision_depth') != 20:
                errors.append('bounded exploration depth differs')
            if bounds.get('max_repeatable_waits') != 20:
                errors.append('repeatable wait bound differs')
            required = set(bounds.get('required_terminal_witnesses', []))
            expected = {'completed_canonical','completed_alternate','failed_discharge','failed_tourniquet','timeout'}
            if required != expected:
                errors.append('terminal witness inventory differs')
    return sorted(set(errors))


def render(profile: dict[str, Any], source_sha: str) -> str:
    pretty = json.dumps(profile, indent=2, ensure_ascii=False)
    return (
        "// Generated by scripts/compile_facility_decision_contracts.py. Do not edit by hand.\n"
        "import type { FacilityDecisionProfile } from './types';\n\n"
        f"export const FACILITY_DECISION_PROFILE_SOURCE_SHA256 = '{source_sha}';\n\n"
        "export const FACILITY_DECISION_PROFILE = "
        + pretty
        + " as const satisfies FacilityDecisionProfile;\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--json-output')
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    source = repo / SOURCE
    target = repo / TARGET
    report_path = repo / (Path(args.json_output) if args.json_output else REPORT)
    errors: list[str] = []
    if not source.is_file():
        errors.append(f'source missing:{SOURCE.as_posix()}')
        profile: dict[str, Any] = {}
        source_bytes = b''
    else:
        source_bytes = source.read_bytes()
        try:
            profile = json.loads(source_bytes)
        except Exception as exc:
            errors.append(f'source JSON invalid:{type(exc).__name__}')
            profile = {}
    if profile:
        errors.extend(validate(profile))
    source_sha = sha256_bytes(source_bytes)
    expected = render(profile, source_sha) if profile else ''
    if args.check:
        if not target.is_file():
            errors.append(f'target missing:{TARGET.as_posix()}')
        elif target.read_text(encoding='utf-8') != expected:
            errors.append('generated TypeScript differs')
    elif not errors:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(expected, encoding='utf-8', newline='\n')
    report = {
        'schema_version': '1.0.0',
        'status': 'PASS' if not errors else 'FAIL',
        'mode': 'check' if args.check else 'write',
        'source': SOURCE.as_posix(),
        'target': TARGET.as_posix(),
        'source_sha256': source_sha,
        'target_sha256': sha256_bytes(expected.encode('utf-8')) if expected else '',
        'decision_count': len(profile.get('decisions', [])) if isinstance(profile, dict) else 0,
        'treatment_policy_count': len(profile.get('treatment_policies', [])) if isinstance(profile, dict) else 0,
        'diagnostic_count': len(profile.get('diagnostic_catalog', [])) if isinstance(profile, dict) else 0,
        'errors': sorted(set(errors)),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
