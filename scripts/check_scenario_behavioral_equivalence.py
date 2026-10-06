#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

POLICY_REL = Path('config/scenario-science/BEHAVIORAL_DIVERSITY_POLICY.json')
ARCHIVE_REL = Path('reports/scenario-behavioral-equivalence.json')
COMPILED_POLICY_ID = 'asklepios-behavioral-diversity-policy-v1'
COMPILED_POLICY_SHA256 = '80b5482457a975f8a97d150e5eb703cad349243646230ae25b2a35d4cc40b0cd'
COMPILED_PROFILES = [
    'DIRECT_HANDOFF_BASELINE',
    'COMMUNICATION_RELAY_REQUIRED',
    'RESOURCE_COORDINATION_REQUIRED',
    'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
]
COMPILED_AUTHORITY = {
    'clinical_authority': 'NOT_GRANTED',
    'patient_care_use': 'PROHIBITED',
    'human_team_behavior': 'STRUCTURAL_ONLY_NOT_CALIBRATED',
    'operational_timing': 'NOT_CALIBRATED',
    'empirical_behavioral_validity': 'NOT_ESTABLISHED',
    'scoring_behavior': 'inherited_unchanged',
}
HEX64 = re.compile(r'^[0-9a-f]{64}$')

class CheckError(ValueError):
    pass

def canonical(value: Any, path: str = '$') -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        raise CheckError(f'floating-point value forbidden:{path}')
    if isinstance(value, list):
        return [canonical(item, f'{path}[{index}]') for index, item in enumerate(value)]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str) or not key:
                raise CheckError(f'invalid object key:{path}')
            result[key] = canonical(value[key], f'{path}.{key}')
        return result
    raise CheckError(f'unsupported canonical value:{path}:{type(value).__name__}')

