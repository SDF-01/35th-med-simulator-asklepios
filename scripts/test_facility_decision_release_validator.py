#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable
from release_result import finalize_adversarial_report

REPORT = Path('reports/facility-decision-release-validator-mutations.json')
Mutation = Callable[[Path], None]


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location('facility_decision_release_validator', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('validator module could not be loaded')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')


def copy_file(source: Path, target: Path, relative: Path) -> None:
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / relative, destination)


def prepare_fixture(source: Path, target: Path, validator) -> None:
    required = {
        Path('scripts/validate_facility_decision_release.py'),
        Path('config/facility-decision/ASK-D-001.json'),
        Path('config/facility-decision/VALIDITY_BOUNDARIES.json'),
        Path('config/facility-arrival/ASK-D-001.json'),
        Path('config/facility-decision/EVIDENCE_PROMOTION_REGISTRY.json'),
        Path('examples/facility-decision/manifest.json'),
        Path('package-lock.json'),
        Path('lean-toolchain'),
        Path('lake-manifest.json'),
        *validator.REQUIRED_REPORTS.values(),
    }
    manifest = read(source / 'examples/facility-decision/manifest.json')
    for name in manifest.get('files', {}):
        required.add(Path('examples/facility-decision') / name)
    for relative in sorted(required):
        copy_file(source, target, relative)
    write(target / validator.LIVE_REPORTS['axiom'], {
        'schema_version': '1.0.0', 'status': 'PASS',
        'theorems_expected': 17, 'theorems_observed': 17, 'errors': [],
    })
    write(target / validator.LIVE_REPORTS['reproducibility'], {
        'schema_version': '1.0.0', 'status': 'PASS',
        'files_compared': 2, 'errors': [],
    })
    write(target / validator.LIVE_REPORTS['provenance'], {
        '_type': 'https://in-toto.io/Statement/v1',
        'predicateType': 'https://slsa.dev/provenance/v1',
        'subject': [{'name': 'index.html', 'digest': {'sha256': '0' * 64}}],
        'asklepios_verification': {
            'status': 'PASS', 'signature_status': 'UNSIGNED',
            'claim_scope': 'BUILD_IDENTITY_ONLY', 'errors': [],
        },
    })


def mutate_json(relative: str, fn: Callable[[dict[str, Any]], None]) -> Mutation:
    def mutate(repo: Path) -> None:
        path = repo / relative
        value = read(path)
        fn(value)
        write(path, value)
    return mutate


def remove(relative: str) -> Mutation:
    return lambda repo: (repo / relative).unlink()


def tamper_manifest_file(repo: Path) -> None:
    path = repo / 'examples/facility-decision/learner-projection.json'
    path.write_text(path.read_text(encoding='utf-8') + '\n', encoding='utf-8', newline='\n')


def reduce_mutation_inventory(repo: Path) -> None:
    path = repo / 'reports/facility-decision-mutations.json'
    value = read(path)
    value['results'] = value['results'][:-1]
    value['attacks'] = value.get('attacks', 0) - 1
    write(path, value)




def admit_evidence_rule(repo: Path) -> None:
    path = repo / 'reports/facility-decision-evidence-promotion.json'
    value = read(path)
    value['admitted_clinical_rules'] = 1
    write(path, value)


def weaken_evidence_mutations(repo: Path) -> None:
    path = repo / 'reports/facility-decision-evidence-promotion-mutations.json'
    value = read(path)
    value['attacks'] = 1
    value['results'] = value.get('results', [])[:2]
    write(path, value)


def couple_world_event_to_imaging(repo: Path) -> None:
    path = repo / 'config/facility-arrival/ASK-D-001.json'
    value = read(path)
    event = next(row for row in value['events'] if row['event_id'] == 'second_casualty_inbound')
    event['trigger'] = {'kind': 'after_action', 'action_id': 'order_imaging'}
    write(path, value)

def crash_validator(repo: Path) -> None:
    (repo / 'scripts/validate_facility_decision_release.py').write_text('this is not python\n', encoding='utf-8', newline='\n')


