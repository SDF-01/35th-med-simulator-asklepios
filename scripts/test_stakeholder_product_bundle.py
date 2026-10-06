#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from portable_test_workspace import WORKSPACE_PROFILE, compact_case_name, temporary_workspace

DASHBOARD = Path('public/data/scenario_library/stakeholder-dashboard.json')
CAPABILITY_MAP = Path('config/product/STAKEHOLDER_CAPABILITY_MAP.json')
TREATMENT = Path('config/scenario-science/TREATMENT_ADMISSION_REGISTRY.json')
PLAIN_CONTRACT = Path('config/product/PLAIN_LANGUAGE_RELEASE_CONTRACT.json')
PLAIN_SUMMARY = Path('docs/RC3_8_STAKEHOLDER_RELEASE_SUMMARY.md')
OPERATIONAL_PACK = Path('public/data/scenario_library/operational-pack.json')
APP = Path('src/App.tsx')
PAGE = Path('src/pages/ScenarioLibraryPage.tsx')


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')


def rehash(path: Path, field: str) -> None:
    value = json.loads(path.read_text(encoding='utf-8'))
    body = dict(value); body.pop(field, None)
    value[field] = sha(body)
    write_json(path, value)


def run_checkers(repo: Path) -> tuple[bool, list[str]]:
    commands = [
        ['node', 'scripts/check_stakeholder_product_bundle.mjs', '--repo', '.', '--json-output', 'reports/stakeholder-product-bundle-node.json'],
        [sys.executable, 'scripts/check_stakeholder_product_bundle.py', '--repo', '.', '--json-output', 'reports/stakeholder-product-bundle-python.json'],
    ]
    observed_ok = True
    observed_errors: list[str] = []
    for command in commands:
        environment = dict(os.environ)
        completed = subprocess.run(command, cwd=repo, env=environment, text=True, capture_output=True, check=False, timeout=120)
        observed_ok = observed_ok and completed.returncode == 0
        stdout = completed.stdout or ''
        start = stdout.find('{')
        parsed = False
        if start >= 0:
            try:
                payload = json.loads(stdout[start:stdout.rfind('}') + 1])
                observed_errors.extend(str(item) for item in (payload.get('errors') or []))
                observed_errors.extend(str(item) for item in (payload.get('mismatches') or []))
                parsed = True
            except Exception:
                parsed = False
        if completed.returncode != 0 and not parsed:
            text = stdout + '\n' + (completed.stderr or '')
            observed_errors.append(text[-1600:])
    return observed_ok, sorted(set(item for item in observed_errors if item))


def mutate_json(repo: Path, rel: Path, fn: Callable[[dict[str, Any]], None], hash_field: str | None = None) -> None:
    path = repo / rel
    value = json.loads(path.read_text(encoding='utf-8'))
    fn(value)
    write_json(path, value)
    if hash_field:
        rehash(path, hash_field)


