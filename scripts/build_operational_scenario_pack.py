#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

POLICY_REL = Path('config/scenario-science/OPERATIONAL_SCENARIO_PACK_POLICY.json')
HEX = set('0123456789abcdef')
COMPILED_REQUIRED_PROFILES = (
    'DIRECT_HANDOFF_BASELINE',
    'COMMUNICATION_RELAY_REQUIRED',
    'RESOURCE_COORDINATION_REQUIRED',
    'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()




def safe_repo_path(repo: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError(f'unsafe repository path:{label}')
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {'', '.', '..'} or ':' in part or part.endswith((' ', '.')) for part in pure.parts):
        raise ValueError(f'unsafe repository path:{label}')
    candidate = repo.joinpath(*pure.parts)
    current = repo
    for part in pure.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f'symlinked repository parent rejected:{label}')
    resolved = candidate.resolve(strict=False)
    if repo != resolved and repo not in resolved.parents:
        raise ValueError(f'repository path escapes root:{label}')
    return candidate

def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'JSON object required:{path}')
    return value


def atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    temp.replace(path)


def policy_hash(policy: dict[str, Any]) -> str:
    body = dict(policy)
    body.pop('policy_sha256', None)
    return sha256_value(body)


def is_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


PROFILE_LABELS = {
    'DIRECT_HANDOFF_BASELINE': 'Direct handoff',
    'COMMUNICATION_RELAY_REQUIRED': 'Communications relay',
    'RESOURCE_COORDINATION_REQUIRED': 'Resource coordination',
    'DUAL_CONSTRAINT_RELAY_AND_COORDINATION': 'Relay and resource coordination',
}

PROFILE_FOCUS = {
    'DIRECT_HANDOFF_BASELINE': [
        'establish the operational picture',
        'complete a traceable direct handoff',
        'close the evolution without an unsafe branch',
    ],
    'COMMUNICATION_RELAY_REQUIRED': [
        'recognize degraded communications',
        'establish an intermediate relay',
        'preserve information through the final handoff',
    ],
    'RESOURCE_COORDINATION_REQUIRED': [
        'recognize resource contention',
        'coordinate the constrained resource',
        'complete handoff after the resource step',
    ],
    'DUAL_CONSTRAINT_RELAY_AND_COORDINATION': [
        'manage simultaneous communications and resource constraints',
        'sequence relay before resource coordination',
        'preserve a closed-loop final handoff',
    ],
}


def selection_key(candidate: dict[str, Any]) -> tuple[str, str, str, int, str]:
    context = candidate.get('context_signature') or {}
    return (
        str(candidate.get('topic_id') or ''),
        str(context.get('location') or ''),
        str(candidate.get('context_signature_sha256') or ''),
        int(candidate.get('seed') or 0),
        str(candidate.get('candidate_id') or ''),
    )