CASES: list[tuple[str, Mutation, str]] = [
    ('missing_axiom_report', remove('reports/facility-decision-axiom-check.json'), 'REJECTED'),
    ('axiom_inventory_weakened', mutate_json('reports/facility-decision-axiom-check.json', lambda d: d.__setitem__('theorems_observed', 16)), 'REJECTED'),
    ('axiom_status_failed', mutate_json('reports/facility-decision-axiom-check.json', lambda d: d.__setitem__('status', 'FAIL')), 'REJECTED'),
    ('reproducibility_error', mutate_json('reports/facility-decision-build-reproducibility.json', lambda d: d['errors'].append('changed:index.js')), 'REJECTED'),
    ('false_signed_provenance', mutate_json('reports/facility-decision-build-provenance.json', lambda d: d['asklepios_verification'].__setitem__('signature_status', 'SIGNED')), 'REJECTED'),
    ('empty_provenance_subject', mutate_json('reports/facility-decision-build-provenance.json', lambda d: d.__setitem__('subject', [])), 'REJECTED'),
    ('source_report_failed', mutate_json('reports/facility-decision-integrity-python.json', lambda d: d.__setitem__('status', 'FAIL')), 'REJECTED'),
    ('mutation_inventory_reduced', reduce_mutation_inventory, 'REJECTED'),
    ('manifest_bound_file_tampered', tamper_manifest_file, 'REJECTED'),
    ('patient_care_authority_escalated', mutate_json('config/facility-decision/ASK-D-001.json', lambda d: d['authority'].__setitem__('patient_care_use', 'GRANTED')), 'REJECTED'),
    ('world_event_action_coupling_rejected', couple_world_event_to_imaging, 'REJECTED'),
    ('evidence_rule_prematurely_admitted', admit_evidence_rule, 'REJECTED'),
    ('evidence_mutation_inventory_weakened', weaken_evidence_mutations, 'REJECTED'),
    ('validator_internal_error_is_not_rejection', crash_validator, 'INTERNAL_ERROR'),
]


def classify(repo: Path) -> tuple[str, list[str]]:
    completed = subprocess.run(
        [sys.executable, 'scripts/validate_facility_decision_release.py', '--repo', '.', '--mode', 'release', '--json-output', 'reports/result.json'],
        cwd=repo, text=True, capture_output=True,
    )
    try:
        payload = json.loads(completed.stdout)
    except Exception:
        return 'INTERNAL_ERROR', ['validator_failed_before_structured_result']
    errors = payload.get('errors', []) if isinstance(payload, dict) and isinstance(payload.get('errors'), list) else []
    if completed.returncode == 0 and payload.get('status') == 'PASS':
        return 'PASS', errors
    if completed.returncode != 0 and payload.get('status') == 'FAIL':
        return 'REJECTED', errors
    return 'INTERNAL_ERROR', ['validator_returned_inconsistent_result']


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--json-output', default=REPORT.as_posix())
    args = parser.parse_args()
    source = Path(args.repo).resolve()
    validator = load_module(source / 'scripts/validate_facility_decision_release.py')
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    with tempfile.TemporaryDirectory(prefix='asklepios-release-validator-baseline-') as temp:
        fixture = Path(temp) / 'repo'
        fixture.mkdir()
        prepare_fixture(source, fixture, validator)
        observed, details = classify(fixture)
        passed = observed == 'PASS'
        if not passed:
            errors.append(f'baseline:expected=PASS:observed={observed}')
        results.append({'case_id': 'baseline', 'expected': 'PASS', 'classification': observed, 'pass': passed, 'checker_errors': details})

    for case_id, mutation, expected in CASES:
        with tempfile.TemporaryDirectory(prefix='asklepios-release-validator-case-') as temp:
            fixture = Path(temp) / 'repo'
            fixture.mkdir()
            prepare_fixture(source, fixture, validator)
            mutation(fixture)
            observed, details = classify(fixture)
            passed = observed == expected
            if not passed:
                errors.append(f'{case_id}:expected={expected}:observed={observed}')
            results.append({'case_id': case_id, 'expected': expected, 'classification': observed, 'pass': passed, 'checker_errors': details})

    report = {
        'schema_version': '1.0.0',
        'status': 'PASS' if not errors else 'FAIL',
        'cases': len(results),
        'attacks': len(CASES),
        'accepted_attacks': sum(1 for row in results[1:] if row['classification'] == 'PASS'),
        'unexpected_internal_errors': sum(1 for row in results[1:] if row['classification'] == 'INTERNAL_ERROR' and row['expected'] != 'INTERNAL_ERROR'),
        'results': results,
        'errors': errors,
    }
    report = finalize_adversarial_report(report, baseline_case_ids=("baseline",))
    output = source / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 3


if __name__ == '__main__':
    raise SystemExit(main())
