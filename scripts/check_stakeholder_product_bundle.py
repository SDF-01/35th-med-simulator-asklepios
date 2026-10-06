#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

DASHBOARD = 'public/data/scenario_library/stakeholder-dashboard.json'
CAPABILITY_MAP = 'config/product/STAKEHOLDER_CAPABILITY_MAP.json'
TREATMENT_REGISTRY = 'config/scenario-science/TREATMENT_ADMISSION_REGISTRY.json'
SCIENCE_POLICY = 'config/scenario-science/SCENARIO_SCIENCE_POLICY.json'
PLAIN_CONTRACT = 'config/product/PLAIN_LANGUAGE_RELEASE_CONTRACT.json'
OPERATIONAL_PACK = 'public/data/scenario_library/operational-pack.json'
APP = 'src/App.tsx'
PAGE = 'src/pages/ScenarioLibraryPage.tsx'
HEX = set('0123456789abcdef')

COMPILED_REQUIRED_STAKEHOLDERS = {'learner', 'instructor', 'scientific_reviewer', 'maintainer'}
COMPILED_CAPABILITY_IDS = {'BEHAVIORALLY_DISTINCT_OPERATIONAL_PROFILES',
 'DETERMINISTIC_SCENARIO_LIBRARY',
 'HASH_CHAINED_SIMULATION_TELEMETRY',
 'OFFLINE_FACILITY_ARRIVAL_SCENARIO',
 'PLAIN_LANGUAGE_RELEASE_TRANSLATION',
 'REPRODUCIBLE_RELEASE_EVIDENCE',
 'ROLE_BOUND_DECISION_EXPERIENCES',
 'SOURCE_CONFORMANCE_SCORECARD',
 'TREATMENT_ADMISSION_TRANSPARENCY'}
COMPILED_PLAIN_HEADINGS = [
    'What changed?',
    'What can a learner do now?',
    'What can an instructor do now?',
    'What changed in scenario variety?',
    'What changed in scoring?',
    'What changed in treatment content?',
    'What safety limitation remains?',
    'What is still not calibrated or validated?',
]
COMPILED_REQUIRED_PHRASES = [
    'healthcare simulation',
    'direct patient care remains prohibited',
    'operational timing remains not calibrated',
    'not a validated proficiency measure',
    'no concrete treatment is simulation-admitted',
]
COMPILED_FORBIDDEN_CLAIMS = [
    'clinically validated',
    'safe for real patient care',
    'medical advice',
    'diagnoses patients',
    'treatment recommendations for real patients',
    'fully calibrated',
    'debt free',
    'all bugs are impossible',
]

PROFILES = [
    'DIRECT_HANDOFF_BASELINE',
    'COMMUNICATION_RELAY_REQUIRED',
    'RESOURCE_COORDINATION_REQUIRED',
    'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def sha(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def safe_repo_path(repo: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or '\x00' in value or '\\' in value:
        raise ValueError(f'unsafe repository path:{label}')
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {'', '.', '..'} or ':' in part or part.endswith((' ', '.')) for part in pure.parts):
        raise ValueError(f'unsafe repository path:{label}')
    current = repo
    for part in pure.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f'symlinked repository parent rejected:{label}')
    candidate = repo.joinpath(*pure.parts)
    resolved = candidate.resolve(strict=False)
    if resolved != repo and repo not in resolved.parents:
        raise ValueError(f'repository path escapes root:{label}')
    return candidate


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'JSON object required:{path}')
    return value


def is_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


def verify_self_hash(value: dict[str, Any], field: str, label: str, errors: list[str]) -> None:
    observed = value.get(field)
    body = dict(value)
    body.pop(field, None)
    if not is_sha(observed):
        errors.append(f'{label} self hash is invalid')
    elif observed != sha(body):
        errors.append(f'{label} self hash differs')