def choose_candidates(candidates: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    remaining = sorted(candidates, key=selection_key)
    chosen: list[dict[str, Any]] = []
    used_topics: set[str] = set()
    used_locations: set[str] = set()
    used_contexts: set[str] = set()
    while remaining and len(chosen) < count:
        def rank(item: dict[str, Any]) -> tuple[int, int, int, tuple[str, str, str, int, str]]:
            context = item.get('context_signature') or {}
            topic = str(item.get('topic_id') or '')
            location = str(context.get('location') or '')
            context_hash = str(item.get('context_signature_sha256') or '')
            return (
                0 if topic not in used_topics else 1,
                0 if location not in used_locations else 1,
                0 if context_hash not in used_contexts else 1,
                selection_key(item),
            )
        selected = min(remaining, key=rank)
        remaining.remove(selected)
        chosen.append(selected)
        used_topics.add(str(selected.get('topic_id') or ''))
        context = selected.get('context_signature') or {}
        used_locations.add(str(context.get('location') or ''))
        used_contexts.add(str(selected.get('context_signature_sha256') or ''))
    if len(chosen) != count:
        raise ValueError(f'insufficient candidates for pack:{len(chosen)}:{count}')
    return chosen


def build_catalog(policy: dict[str, Any], archive: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if policy.get('policy_sha256') != policy_hash(policy):
        errors.append('operational pack policy self hash differs')
    if archive.get('classification') != 'PASS' or archive.get('status') != 'PASS':
        errors.append('behavioral archive is not passing')
    if not is_sha(archive.get('archive_root_sha256')):
        errors.append('behavioral archive root is invalid')
    else:
        archive_body = dict(archive)
        archive_body.pop('archive_root_sha256', None)
        if archive.get('archive_root_sha256') != sha256_value(archive_body):
            errors.append('behavioral archive root differs')
    candidates = archive.get('candidates')
    if not isinstance(candidates, list):
        errors.append('behavioral archive candidates missing')
        candidates = []
    required_profiles = policy.get('required_profiles') or []
    if required_profiles != list(COMPILED_REQUIRED_PROFILES):
        errors.append('required operational profile inventory differs')
    entries_per_profile = policy.get('entries_per_profile')
    if not isinstance(entries_per_profile, int) or entries_per_profile <= 0:
        errors.append('entries per profile invalid')
        entries_per_profile = 0
    if errors:
        raise ValueError('; '.join(errors))

    entries: list[dict[str, Any]] = []
    for profile in required_profiles:
        group = [item for item in candidates if item.get('operational_behavior_profile_id') == profile]
        for sequence, candidate in enumerate(choose_candidates(group, entries_per_profile), start=1):
            context = candidate['context_signature']
            entry_body = {
                'schema_version': '1.0.0',
                'candidate_id': candidate['candidate_id'],
                'source_scenario_id': candidate['source_scenario_id'],
                'topic_id': candidate['topic_id'],
                'seed': candidate['seed'],
                'operational_behavior_profile_id': profile,
                'profile_label': PROFILE_LABELS[profile],
                'title': f"{PROFILE_LABELS[profile]} — {str(context['location']).title()}",
                'plain_language_summary': (
                    f"A fictional healthcare-simulation exercise in {context['location']} with "
                    f"{context['communications']} communications and {context['resources']} resources."
                ),
                'context': {
                    'location': context['location'],
                    'weather': context['weather'],
                    'visibility': context['visibility'],
                    'communications': context['communications'],
                    'resources': context['resources'],
                    'resource_event': context['resource_event'],
                },
                'learning_focus': PROFILE_FOCUS[profile],
                'reproducibility': {
                    'package_sha256': candidate['package_sha256'],
                    'context_signature_sha256': candidate['context_signature_sha256'],
                    'policy_signature_sha256': candidate['policy_signature_sha256'],
                    'equivalence_class_id': candidate['equivalence_class_id'],
                },
                'authority': {
                    'healthcare_simulation': 'PERMITTED_WITHIN_VALIDATED_SCOPE',
                    'direct_patient_care': 'PROHIBITED',
                    'clinical_decision_support': 'PROHIBITED',
                    'operational_timing': 'NOT_CALIBRATED',
                    'scoring_state': 'SOURCE_CONFORMANCE_ONLY',
                    'treatment_state': 'NO_SIMULATION_ADMITTED_CONCRETE_TREATMENT',
                },
                'profile_sequence': sequence,
            }
            entry_id = f"ASK-OP-{sha256_value(entry_body)[:16].upper()}"
            entries.append({'catalog_entry_id': entry_id, **entry_body})

    entries.sort(key=lambda item: (required_profiles.index(item['operational_behavior_profile_id']), item['profile_sequence'], item['catalog_entry_id']))
    profile_counts = {profile: sum(1 for item in entries if item['operational_behavior_profile_id'] == profile) for profile in required_profiles}
    if len(entries) != policy.get('required_total_entries'):
        raise ValueError('operational scenario pack size differs')
    if any(count != entries_per_profile for count in profile_counts.values()):
        raise ValueError('operational scenario profile count differs')
    if len({item['candidate_id'] for item in entries}) != len(entries):
        raise ValueError('operational scenario pack contains duplicate candidates')

    without_hash = {
        'schema_version': '1.0.0',
        'classification': 'PASS',
        'status': 'PASS',
        'catalog_id': policy['catalog_id'],
        'catalog_profile': policy['catalog_profile'],
        'selection_profile': policy['selection_profile'],
        'policy_id': policy['policy_id'],
        'policy_epoch': policy['policy_epoch'],
        'policy_sha256': policy['policy_sha256'],
        'source_archive_path': policy['source_archive_path'],
        'source_archive_root_sha256': archive['archive_root_sha256'],
        'entry_count': len(entries),
        'profile_counts': profile_counts,
        'entries': entries,
        'stakeholder_surfaces': policy['stakeholder_surfaces'],
        'truth_boundaries': policy['admission_boundaries'],
    }
    return {**without_hash, 'catalog_root_sha256': sha256_value(without_hash)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--json-output', default='reports/operational-scenario-pack-generation.json')
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    policy = load_object(safe_repo_path(repo, POLICY_REL.as_posix(), 'policy'))
    archive = load_object(safe_repo_path(repo, policy.get('source_archive_path'), 'source_archive_path'))
    catalog = build_catalog(policy, archive)
    output_path = safe_repo_path(repo, policy.get('output_path'), 'output_path')
    mismatches: list[str] = []
    if args.check:
        if not output_path.is_file() or load_object(output_path) != catalog:
            mismatches.append(str(policy.get('output_path')))
    else:
        atomic_write(output_path, catalog)
    result = {
        'schema_version': '1.0.0',
        'classification': 'PASS' if not mismatches else 'FAIL',
        'status': 'PASS' if not mismatches else 'FAIL',
        'mode': 'check' if args.check else 'write',
        'catalog_id': catalog['catalog_id'],
        'entries': catalog['entry_count'],
        'profile_counts': catalog['profile_counts'],
        'catalog_root_sha256': catalog['catalog_root_sha256'],
        'mismatches': mismatches,
        'errors': [],
    }
    atomic_write(safe_repo_path(repo, args.json_output, 'json_output'), result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not mismatches else 3


if __name__ == '__main__':
    raise SystemExit(main())
