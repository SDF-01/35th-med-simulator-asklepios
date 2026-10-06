#!/usr/bin/env python3
"""Adversarial differential tests for the deterministic Scenario Genome."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

from release_result import EXPECTED_REJECTION, PASS, case_result, exit_code, suite_classification
from scenario_genome_common import atomic_write_json, load_object, safe_repo_path

sys.dont_write_bytecode = True
Mutator = Callable[[Path], None]


FIXTURE_FILES = (
    "config/scenario-genome/SCENARIO_GENOME_POLICY.json",
    "public/data/content_registry/content_registry.json",
    "public/data/scenario_core/verified_scenario_package.json",
    "public/data/scenario_core/verified_scenario_genome.json",
    "scripts/build_scenario_genome.py",
    "scripts/check_scenario_genome.mjs",
    "scripts/scenario_genome_common.py",
    "scripts/node_checker_cli.mjs",
)


def copy_repo(source: Path, target: Path) -> None:
    """Copy only the closed Scenario Genome source boundary.

    The old suite copied the entire repository for every mutation, making a
    small 18-case assurance test take many minutes and increasing the chance of
    ambient-file coupling.  A closed fixture is faster and proves the checkers
    depend only on their declared inputs.
    """
    target.mkdir(parents=True, exist_ok=True)
    for relative in FIXTURE_FILES:
        src = source / relative
        if not src.is_file() or src.is_symlink():
            raise RuntimeError(f"Scenario Genome fixture source unavailable:{relative}")
        dst = target / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def run(repo: Path) -> tuple[int, int, list[str]]:
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    py = subprocess.run(
        [sys.executable, 'scripts/build_scenario_genome.py', '--repo', '.', '--check', '--json-output', 'reports/scenario-genome-python-check.json'],
        cwd=repo, env=env, text=True, capture_output=True, timeout=60,
    )
    node = subprocess.run(
        ['node', 'scripts/check_scenario_genome.mjs', '--repo', '.', '--report', 'reports/scenario-genome-node.json'],
        cwd=repo, env=env, text=True, capture_output=True, timeout=60,
    )
    tails = []
    for label, completed in [('python', py), ('node', node)]:
        text = (completed.stdout + '\n' + completed.stderr).strip().splitlines()
        tails.extend(f'{label}:{line}' for line in text[-20:])
    return py.returncode, node.returncode, tails


def _write_fixture_json(path: Path, value: dict) -> None:
    """Write a mutated fixture without imposing the Genome's no-float output schema.

    The verified scenario package predates the Scenario Genome and legitimately
    contains source observations such as decimal temperatures.  Adversarial
    fixture mutation must preserve that source schema rather than accidentally
    failing inside the test harness before either independent checker runs.
    """
    if path.is_symlink():
        raise RuntimeError(f"fixture destination is symlinked:{path}")
    rendered = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".fixture.tmp")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    temporary.write_text(rendered, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def mutate_json(repo: Path, relative: str, fn: Callable[[dict], None]) -> None:
    path = safe_repo_path(repo, relative)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"fixture JSON unavailable:{path}")
    value = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
    )
    if not isinstance(value, dict):
        raise RuntimeError(f"fixture JSON root is not an object:{path}")
    fn(value)
    _write_fixture_json(path, value)


def cases() -> list[tuple[str, Mutator | None]]:
    return [
        ('baseline', None),
        ('clinical_authority_escalation_rejected', lambda r: mutate_json(r, 'public/data/scenario_core/verified_scenario_package.json', lambda d: d['authority'].__setitem__('clinical_authority', 'GRANTED'))),
        ('scoring_behavior_change_rejected', lambda r: mutate_json(r, 'public/data/scenario_core/verified_scenario_package.json', lambda d: d['authority'].__setitem__('scoring_behavior', 'modified'))),
        ('forbidden_probability_field_rejected', lambda r: mutate_json(r, 'public/data/scenario_core/verified_scenario_package.json', lambda d: d['scenario'].__setitem__('real_world_frequency', 1))),
        ('failed_certificate_rejected', lambda r: mutate_json(r, 'public/data/scenario_core/verified_scenario_package.json', lambda d: next(iter(d['certificate']['checks'])).__class__ and d['certificate']['checks'].__setitem__(next(iter(d['certificate']['checks'])), False))),
        ('malformed_evidence_hash_rejected', lambda r: mutate_json(r, 'public/data/scenario_core/verified_scenario_package.json', lambda d: d['evidence'][0].__setitem__('chunk_sha256', 'bad'))),
        ('duplicate_route_node_rejected', lambda r: mutate_json(r, 'public/data/scenario_core/verified_scenario_package.json', lambda d: d['route']['nodes'].append(dict(d['route']['nodes'][0])))),
        ('unknown_route_endpoint_rejected', lambda r: mutate_json(r, 'public/data/scenario_core/verified_scenario_package.json', lambda d: d['route']['edges'][0].__setitem__('to', 'missing-node'))),
        ('unreachable_route_node_rejected', lambda r: mutate_json(r, 'public/data/scenario_core/verified_scenario_package.json', lambda d: d['route']['nodes'].append({'node_id':'unreachable','node_kind':'observation','terminal':True}))),
        ('nonterminal_route_dead_end_rejected', lambda r: mutate_json(r, 'public/data/scenario_core/verified_scenario_package.json', lambda d: (d['route']['nodes'].append({'node_id':'dead-end','node_kind':'observation','terminal':False}), d['route']['edges'].append({'edge_id':'to-dead-end','from':d['route']['start_node_id'],'to':'dead-end'})))),
        ('cyclic_route_rejected', lambda r: mutate_json(r, 'public/data/scenario_core/verified_scenario_package.json', lambda d: d['route']['edges'].append({'edge_id':'cycle-edge','from':d['route']['nodes'][-1]['node_id'],'to':d['route']['start_node_id']}))),
        ('windows_style_path_escape_rejected', lambda r: mutate_json(r, 'config/scenario-genome/SCENARIO_GENOME_POLICY.json', lambda d: d['source_paths'].__setitem__('scenario_package', '..\\outside.json'))),
        ('posix_path_escape_rejected', lambda r: mutate_json(r, 'config/scenario-genome/SCENARIO_GENOME_POLICY.json', lambda d: d.__setitem__('output_path', '../outside.json'))),
        ('absolute_path_rejected', lambda r: mutate_json(r, 'config/scenario-genome/SCENARIO_GENOME_POLICY.json', lambda d: d.__setitem__('report_path', '/tmp/out.json'))),
        ('genome_self_hash_tamper_rejected', lambda r: mutate_json(r, 'public/data/scenario_core/verified_scenario_genome.json', lambda d: d.__setitem__('genome_sha256', '0' * 64))),
        ('genome_identity_tamper_rejected', lambda r: mutate_json(r, 'public/data/scenario_core/verified_scenario_genome.json', lambda d: d.__setitem__('genome_id', 'ASK-GENOME-FORGED'))),
        ('missing_genome_rejected', lambda r: safe_repo_path(r, 'public/data/scenario_core/verified_scenario_genome.json').unlink()),
        ('symlinked_genome_rejected', lambda r: (safe_repo_path(r, 'public/data/scenario_core/verified_scenario_genome.json').unlink(), safe_repo_path(r, 'public/data/scenario_core/verified_scenario_genome.json').symlink_to('/etc/hosts'))),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--json-output', type=Path, default=Path('reports/scenario-genome-mutations.json'))
    args = parser.parse_args()
    source = args.repo.resolve()
    results = []
    errors = []
    with tempfile.TemporaryDirectory(prefix='asklepios-scenario-genome-suite-') as temp:
        template = Path(temp) / 'template'
        copy_repo(source, template)
        # Rebuild once so the baseline binds to the exact current writer and checker bytes.
        generated = subprocess.run([sys.executable, 'scripts/build_scenario_genome.py', '--repo', '.'], cwd=template, text=True, capture_output=True, timeout=60)
        if generated.returncode != 0:
            errors.append('template scenario genome generation failed')
        for case_id, mutator in cases():
            repo = Path(temp) / case_id
            copy_repo(template, repo)
            try:
                if mutator is not None:
                    mutator(repo)
                py_status, node_status, tails = run(repo)
                expected = mutator is None
                observed = py_status == 0 and node_status == 0
                passed = observed if expected else not observed
                classification = PASS if expected and passed else (EXPECTED_REJECTION if not expected and passed else 'FAIL')
                results.append(case_result(case_id, classification, python_exit_status=py_status, node_exit_status=node_status, checker_output_tail=tails))
                if not passed:
                    errors.append(f'case failed:{case_id}')
            except Exception as exc:  # noqa: BLE001
                results.append(case_result(case_id, 'FAIL', errors=[f'{type(exc).__name__}:{exc}']))
                errors.append(f'case error:{case_id}')
    classification = suite_classification(results)
    if errors and classification == PASS:
        classification = 'FAIL'
    report = {
        'schema_version': '1.0.0',
        'classification': classification,
        'status': classification,
        'cases': len(results),
        'accepted_attacks': sum(1 for item in results[1:] if item.get('classification') == 'FAIL'),
        'results': results,
        'errors': sorted(set(errors)),
    }
    output = args.json_output if args.json_output.is_absolute() else source / args.json_output
    atomic_write_json(output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(classification)


if __name__ == '__main__':
    raise SystemExit(main())