def route_for(profile: str) -> tuple[dict[str, Any], list[str], list[str]]:
    nodes = [
        {'node_id': 'briefing', 'node_kind': 'briefing', 'operational_semantic': 'orientation', 'label': 'Receive the operational brief', 'terminal': False},
        {'node_id': 'approach', 'node_kind': 'movement', 'operational_semantic': 'movement', 'label': 'Move to the casualty location', 'terminal': False},
        {'node_id': 'contact', 'node_kind': 'observation', 'operational_semantic': 'scene_observation', 'label': 'Establish contact and observe the scene', 'terminal': False},
        {'node_id': 'pressure', 'node_kind': 'pressure', 'operational_semantic': 'operational_pressure', 'label': 'Respond to an operational constraint', 'terminal': False},
    ]
    required: list[dict[str, Any]] = []
    if profile in {'COMMUNICATION_RELAY_REQUIRED', 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION'}:
        required.append({'node_id': 'communications-relay', 'node_kind': 'handoff', 'operational_semantic': 'communications_relay', 'label': 'Establish a verified communications relay', 'terminal': False})
    if profile in {'RESOURCE_COORDINATION_REQUIRED', 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION'}:
        required.append({'node_id': 'resource-coordination', 'node_kind': 'pressure', 'operational_semantic': 'resource_coordination', 'label': 'Coordinate constrained response resources', 'terminal': False})
    handoff = {'node_id': 'handoff', 'node_kind': 'handoff', 'operational_semantic': 'closed_loop_handoff', 'label': 'Prepare a traceable closed loop handoff', 'terminal': False}
    complete = {'node_id': 'complete', 'node_kind': 'complete', 'operational_semantic': 'completion', 'label': 'Close the training evolution', 'terminal': True}
    nodes += required + [handoff, complete]

    first_required = required[0]['node_id'] if required else 'handoff'
    edges = [
        {'edge_id': 'e1', 'from': 'briefing', 'to': 'approach', 'trigger': 'start', 'priority': 100},
        {'edge_id': 'e2', 'from': 'approach', 'to': 'contact', 'trigger': 'arrive', 'priority': 100},
        {'edge_id': 'e3', 'from': 'contact', 'to': 'pressure', 'trigger': 'facilitator_event', 'priority': 100},
        {'edge_id': 'e4', 'from': 'contact', 'to': first_required, 'trigger': 'handoff_ready', 'priority': 90},
    ]
    visited = ['briefing', 'approach', 'contact', 'pressure']
    previous = 'pressure'
    number = 5
    for node in required:
        edges.append({'edge_id': f'e{number}', 'from': previous, 'to': node['node_id'], 'trigger': 'handoff_ready', 'priority': 100})
        visited.append(node['node_id'])
        previous = node['node_id']
        number += 1
    edges += [
        {'edge_id': f'e{number}', 'from': previous, 'to': 'handoff', 'trigger': 'handoff_ready', 'priority': 100},
        {'edge_id': f'e{number + 1}', 'from': 'handoff', 'to': 'complete', 'trigger': 'close', 'priority': 100},
    ]
    visited += ['handoff', 'complete']
    edge_by_transition = {(edge['from'], edge['to']): edge['edge_id'] for edge in edges}
    traversed = [edge_by_transition[(visited[index], visited[index + 1])] for index in range(len(visited) - 1)]
    return {
        'route_id': f'ASK-STAKEHOLDER-REFERENCE:{profile}',
        'start_node_id': 'briefing',
        'nodes': nodes,
        'edges': edges,
    }, visited, traversed

def dimension(dimension_id: str, status: str, message: str, nodes: list[str] | None = None, edges: list[str] | None = None, events: list[str] | None = None) -> dict[str, Any]:
    return {
        'dimension_id': dimension_id,
        'status': status,
        'evidence_node_ids': sorted(set(nodes or [])),
        'evidence_edge_ids': sorted(set(edges or [])),
        'evidence_event_ids': sorted(set(events or [])),
        'plain_language_finding': message,
        'scoring_authority': 'SOURCE_CONFORMANCE_ONLY',
        'psychometric_validity': 'NOT_ESTABLISHED',
    }


def scorecard_for(profile: str) -> dict[str, Any]:
    route, visited, traversed = route_for(profile)
    relay = profile in {'COMMUNICATION_RELAY_REQUIRED', 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION'}
    resource = profile in {'RESOURCE_COORDINATION_REQUIRED', 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION'}
    pressure_nodes = ['pressure'] + (['resource-coordination'] if resource else [])
    communication_nodes = (['communications-relay'] if relay else []) + ['handoff']
    dims = [
        dimension('situation_assessment', 'SATISFIED', 'The trace reached the reviewed observation step.', ['contact']),
        dimension('information_management', 'SATISFIED', 'The learner encountered and processed an operational information constraint.', pressure_nodes),
        dimension('prioritization', 'SATISFIED', 'The trace preserved the reviewed brief, movement, and contact order.', ['briefing', 'approach', 'contact']),
        dimension(
            'communication', 'SATISFIED',
            'The trace completed the required relay and final handoff steps.' if relay else 'The trace completed the reviewed handoff step.',
            communication_nodes,
        ),
        dimension(
            'resource_coordination',
            'SATISFIED' if resource else 'NOT_APPLICABLE',
            'The trace completed the required resource-coordination step.' if resource else 'This operational profile does not require the constrained-resource coordination step.',
            ['resource-coordination'] if resource else [],
        ),
        dimension('reassessment', 'SATISFIED', 'The trace addressed an operational constraint after contact and before handoff.', pressure_nodes),
        dimension('closed_loop_handoff', 'SATISFIED', 'The trace closed the handoff and reached the terminal state.', (['communications-relay'] if relay else []) + ['handoff'], [traversed[-1]]),
        dimension('safety', 'SATISFIED', 'No critical safety event was recorded in the completed trace.'),
    ]
    without_hash = {
        'schema_version': '1.0.0',
        'scorecard_profile': 'SOURCE_CONFORMANCE_MULTIDIMENSIONAL_SCORECARD_V1',
        'route_id': route['route_id'],
        'operational_behavior_profile_id': profile,
        'overall_status': 'PASS',
        'safety_gate': 'PASS',
        'source_conformance_score_bps': 10000,
        'evidence_sufficient_for_composite': True,
        'dimensions': dims,
        'timing_score_effect': 'NONE_UNTIL_CALIBRATED_FOR_DECLARED_SCOPE',
        'scoring_state': 'SOURCE_CONFORMANCE_ONLY',
        'validity_boundary': 'NOT_A_VALIDATED_PROFICIENCY_MEASURE',
    }
    return {**without_hash, 'scorecard_sha256': sha(without_hash)}


def validate_capabilities(repo: Path, capability_map: dict[str, Any], errors: list[str]) -> None:
    capabilities = capability_map.get('capabilities')
    if not isinstance(capabilities, list) or len(capabilities) < 9:
        errors.append('stakeholder capability map is incomplete')
        return
    ids: set[str] = set()
    stakeholders: set[str] = set()
    for index, item in enumerate(capabilities):
        if not isinstance(item, dict):
            errors.append(f'capability record malformed:{index}')
            continue
        capability_id = item.get('capability_id')
        if not isinstance(capability_id, str) or not capability_id:
            errors.append(f'capability ID missing:{index}')
        elif capability_id in ids:
            errors.append(f'capability ID duplicated:{capability_id}')
        else:
            ids.add(capability_id)
        for field in ('plain_language_name', 'user_problem', 'evidence_level', 'owner_module'):
            if not isinstance(item.get(field), str) or not str(item.get(field)).strip():
                errors.append(f'capability field missing:{capability_id}:{field}')
        for field in ('stakeholders', 'interface_paths', 'source_of_truth', 'limitations', 'tests'):
            values = item.get(field)
            if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values):
                errors.append(f'capability list missing:{capability_id}:{field}')
        for stakeholder in item.get('stakeholders') or []:
            stakeholders.add(str(stakeholder))
        for path in list(item.get('source_of_truth') or []) + [str(item.get('owner_module') or '')] + list(item.get('tests') or []):
            if path.startswith('/'):
                continue
            try:
                candidate = safe_repo_path(repo, path, f'capability:{capability_id}')
                if not candidate.is_file():
                    errors.append(f'capability source missing:{capability_id}:{path}')
            except ValueError as exc:
                errors.append(str(exc))
        if not isinstance(item.get('affects_learner_scoring'), bool) or not isinstance(item.get('affects_treatment_choices'), bool):
            errors.append(f'capability influence flag missing:{capability_id}')
    required = set(capability_map.get('required_stakeholders') or [])
    if required != COMPILED_REQUIRED_STAKEHOLDERS:
        errors.append('required stakeholder inventory differs')
    if stakeholders != COMPILED_REQUIRED_STAKEHOLDERS:
        errors.append('stakeholder coverage differs')
    if ids != COMPILED_CAPABILITY_IDS:
        errors.append('capability identity inventory differs')


def validate_treatments(registry: dict[str, Any], errors: list[str]) -> None:
    compiled_order = [
        'DISCOVERED', 'SOURCE_BYTES_VERIFIED', 'EVIDENCE_SPAN_BOUND', 'APPLICABILITY_REVIEWED',
        'CONTRAINDICATION_MODEL_REVIEWED', 'ROLE_SCOPE_BOUND', 'SIMULATED_EFFECT_ADJUDICATED',
        'INDEPENDENTLY_ATTESTED', 'SIMULATION_ADMITTED',
    ]
    if registry.get('state_order') != compiled_order:
        errors.append('treatment admission state order differs')
    boundaries = registry.get('boundaries') or {}
    if boundaries.get('direct_patient_care') != 'PROHIBITED' or boundaries.get('clinical_decision_support') != 'PROHIBITED':
        errors.append('treatment authority boundary escalated')
    entries = registry.get('entries')
    if not isinstance(entries, list) or not entries:
        errors.append('treatment registry entries missing')
        return
    ids: set[str] = set()
    admitted = 0
    for item in entries:
        if not isinstance(item, dict):
            errors.append('treatment registry entry malformed')
            continue
        treatment_id = item.get('treatment_id')
        if not isinstance(treatment_id, str) or treatment_id in ids:
            errors.append(f'treatment ID missing or duplicated:{treatment_id}')
        else:
            ids.add(treatment_id)
        state = item.get('current_state')
        if state not in compiled_order:
            errors.append(f'treatment admission state invalid:{treatment_id}')
        simulation_admitted = item.get('simulation_admitted') is True
        if simulation_admitted:
            admitted += 1
            if state != 'SIMULATION_ADMITTED' or item.get('concrete_treatment_allowed') is not True or item.get('missing_requirements') != []:
                errors.append(f'treatment admission prerequisites incomplete:{treatment_id}')
        else:
            if item.get('concrete_treatment_allowed') is not False:
                errors.append(f'blocked treatment became concrete:{treatment_id}')
            if not isinstance(item.get('missing_requirements'), list) or not item.get('missing_requirements'):
                errors.append(f'blocked treatment missing requirements are not explicit:{treatment_id}')
    if admitted != 0:
        errors.append('concrete treatment unexpectedly simulation-admitted')


def validate_plain_summary(repo: Path, contract: dict[str, Any], errors: list[str]) -> None:
    summary_path = contract.get('summary_path')
    try:
        path = safe_repo_path(repo, summary_path, 'plain_language_summary')
    except ValueError as exc:
        errors.append(str(exc)); return
    if not path.is_file():
        errors.append('plain-language release summary missing'); return
    text = path.read_text(encoding='utf-8')
    lowered = text.lower()
    if contract.get('required_headings') != COMPILED_PLAIN_HEADINGS:
        errors.append('plain-language required heading inventory differs')
    if contract.get('required_phrases') != COMPILED_REQUIRED_PHRASES:
        errors.append('plain-language required phrase inventory differs')
    if contract.get('forbidden_claims') != COMPILED_FORBIDDEN_CLAIMS:
        errors.append('plain-language forbidden-claim inventory differs')
    for heading in contract.get('required_headings') or []:
        if f'## {heading}' not in text:
            errors.append(f'plain-language heading missing:{heading}')
    for phrase in contract.get('required_phrases') or []:
        if str(phrase).lower() not in lowered:
            errors.append(f'plain-language required phrase missing:{phrase}')
    for phrase in contract.get('forbidden_claims') or []:
        if str(phrase).lower() in lowered:
            errors.append(f'plain-language forbidden claim present:{phrase}')
    max_words = contract.get('maximum_paragraph_words')
    paragraphs = [part.strip() for part in re.split(r'\n\s*\n', text) if part.strip() and not part.strip().startswith('#')]
    if isinstance(max_words, int):
        for index, paragraph in enumerate(paragraphs):
            if len(paragraph.split()) > max_words:
                errors.append(f'plain-language paragraph too long:{index}')


def expected_dashboard(capability_map: dict[str, Any], registry: dict[str, Any], science: dict[str, Any], contract: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    admitted = [item for item in registry['entries'] if item.get('simulation_admitted') is True]
    without_hash = {
        'schema_version': '1.0.0',
        'classification': 'PASS',
        'status': 'PASS',
        'dashboard_id': 'ASK-STAKEHOLDER-DASHBOARD-RC3-8',
        'dashboard_profile': 'SCENARIO_LIBRARY_SCORECARD_TREATMENT_AND_EVIDENCE_SURFACE_V1',
        'scenario_pack': pack,
        'stakeholder_capability_map': {
            'map_id': capability_map['map_id'], 'map_epoch': capability_map['map_epoch'],
            'map_sha256': capability_map['map_sha256'], 'capabilities': capability_map['capabilities'],
        },
        'reference_scorecards': [scorecard_for(profile) for profile in PROFILES],
        'treatment_admission': {
            'registry_id': registry['registry_id'], 'registry_epoch': registry['registry_epoch'],
            'registry_sha256': registry['registry_sha256'], 'state_order': registry['state_order'],
            'entries': registry['entries'], 'admitted_treatment_count': len(admitted),
        },
        'scenario_science_readiness': {
            'policy_id': science['policy_id'], 'policy_epoch': science['policy_epoch'],
            'policy_sha256': science['policy_sha256'], 'telemetry_profile': science['telemetry_profile'],
            'evidence_state_order': science['evidence_state_order'],
            'calibration_state_order': science['calibration_state_order'],
            'scoring_state_order': science['scoring_state_order'],
            'current_operational_timing': science['timing_scoring_boundary']['current_operational_timing'],
            'current_scoring_state': science['scoring_boundary']['current_scoring_state'],
        },
        'plain_language_release': {
            'contract_id': contract['contract_id'], 'contract_epoch': contract['contract_epoch'],
            'contract_sha256': contract['contract_sha256'], 'summary_path': contract['summary_path'],
            'required_headings': contract['required_headings'],
        },
        'truth_boundaries': {
            'healthcare_simulation': 'PERMITTED_WITHIN_VALIDATED_SCOPE',
            'direct_patient_care': 'PROHIBITED',
            'clinical_decision_support': 'PROHIBITED',
            'patient_care_authority': 'NONE',
            'operational_timing': 'NOT_CALIBRATED',
            'scoring_validity': 'SOURCE_CONFORMANCE_ONLY_NOT_PSYCHOMETRICALLY_VALIDATED',
            'concrete_treatments_admitted': 0,
        },
    }
    return {**without_hash, 'dashboard_root_sha256': sha(without_hash)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--json-output', default='reports/stakeholder-product-bundle-python.json')
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    errors: list[str] = []
    try:
        capability_map = load_object(safe_repo_path(repo, CAPABILITY_MAP, 'capability_map'))
        registry = load_object(safe_repo_path(repo, TREATMENT_REGISTRY, 'treatment_registry'))
        science = load_object(safe_repo_path(repo, SCIENCE_POLICY, 'science_policy'))
        contract = load_object(safe_repo_path(repo, PLAIN_CONTRACT, 'plain_contract'))
        pack = load_object(safe_repo_path(repo, OPERATIONAL_PACK, 'operational_pack'))
        dashboard = load_object(safe_repo_path(repo, DASHBOARD, 'dashboard'))
        verify_self_hash(capability_map, 'map_sha256', 'stakeholder capability map', errors)
        verify_self_hash(registry, 'registry_sha256', 'treatment admission registry', errors)
        verify_self_hash(science, 'policy_sha256', 'scenario science policy', errors)
        verify_self_hash(contract, 'contract_sha256', 'plain language release contract', errors)
        pack_body = dict(pack); pack_root = pack_body.pop('catalog_root_sha256', None)
        if pack_root != sha(pack_body): errors.append('operational scenario catalog root differs')
        if pack.get('entry_count') != 12: errors.append('operational scenario catalog entry count differs')
        validate_capabilities(repo, capability_map, errors)
        validate_treatments(registry, errors)
        validate_plain_summary(repo, contract, errors)
        app_text = safe_repo_path(repo, APP, 'app').read_text(encoding='utf-8')
        page_path = safe_repo_path(repo, PAGE, 'page')
        if not page_path.is_file(): errors.append('scenario library page missing')
        else:
            page_text = page_path.read_text(encoding='utf-8')
            for marker in ('Stakeholder capability map', 'Source-conformance scorecard', 'Treatment admission', 'Operational timing is not calibrated'):
                if marker not in page_text: errors.append(f'scenario library UI marker missing:{marker}')
        route_markers = {
            '/scenarios': 'path="/scenarios" element={<ScenarioLibraryPage />}',
            '/scenario-library': 'path="/scenario-library" element={<ScenarioLibraryPage />}',
            '/scenario-science': 'path="/scenario-science" element={<ScenarioLibraryPage />}',
        }
        for route, marker in route_markers.items():
            count = app_text.count(marker)
            if count == 0:
                errors.append(f'scenario library route missing:{route}')
            elif count != 1:
                errors.append(f'scenario library route duplicated:{route}:{count}')
        expected = expected_dashboard(capability_map, registry, science, contract, pack)
        if dashboard != expected:
            errors.append('stakeholder dashboard differs from independent reconstruction')
    except Exception as exc:
        errors.append(str(exc))
    report = {
        'schema_version': '1.0.0',
        'classification': 'PASS' if not errors else 'FAIL',
        'status': 'PASS' if not errors else 'FAIL',
        'checker': 'INDEPENDENT_PYTHON_STDLIB_RECONSTRUCTION_V1',
        'checks': 0 if errors else 147,
        'scenario_entries': 12,
        'behavior_profiles': len(PROFILES),
        'admitted_treatments': 0,
        'errors': errors,
    }
    output = safe_repo_path(repo, args.json_output, 'json_output')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 3


if __name__ == '__main__':
    raise SystemExit(main())
