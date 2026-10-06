#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scenario_science_common import (
    COMPILED_ALLOWED_EVENT_KINDS,
    COMPILED_CALIBRATION_STATES,
    COMPILED_EVENT_HASH_PROFILE,
    COMPILED_EVIDENCE_STATES,
    COMPILED_FORBIDDEN_FIELD_TOKENS,
    COMPILED_POLICY_EPOCH,
    COMPILED_POLICY_ID,
    COMPILED_REQUIRED_EVENT_FIELDS,
    COMPILED_SCORING_STATES,
    COMPILED_TELEMETRY_PROFILE,
    GENOME_REL,
    POLICY_REL,
    TELEMETRY_REL,
    ScenarioScienceError,
    canonical_json,
    deterministic_hash,
    event_chain_root,
    event_sha256,
    policy_sha256,
    sha256_file,
    write_json_atomic,
)

HEX = set('0123456789abcdef')


def is_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


def collect_keys(value: Any, path: str = '$') -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.append((key.lower(), f'{path}.{key}'))
            found.extend(collect_keys(item, f'{path}.{key}'))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(collect_keys(item, f'{path}[{index}]'))
    return found


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ScenarioScienceError(f'JSON object required:{path}')
    return value


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    exact = {
        'policy_id': COMPILED_POLICY_ID,
        'policy_epoch': COMPILED_POLICY_EPOCH,
        'telemetry_profile': COMPILED_TELEMETRY_PROFILE,
        'event_hash_profile': COMPILED_EVENT_HASH_PROFILE,
        'evidence_state_order': COMPILED_EVIDENCE_STATES,
        'calibration_state_order': COMPILED_CALIBRATION_STATES,
        'scoring_state_order': COMPILED_SCORING_STATES,
        'required_event_fields': COMPILED_REQUIRED_EVENT_FIELDS,
        'allowed_event_kinds': COMPILED_ALLOWED_EVENT_KINDS,
        'forbidden_field_tokens': COMPILED_FORBIDDEN_FIELD_TOKENS,
    }
    for key, expected in exact.items():
        if policy.get(key) != expected:
            errors.append(f'policy compiled floor differs:{key}')
    if policy.get('policy_sha256') != policy_sha256(policy):
        errors.append('policy self hash differs')
    boundaries = policy.get('telemetry_boundaries') or {}
    expected_boundaries = {
        'protected_health_information': 'PROHIBITED',
        'direct_patient_care': 'PROHIBITED',
        'clinical_decision_support': 'PROHIBITED',
        'patient_care_authority': 'NONE',
        'wall_clock_in_deterministic_event_hash': False,
        'logical_time_must_be_monotonic': True,
        'sequence_must_be_contiguous': True,
        'event_hash_chain_required': True,
    }
    for key, expected in expected_boundaries.items():
        if boundaries.get(key) != expected:
            errors.append(f'policy authority or telemetry boundary differs:{key}')
    timing = policy.get('timing_scoring_boundary') or {}
    if timing.get('uncalibrated_timing_may_change_learner_score') is not False:
        errors.append('uncalibrated timing may change learner score')
    if timing.get('minimum_state_for_timing_score_effect') != 'CALIBRATED_FOR_DECLARED_SCOPE':
        errors.append('timing scoring promotion floor differs')
    scoring = policy.get('scoring_boundary') or {}
    if scoring.get('critical_safety_failure_overridable_by_statistical_score') is not False:
        errors.append('statistical score may override critical safety failure')
    if scoring.get('insufficient_evidence_output') != 'INSUFFICIENT_EVIDENCE':
        errors.append('insufficient evidence output differs')
    novelty = policy.get('behavioral_novelty_boundary') or {}
    for key in ('narrative_only_variant_creates_new_behavior', 'provenance_only_variant_creates_new_behavior', 'seed_only_variant_creates_new_behavior'):
        if novelty.get(key) is not False:
            errors.append(f'cosmetic variant may create new behavior:{key}')
    if policy.get('automatic_clinical_authority_promotion_permitted') is not False:
        errors.append('automatic clinical authority promotion enabled')
    return errors


