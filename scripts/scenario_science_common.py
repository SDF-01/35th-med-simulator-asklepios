from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

POLICY_REL = Path('config/scenario-science/SCENARIO_SCIENCE_POLICY.json')
TELEMETRY_REL = Path('examples/scenario-science/reference-telemetry.json')
GENOME_REL = Path('public/data/scenario_core/verified_scenario_genome.json')

COMPILED_POLICY_ID = 'asklepios-scenario-science-policy-v1'
COMPILED_POLICY_EPOCH = 1
COMPILED_TELEMETRY_PROFILE = 'HASH_CHAINED_PRIVACY_BOUNDED_SIMULATION_TELEMETRY_V1'
COMPILED_EVENT_HASH_PROFILE = 'SHA256_PREVIOUS_HASH_PLUS_CANONICAL_EVENT_V1'
COMPILED_EVIDENCE_STATES = [
    'DISCOVERED',
    'IDENTITY_VERIFIED',
    'SPAN_BOUND',
    'APPLICABILITY_REVIEWED',
    'CONTRADICTION_CLEARED',
    'SUPERSESSION_CLEARED',
    'INDEPENDENTLY_ATTESTED',
    'ADMITTED',
]
COMPILED_CALIBRATION_STATES = [
    'EXERCISE_ASSUMPTION',
    'DATASET_BOUND',
    'MODEL_FIT',
    'SIMULATION_BASED_CALIBRATION_PASSED',
    'TEMPORAL_HOLDOUT_PASSED',
    'SITE_HOLDOUT_PASSED',
    'UNCERTAINTY_BOUND',
    'DRIFT_RULE_DEFINED',
    'CALIBRATED_FOR_DECLARED_SCOPE',
]
COMPILED_SCORING_STATES = [
    'SOURCE_CONFORMANCE_ONLY',
    'EVIDENCE_MODEL_DEFINED',
    'PILOT_RELIABILITY_ESTIMATED',
    'HELD_OUT_CALIBRATED',
    'MULTISITE_VALIDATED',
]
COMPILED_REQUIRED_EVENT_FIELDS = [
    'sequence',
    'event_id',
    'event_kind',
    'logical_time_seconds',
    'actor_role',
    'state_before_sha256',
    'state_after_sha256',
    'calibration_use',
    'scoring_effect',
    'previous_event_sha256',
    'event_sha256',
]
COMPILED_ALLOWED_EVENT_KINDS = [
    'RUN_STARTED',
    'COMMAND_ADMITTED',
    'WORLD_EVENT_FIRED',
    'RESOURCE_STATE_CHANGED',
    'INFORMATION_RELEASED',
    'FACILITATOR_INTERVENTION',
    'RUN_TERMINATED',
]
COMPILED_FORBIDDEN_FIELD_TOKENS = [
    'patient_name',
    'full_name',
    'date_of_birth',
    'dob',
    'medical_record_number',
    'mrn',
    'street_address',
    'email_address',
    'phone_number',
    'free_text_patient_identifier',
]


class ScenarioScienceError(ValueError):
    pass


def canonical_value(value: Any, path: str = '$') -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        raise ScenarioScienceError(f'floating-point value forbidden in canonical science artifact:{path}')
    if isinstance(value, list):
        return [canonical_value(item, f'{path}[{index}]') for index, item in enumerate(value)]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str) or not key:
                raise ScenarioScienceError(f'invalid canonical object key:{path}')
            result[key] = canonical_value(value[key], f'{path}.{key}')
        return result
    raise ScenarioScienceError(f'unsupported canonical value:{path}:{type(value).__name__}')


def canonical_json(value: Any) -> str:
    return json.dumps(canonical_value(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def policy_sha256(policy: dict[str, Any]) -> str:
    body = dict(policy)
    body.pop('policy_sha256', None)
    return sha256_text(canonical_json(body))


def event_sha256(event: dict[str, Any]) -> str:
    body = dict(event)
    body.pop('event_sha256', None)
    previous = body.get('previous_event_sha256')
    prefix = '' if previous is None else str(previous)
    return sha256_text(prefix + '\n' + canonical_json(body))


def event_chain_root(events: list[dict[str, Any]]) -> str:
    return sha256_text(canonical_json([event.get('event_sha256') for event in events]))


def deterministic_hash(label: str) -> str:
    return sha256_text(f'asklepios-scenario-science-v1:{label}')


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    temp.replace(path)