def canonical_json(value: Any) -> str:
    return json.dumps(canonical(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def sha(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()

def without(value: dict[str, Any], key: str) -> dict[str, Any]:
    body = dict(value)
    body.pop(key, None)
    return body

def require(condition: Any, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)

def load(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        errors.append(f'{label} unreadable:{exc}')
        return {}
    if not isinstance(value, dict):
        errors.append(f'{label} is not an object')
        return {}
    return value

def safe_output(repo: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or '..' in candidate.parts or '\\' in value or ':' in candidate.parts:
        raise CheckError('unsafe output path')
    path = (repo / candidate).resolve()
    if repo.resolve() not in path.parents:
        raise CheckError('output path escapes repository')
    for parent in [path.parent, *path.parent.parents]:
        if parent == repo.parent:
            break
        if parent.exists() and parent.is_symlink():
            raise CheckError('symlinked output parent rejected')
        if parent == repo:
            break
    return path

def write_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    temp.replace(path)

def check(repo: Path) -> dict[str, Any]:
    errors: list[str] = []
    policy = load(repo / POLICY_REL, 'behavioral-diversity policy', errors)
    archive = load(repo / ARCHIVE_REL, 'behavioral-equivalence archive', errors)
    if errors:
        return {'schema_version':'1.0.0','classification':'FAIL','status':'FAIL','checks':0,'errors':errors}

    checks = 0
    def c(condition: Any, message: str) -> None:
        nonlocal checks
        checks += 1
        require(condition, message, errors)

    c(policy.get('schema_version') == '1.0.0', 'policy schema differs')
    c(policy.get('policy_id') == COMPILED_POLICY_ID, 'policy ID differs')
    c(policy.get('policy_epoch') == 1, 'policy epoch differs')
    c(policy.get('policy_sha256') == sha(without(policy, 'policy_sha256')), 'policy self-hash differs')
    c(policy.get('policy_sha256') == COMPILED_POLICY_SHA256, 'policy compiled anchor differs')
    c(policy.get('required_operational_profiles') == COMPILED_PROFILES, 'required operational profiles differ')
    c(policy.get('authority_boundaries') == COMPILED_AUTHORITY, 'policy authority boundaries differ')
    novelty = policy.get('novelty_rules') if isinstance(policy.get('novelty_rules'), dict) else {}
    c(novelty.get('narrative_only_change_creates_policy_novelty') is False, 'narrative-only novelty was enabled')
    c(novelty.get('provenance_only_change_creates_policy_novelty') is False, 'provenance-only novelty was enabled')
    c(novelty.get('seed_only_change_creates_policy_novelty') is False, 'seed-only novelty was enabled')
    c(novelty.get('context_only_change_creates_policy_novelty') is False, 'context-only novelty was enabled')
    c(novelty.get('profile_relabeling_without_policy_change_permitted') is False, 'profile relabeling was permitted')

    c(archive.get('schema_version') == '1.0.0', 'archive schema differs')
    c(archive.get('classification') == 'PASS' and archive.get('status') == 'PASS', 'archive is not passing')
    c(archive.get('archive_profile') == policy.get('archive_profile'), 'archive profile differs')
    c(archive.get('policy_profile') == policy.get('policy_signature_profile'), 'policy signature profile differs')
    c(archive.get('truth_boundaries') == COMPILED_AUTHORITY, 'archive authority boundaries differ')
    c(archive.get('archive_root_sha256') == sha(without(archive, 'archive_root_sha256')), 'archive root differs')

    candidates = archive.get('candidates') if isinstance(archive.get('candidates'), list) else []
    classes = archive.get('equivalence_classes') if isinstance(archive.get('equivalence_classes'), list) else []
    summary = archive.get('summary') if isinstance(archive.get('summary'), dict) else {}
    c(bool(candidates), 'archive candidates missing')
    c(bool(classes), 'archive equivalence classes missing')

    candidate_by_id: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, candidate in enumerate(candidates):
        label = f'candidate:{index}'
        c(isinstance(candidate, dict), f'{label} malformed')
        if not isinstance(candidate, dict):
            continue
        candidate_id = candidate.get('candidate_id')
        package_sha = candidate.get('package_sha256')
        policy_sha = candidate.get('policy_signature_sha256')
        context_sha = candidate.get('context_signature_sha256')
        class_id = candidate.get('equivalence_class_id')
        profile_id = candidate.get('operational_behavior_profile_id')
        c(isinstance(candidate_id, str) and candidate_id == f'ASK-BEQ-CAND-{str(package_sha)[:16].upper()}', f'{label} identity differs')
        c(isinstance(package_sha, str) and bool(HEX64.fullmatch(package_sha)), f'{label} package hash malformed')
        c(isinstance(policy_sha, str) and bool(HEX64.fullmatch(policy_sha)), f'{label} policy hash malformed')
        c(isinstance(context_sha, str) and bool(HEX64.fullmatch(context_sha)), f'{label} context hash malformed')
        c(candidate.get('context_signature_sha256') == sha(candidate.get('context_signature')), f'{label} context signature differs')
        c(candidate.get('policy_signature_sha256') == sha(candidate.get('policy_descriptor')), f'{label} policy signature differs')
        c(class_id == f'ASK-BEQ-CLASS-{str(policy_sha)[:16].upper()}', f'{label} class identity differs')
        c(profile_id in COMPILED_PROFILES, f'{label} operational profile differs')
        if isinstance(candidate_id, str):
            c(candidate_id not in candidate_by_id, f'candidate duplicated:{candidate_id}')
            candidate_by_id[candidate_id] = candidate
        if isinstance(class_id, str):
            grouped.setdefault(class_id, []).append(candidate)

    observed_class_ids: set[str] = set()
    class_profiles: list[str] = []
    context_counts: list[int] = []
    for index, item in enumerate(classes):
        label = f'class:{index}'
        c(isinstance(item, dict), f'{label} malformed')
        if not isinstance(item, dict):
            continue
        class_id = item.get('equivalence_class_id')
        policy_sha = item.get('policy_signature_sha256')
        profile_id = item.get('operational_behavior_profile_id')
        member_ids = item.get('candidate_ids') if isinstance(item.get('candidate_ids'), list) else []
        members = grouped.get(str(class_id), [])
        expected_ids = sorted(str(candidate.get('candidate_id')) for candidate in members)
        c(isinstance(class_id, str) and class_id not in observed_class_ids, f'{label} duplicated')
        if isinstance(class_id, str): observed_class_ids.add(class_id)
        c(class_id == f'ASK-BEQ-CLASS-{str(policy_sha)[:16].upper()}', f'{label} identity differs')
        c(member_ids == expected_ids, f'{label} candidate inventory differs')
        c(item.get('representative_candidate_id') == (expected_ids[0] if expected_ids else None), f'{label} representative differs')
        c(bool(members) and all(candidate.get('policy_signature_sha256') == policy_sha for candidate in members), f'{label} policy membership differs')
        c(bool(members) and all(candidate.get('operational_behavior_profile_id') == profile_id for candidate in members), f'{label} collapses reviewed operational profiles')
        expected_contexts = len({str(candidate.get('context_signature_sha256')) for candidate in members})
        c(item.get('context_signature_count') == expected_contexts, f'{label} context count differs')
        if isinstance(profile_id, str): class_profiles.append(profile_id)
        context_counts.append(expected_contexts)

    c(observed_class_ids == set(grouped), 'class inventory differs from candidates')
    c(sorted(class_profiles) == sorted(COMPILED_PROFILES), 'profile-to-class inventory differs')
    c(len(set(class_profiles)) == len(class_profiles), 'one profile occupies multiple policy classes')

    candidate_count = len(candidates)
    context_count = len({str(candidate.get('context_signature_sha256')) for candidate in candidates if isinstance(candidate, dict)})
    policy_count = len({str(candidate.get('policy_signature_sha256')) for candidate in candidates if isinstance(candidate, dict)})
    expected_summary = {
        'candidate_count': candidate_count,
        'unique_context_signatures': context_count,
        'unique_policy_signatures': policy_count,
        'operational_behavior_profiles_observed': sorted(class_profiles),
        'policy_equivalence_classes': len(classes),
        'context_only_variant_count': candidate_count - len(classes),
        'policy_novelty_ratio_bps': (len(classes) * 10_000) // candidate_count if candidate_count else 0,
        'maximum_contexts_in_one_policy_class': max(context_counts) if context_counts else 0,
        'minimum_contexts_in_one_policy_class': min(context_counts) if context_counts else 0,
        'behavioral_uniqueness_status': 'EVERY_CANDIDATE_POLICY_DISTINCT' if len(classes) == candidate_count else ('CONTEXT_DIVERSITY_ONLY_POLICY_DIVERSITY_NOT_ESTABLISHED' if len(classes) == 1 and candidate_count > 1 else 'MIXED_CONTEXT_AND_POLICY_DIVERSITY'),
        'narrative_or_provenance_only_changes_create_policy_novelty': False,
        'operational_context_change_without_policy_change_counts_as_policy_novelty': False,
    }
    c(summary == expected_summary, 'archive summary differs')

    floors = policy.get('ratchet_floors') if isinstance(policy.get('ratchet_floors'), dict) else {}
    c(candidate_count >= floors.get('minimum_candidates', 10**9), 'candidate ratchet regressed')
    c(context_count >= floors.get('minimum_unique_context_signatures', 10**9), 'context ratchet regressed')
    c(len(classes) >= floors.get('minimum_policy_equivalence_classes', 10**9), 'policy-class ratchet regressed')
    c(expected_summary['policy_novelty_ratio_bps'] >= floors.get('minimum_policy_novelty_ratio_bps', 10**9), 'policy-novelty ratio ratchet regressed')
    c(expected_summary['minimum_contexts_in_one_policy_class'] >= floors.get('minimum_contexts_per_policy_class', 10**9), 'policy-class context floor regressed')

    return {
        'schema_version':'1.0.0',
        'classification':'PASS' if not errors else 'FAIL',
        'status':'PASS' if not errors else 'FAIL',
        'checks':checks,
        'policy_id':policy.get('policy_id'),
        'policy_sha256':policy.get('policy_sha256'),
        'archive_root_sha256':archive.get('archive_root_sha256'),
        'candidate_count':candidate_count,
        'unique_context_signatures':context_count,
        'policy_equivalence_classes':len(classes),
        'operational_behavior_profiles':sorted(class_profiles),
        'errors':errors,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--json-output', default='reports/scenario-behavioral-equivalence-python.json')
    args = parser.parse_args()
    repo = args.repo.resolve()
    try:
        result = check(repo)
        output = safe_output(repo, args.json_output)
        write_atomic(output, result)
    except Exception as exc:
        result = {'schema_version':'1.0.0','classification':'INTERNAL_ERROR','status':'INTERNAL_ERROR','checks':0,'errors':[str(exc)]}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('classification') == 'PASS' else 3

if __name__ == '__main__':
    sys.exit(main())