def mutate_text(repo: Path, rel: Path, fn: Callable[[str], str]) -> None:
    path = repo / rel
    path.write_text(fn(path.read_text(encoding='utf-8')), encoding='utf-8', newline='\n')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--json-output', default='reports/stakeholder-product-bundle-mutations.json')
    args = parser.parse_args()
    source = Path(args.repo).resolve()

    cases: list[tuple[str, Callable[[Path], None] | None, bool, str | None]] = [
        ('baseline', None, True, None),
        ('scenario-entry-removed', lambda r: mutate_json(r, DASHBOARD, lambda d: d['scenario_pack']['entries'].pop(), 'dashboard_root_sha256'), False, 'stakeholder dashboard differs'),
        ('orphan-capability-stakeholders-removed', lambda r: mutate_json(r, CAPABILITY_MAP, lambda d: d['capabilities'][0].__setitem__('stakeholders', []), 'map_sha256'), False, 'capability list missing'),
        ('capability-owner-missing', lambda r: mutate_json(r, CAPABILITY_MAP, lambda d: d['capabilities'][0].__setitem__('owner_module', 'src/missing.ts'), 'map_sha256'), False, 'capability source missing'),
        ('scenario-route-removed', lambda r: mutate_text(r, APP, lambda s: s.replace('<Route path="/scenarios" element={<ScenarioLibraryPage />} />', '')), False, 'scenario library route missing'),
        ('scenario-route-duplicated', lambda r: mutate_text(r, APP, lambda s: s.replace('<Route path="/scenarios" element={<ScenarioLibraryPage />} />', '<Route path="/scenarios" element={<ScenarioLibraryPage />} />\n        <Route path="/scenarios" element={<ScenarioLibraryPage />} />')), False, 'scenario library route duplicated:/scenarios:2'),
        ('scenario-ui-scorecard-marker-removed', lambda r: mutate_text(r, PAGE, lambda s: s.replace('Source-conformance scorecard', 'Performance panel')), False, 'scenario library UI marker missing:Source-conformance scorecard'),
        ('scorecard-validity-promoted', lambda r: mutate_json(r, DASHBOARD, lambda d: d['reference_scorecards'][0].__setitem__('validity_boundary', 'VALIDATED_PROFICIENCY_MEASURE'), 'dashboard_root_sha256'), False, 'stakeholder dashboard differs'),
        ('timing-affects-score', lambda r: mutate_json(r, DASHBOARD, lambda d: d['reference_scorecards'][0].__setitem__('timing_score_effect', 'ENABLED'), 'dashboard_root_sha256'), False, 'stakeholder dashboard differs'),
        ('treatment-admitted-without-prerequisites', lambda r: mutate_json(r, TREATMENT, lambda d: d['entries'][0].update({'current_state': 'SIMULATION_ADMITTED', 'simulation_admitted': True}), 'registry_sha256'), False, 'treatment admission prerequisites incomplete'),
        ('treatment-state-order-weakened', lambda r: mutate_json(r, TREATMENT, lambda d: d['state_order'].pop(), 'registry_sha256'), False, 'treatment admission state order differs'),
        ('plain-language-heading-removed', lambda r: mutate_text(r, PLAIN_SUMMARY, lambda s: s.replace('## What changed?', '## Technical changes')), False, 'plain-language heading missing:What changed?'),
        ('plain-language-forbidden-claim', lambda r: mutate_text(r, PLAIN_SUMMARY, lambda s: s + '\nThis system is fully calibrated.\n'), False, 'plain-language forbidden claim present:fully calibrated'),
        ('plain-language-contract-weakened', lambda r: mutate_json(r, PLAIN_CONTRACT, lambda d: d['required_headings'].pop(), 'contract_sha256'), False, 'plain-language required heading inventory differs'),
        ('operational-pack-root-forged', lambda r: mutate_json(r, OPERATIONAL_PACK, lambda d: d.__setitem__('catalog_root_sha256', '0' * 64)), False, 'operational scenario catalog root differs'),
        ('dashboard-root-forged', lambda r: mutate_json(r, DASHBOARD, lambda d: d.__setitem__('dashboard_root_sha256', '0' * 64)), False, 'stakeholder dashboard differs'),
    ]

    results: list[dict[str, Any]] = []
    errors: list[str] = []
    with temporary_workspace('ask-sp-') as workspace:
        template = workspace / 'template'
        shutil.copytree(source, template, ignore=shutil.ignore_patterns('.git', 'node_modules', '.asklepios', 'dist', '__pycache__', '*.pyc'))
        for case_id, mutation, expected_pass, required_error in cases:
            case_root = workspace / compact_case_name(case_id)
            shutil.copytree(template, case_root)
            if mutation:
                mutation(case_root)
            observed_pass, checker_errors = run_checkers(case_root)
            case_ok = observed_pass == expected_pass and (required_error is None or any(required_error in item for item in checker_errors))
            classification = 'PASS' if expected_pass and observed_pass else 'EXPECTED_REJECTION' if not expected_pass and not observed_pass else 'FAIL'
            results.append({
                'case_id': case_id,
                'classification': classification,
                'expected_pass': expected_pass,
                'observed_pass': observed_pass,
                'required_error': required_error,
                'checker_errors': checker_errors,
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
    output = source / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 3


if __name__ == '__main__':
    raise SystemExit(main())