def build_reference(repo: Path, policy: dict[str, Any]) -> dict[str, Any]:
    genome_path = repo / GENOME_REL
    genome = load_json(genome_path)
    genome_id = genome.get('genome_id')
    genome_sha = genome.get('genome_sha256')
    if not isinstance(genome_id, str) or not is_sha(genome_sha):
        raise ScenarioScienceError('current Scenario Genome identity is invalid')

    state0 = deterministic_hash('state:initial')
    state1 = deterministic_hash('state:handoff-received')
    state2 = deterministic_hash('state:second-casualty-visible')
    state3 = deterministic_hash('state:completed')
    event_specs = [
        {
            'event_id': 'science-run-started',
            'event_kind': 'RUN_STARTED',
            'logical_time_seconds': 0,
            'actor_role': 'SYSTEM',
            'state_before_sha256': None,
            'state_after_sha256': state0,
            'calibration_use': 'DETERMINISTIC_SIMULATION_ONLY',
            'scoring_effect': 'NONE',
            'payload': {'scenario_genome_id': genome_id},
        },
        {
            'event_id': 'science-command-receive-handoff',
            'event_kind': 'COMMAND_ADMITTED',
            'logical_time_seconds': 0,
            'actor_role': 'LEARNER',
            'state_before_sha256': state0,
            'state_after_sha256': state1,
            'calibration_use': 'DETERMINISTIC_SIMULATION_ONLY',
            'scoring_effect': 'SOURCE_BOUND_OBJECTIVE_ONLY',
            'payload': {'command_id': 'receive_handoff'},
        },
        {
            'event_id': 'science-world-event-second-casualty',
            'event_kind': 'WORLD_EVENT_FIRED',
            'logical_time_seconds': 240,
            'actor_role': 'SYSTEM',
            'state_before_sha256': state1,
            'state_after_sha256': state2,
            'calibration_use': 'EXERCISE_ASSUMPTION_NOT_CLINICAL_CALIBRATION',
            'scoring_effect': 'NONE',
            'payload': {'world_event_id': 'second_casualty_inbound'},
        },
        {
            'event_id': 'science-run-terminated',
            'event_kind': 'RUN_TERMINATED',
            'logical_time_seconds': 645,
            'actor_role': 'SYSTEM',
            'state_before_sha256': state2,
            'state_after_sha256': state3,
            'calibration_use': 'DETERMINISTIC_SIMULATION_ONLY',
            'scoring_effect': 'SOURCE_BOUND_OBJECTIVE_ONLY',
            'payload': {'terminal_status': 'completed'},
        },
    ]
    events: list[dict[str, Any]] = []
    previous: str | None = None
    for sequence, spec in enumerate(event_specs):
        event = {
            'sequence': sequence,
            **spec,
            'previous_event_sha256': previous,
        }
        event['event_sha256'] = event_sha256(event)
        previous = event['event_sha256']
        events.append(event)

    telemetry = {
        'schema_version': '1.0.0',
        'telemetry_profile': COMPILED_TELEMETRY_PROFILE,
        'event_hash_profile': COMPILED_EVENT_HASH_PROFILE,
        'policy_id': policy['policy_id'],
        'policy_sha256': policy['policy_sha256'],
        'scenario_genome_id': genome_id,
        'scenario_genome_sha256': genome_sha,
        'scenario_genome_file_sha256': sha256_file(genome_path),
        'run_id': 'ASK-SCIENCE-RUN-REFERENCE-V1',
        'deterministic_seed': 0,
        'session_pseudonym': 'REFERENCE_SESSION_NON_PERSONAL',
        'current_calibration_state': 'EXERCISE_ASSUMPTION',
        'current_scoring_state': 'SOURCE_CONFORMANCE_ONLY',
        'events': events,
        'event_chain_root_sha256': event_chain_root(events),
        'truth_boundaries': {
            'protected_health_information': 'PROHIBITED',
            'direct_patient_care': 'PROHIBITED',
            'clinical_decision_support': 'PROHIBITED',
            'patient_care_authority': 'NONE',
            'operational_timing': 'NOT_CALIBRATED',
            'human_team_behavior': 'STRUCTURAL_ONLY_NOT_CALIBRATED',
            'patient_dynamics': 'SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY',
        },
    }
    return telemetry


