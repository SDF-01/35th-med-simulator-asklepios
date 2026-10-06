#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from portable_test_workspace import WORKSPACE_PROFILE, compact_case_name, temporary_workspace

POLICY = Path('config/scenario-science/OPERATIONAL_SCENARIO_PACK_POLICY.json')
CATALOG = Path('public/data/scenario_library/operational-pack.json')
ARCHIVE = Path('reports/scenario-behavioral-equivalence.json')


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def sha(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')


def rehash_policy(value: dict[str, Any]) -> None:
    body = dict(value)
    body.pop('policy_sha256', None)
    value['policy_sha256'] = sha(body)


def rehash_catalog(value: dict[str, Any]) -> None:
    body = dict(value)
    body.pop('catalog_root_sha256', None)
    value['catalog_root_sha256'] = sha(body)


def run_checkers(repo: Path) -> tuple[bool, list[str]]:
    commands = [
        [sys.executable, 'scripts/build_operational_scenario_pack.py', '--repo', '.', '--check', '--json-output', 'reports/operational-scenario-pack-generation.json'],
        ['node', 'scripts/check_operational_scenario_pack.mjs', '--repo', '.', '--json-output', 'reports/operational-scenario-pack-node.json'],
    ]
    errors: list[str] = []
    ok = True
    for command in commands:
        completed = subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False, timeout=90)
        ok = ok and completed.returncode == 0
        text = (completed.stdout or '') + '\n' + (completed.stderr or '')
        try:
            start = text.find('{')
            payload = json.loads(text[start:]) if start >= 0 else {}
            errors.extend(payload.get('errors') or [])
            errors.extend(payload.get('mismatches') or [])
        except Exception:
            errors.append(text[-1200:])
    return ok, sorted(set(str(item) for item in errors if item))


def mutate_catalog(repo: Path, fn: Callable[[dict[str, Any]], None], *, rehash: bool = True) -> None:
    path = repo / CATALOG
    value = json.loads(path.read_text())
    fn(value)
    if rehash:
        rehash_catalog(value)
    write_json(path, value)


def mutate_policy(repo: Path, fn: Callable[[dict[str, Any]], None]) -> None:
    path = repo / POLICY
    value = json.loads(path.read_text())
    fn(value)
    rehash_policy(value)
    write_json(path, value)


def mutate_archive(repo: Path, fn: Callable[[dict[str, Any]], None]) -> None:
    path = repo / ARCHIVE
    value = json.loads(path.read_text())
    fn(value)
    write_json(path, value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--json-output', default='reports/operational-scenario-pack-mutations.json')
    args = parser.parse_args()
    source = Path(args.repo).resolve()
    cases: list[tuple[str, Callable[[Path], None] | None, bool, str | None]] = [
        ('baseline', None, True, None),
        ('entry-removed-rejected', lambda r: mutate_catalog(r, lambda c: c['entries'].pop()), False, 'operational scenario catalog differs'),
        ('duplicate-candidate-rejected', lambda r: mutate_catalog(r, lambda c: c['entries'][1].__setitem__('candidate_id', c['entries'][0]['candidate_id'])), False, 'operational scenario catalog differs'),
        ('profile-relabel-rejected', lambda r: mutate_catalog(r, lambda c: c['entries'][0].__setitem__('operational_behavior_profile_id', 'RESOURCE_COORDINATION_REQUIRED')), False, 'operational scenario catalog differs'),
        ('direct-care-escalation-rejected', lambda r: mutate_catalog(r, lambda c: c['entries'][0]['authority'].__setitem__('direct_patient_care', 'PERMITTED')), False, 'operational scenario catalog differs'),
        ('timing-promotion-rejected', lambda r: mutate_catalog(r, lambda c: c['entries'][0]['authority'].__setitem__('operational_timing', 'CALIBRATED')), False, 'operational scenario catalog differs'),
        ('scoring-promotion-rejected', lambda r: mutate_catalog(r, lambda c: c['entries'][0]['authority'].__setitem__('scoring_state', 'MULTISITE_VALIDATED')), False, 'operational scenario catalog differs'),
        ('treatment-promotion-rejected', lambda r: mutate_catalog(r, lambda c: c['entries'][0]['authority'].__setitem__('treatment_state', 'SIMULATION_ADMITTED')), False, 'operational scenario catalog differs'),
        ('source-archive-drift-rejected', lambda r: mutate_archive(r, lambda a: a['candidates'][0].__setitem__('seed', int(a['candidates'][0]['seed']) + 1)), False, 'behavioral archive root differs'),
        ('policy-profile-floor-rejected', lambda r: mutate_policy(r, lambda p: p['required_profiles'].pop()), False, 'required operational profile inventory differs'),
        ('policy-output-traversal-rejected', lambda r: mutate_policy(r, lambda p: p.__setitem__('output_path', '../escape.json')), False, 'unsafe repository path:output_path'),
        ('catalog-root-forgery-rejected', lambda r: mutate_catalog(r, lambda c: c.__setitem__('catalog_root_sha256', '0' * 64), rehash=False), False, 'operational scenario catalog differs'),
    ]
    results = []
    errors = []
    with temporary_workspace('ask-op-') as workspace:
        template = workspace / 'template'
        fixture_paths = [
            POLICY, CATALOG, ARCHIVE,
            Path('scripts/build_operational_scenario_pack.py'),
            Path('scripts/check_operational_scenario_pack.mjs'),
        ]
        for relative in fixture_paths:
            destination = template / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, destination)
        for case_id, mutation, expected_pass, required_error in cases:
            case_root = workspace / compact_case_name(case_id)
            shutil.copytree(template, case_root)
            if mutation:
                mutation(case_root)
            observed_pass, observed_errors = run_checkers(case_root)
            case_ok = observed_pass == expected_pass and (required_error is None or any(required_error in item for item in observed_errors))
            classification = 'PASS' if expected_pass and observed_pass else 'EXPECTED_REJECTION' if not expected_pass and not observed_pass else 'FAIL'
            results.append({
                'case_id': case_id,
                'classification': classification,
                'expected_pass': expected_pass,
                'observed_pass': observed_pass,
                'checker_errors': observed_errors,
                'required_error': required_error,
                'pass': case_ok,
            })
            if not case_ok:
                errors.append(f'case failed:{case_id}')
    report = {
        'schema_version': '1.0.0',
        'classification': 'PASS' if not errors else 'FAIL',
        'cases': len(results),
        'attacks': len(results) - 1,
        'accepted_attacks': sum(1 for item in results[1:] if item['observed_pass']),
        'results': results,
        'workspace_profile': WORKSPACE_PROFILE,
        'errors': errors,
    }
    write_json(source / args.json_output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 3


if __name__ == '__main__':
    raise SystemExit(main())