def validate_telemetry(repo: Path, policy: dict[str, Any], telemetry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if telemetry.get('telemetry_profile') != COMPILED_TELEMETRY_PROFILE:
        errors.append('telemetry profile differs')
    if telemetry.get('event_hash_profile') != COMPILED_EVENT_HASH_PROFILE:
        errors.append('event hash profile differs')
    if telemetry.get('policy_id') != policy.get('policy_id') or telemetry.get('policy_sha256') != policy.get('policy_sha256'):
        errors.append('telemetry policy binding differs')

    genome = load_json(repo / GENOME_REL)
    if telemetry.get('scenario_genome_id') != genome.get('genome_id'):
        errors.append('telemetry Scenario Genome ID differs')
    if telemetry.get('scenario_genome_sha256') != genome.get('genome_sha256'):
        errors.append('telemetry Scenario Genome hash differs')
    if telemetry.get('scenario_genome_file_sha256') != sha256_file(repo / GENOME_REL):
        errors.append('telemetry Scenario Genome file hash differs')

    forbidden = {token.lower() for token in COMPILED_FORBIDDEN_FIELD_TOKENS}
    for key, path in collect_keys(telemetry):
        if key in forbidden:
            errors.append(f'forbidden privacy field:{path}')
        if key in {'wall_clock', 'wall_clock_ms', 'timestamp', 'patient_free_text'}:
            errors.append(f'forbidden deterministic telemetry field:{path}')

    events = telemetry.get('events')
    if not isinstance(events, list) or not events:
        errors.append('telemetry events missing')
        return errors
    if events[-1].get('event_kind') != 'RUN_TERMINATED':
        errors.append('terminal telemetry event missing')
    previous_hash: str | None = None
    previous_time = -1
    seen_ids: set[str] = set()
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            errors.append(f'event is not an object:{index}')
            continue
        missing = [field for field in COMPILED_REQUIRED_EVENT_FIELDS if field not in event]
        if missing:
            errors.append(f'event required fields missing:{index}:{",".join(missing)}')
        if event.get('sequence') != index:
            errors.append(f'event sequence is not contiguous:{index}')
        logical = event.get('logical_time_seconds')
        if not isinstance(logical, int) or isinstance(logical, bool) or logical < 0:
            errors.append(f'event logical time invalid:{index}')
        elif logical < previous_time:
            errors.append(f'event logical time regressed:{index}')
        else:
            previous_time = logical
        event_id = event.get('event_id')
        if not isinstance(event_id, str) or not event_id:
            errors.append(f'event ID invalid:{index}')
        elif event_id in seen_ids:
            errors.append(f'event ID duplicated:{event_id}')
        else:
            seen_ids.add(event_id)
        if event.get('event_kind') not in COMPILED_ALLOWED_EVENT_KINDS:
            errors.append(f'event kind is not allowed:{index}')
        if event.get('previous_event_sha256') != previous_hash:
            errors.append(f'event previous hash differs:{index}')
        expected_hash = event_sha256(event)
        if event.get('event_sha256') != expected_hash:
            errors.append(f'event hash differs:{index}')
        previous_hash = event.get('event_sha256') if is_sha(event.get('event_sha256')) else None
        calibration_use = str(event.get('calibration_use') or '')
        scoring_effect = str(event.get('scoring_effect') or '')
        if 'NOT_CLINICAL_CALIBRATION' in calibration_use and scoring_effect != 'NONE':
            errors.append(f'uncalibrated timing changed score:{index}')
    if telemetry.get('event_chain_root_sha256') != event_chain_root(events):
        errors.append('event-chain root differs')
    boundaries = telemetry.get('truth_boundaries') or {}
    expected_boundaries = {
        'protected_health_information': 'PROHIBITED',
        'direct_patient_care': 'PROHIBITED',
        'clinical_decision_support': 'PROHIBITED',
        'patient_care_authority': 'NONE',
        'operational_timing': 'NOT_CALIBRATED',
        'human_team_behavior': 'STRUCTURAL_ONLY_NOT_CALIBRATED',
        'patient_dynamics': 'SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY',
    }
    for key, expected in expected_boundaries.items():
        if boundaries.get(key) != expected:
            errors.append(f'telemetry truth boundary differs:{key}')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--json-output')
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    policy = load_json(repo / POLICY_REL)
    errors = validate_policy(policy)
    expected = build_reference(repo, policy)
    telemetry_path = repo / TELEMETRY_REL
    if args.check:
        if not telemetry_path.is_file():
            errors.append('reference telemetry missing')
            observed: dict[str, Any] = {}
        else:
            observed = load_json(telemetry_path)
            if canonical_json(observed) != canonical_json(expected):
                errors.append('reference telemetry differs from canonical reconstruction')
    else:
        write_json_atomic(telemetry_path, expected)
        observed = expected
    if observed:
        errors.extend(validate_telemetry(repo, policy, observed))
    result = {
        'schema_version': '1.0.0',
        'classification': 'PASS' if not errors else 'FAIL',
        'status': 'PASS' if not errors else 'FAIL',
        'mode': 'check' if args.check else 'write',
        'policy_id': policy.get('policy_id'),
        'policy_sha256': policy.get('policy_sha256'),
        'telemetry_profile': COMPILED_TELEMETRY_PROFILE,
        'events': len((observed or {}).get('events', [])) if isinstance(observed, dict) else 0,
        'event_chain_root_sha256': (observed or {}).get('event_chain_root_sha256') if isinstance(observed, dict) else None,
        'errors': sorted(set(errors)),
    }
    if args.json_output:
        write_json_atomic(repo / args.json_output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 3


if __name__ == '__main__':
    raise SystemExit(main())
