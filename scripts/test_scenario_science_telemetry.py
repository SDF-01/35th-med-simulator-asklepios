#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from portable_test_workspace import WORKSPACE_PROFILE, temporary_workspace

from scenario_science_common import POLICY_REL, TELEMETRY_REL, event_chain_root, event_sha256, policy_sha256, write_json_atomic


def run_checker(repo: Path) -> tuple[bool, list[str]]:
    commands = [
        [sys.executable, 'scripts/build_scenario_science_telemetry.py', '--repo', '.', '--check'],
        ['node', 'scripts/check_scenario_science_telemetry.mjs', '--repo', '.'],
    ]
    errors: list[str] = []
    ok = True
    for command in commands:
        completed = subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False, timeout=60)
        if completed.returncode != 0:
            ok = False
        text = (completed.stdout or '') + '\n' + (completed.stderr or '')
        try:
            start = text.find('{')
            value = json.loads(text[start:]) if start >= 0 else {}
            errors.extend(value.get('errors') or [])
        except Exception:
            errors.append(text[-1000:])
    return ok, sorted(set(errors))


def rehash_events(telemetry: dict[str, Any]) -> None:
    previous = None
    for sequence, event in enumerate(telemetry['events']):
        event['sequence'] = sequence
        event['previous_event_sha256'] = previous
        event['event_sha256'] = event_sha256(event)
        previous = event['event_sha256']
    telemetry['event_chain_root_sha256'] = event_chain_root(telemetry['events'])


def mutate_policy(repo: Path, fn: Callable[[dict[str, Any]], None]) -> None:
    path = repo / POLICY_REL
    value = json.loads(path.read_text())
    fn(value)
    value['policy_sha256'] = policy_sha256(value)
    write_json_atomic(path, value)


def mutate_telemetry(repo: Path, fn: Callable[[dict[str, Any]], None], *, rehash: bool = False) -> None:
    path = repo / TELEMETRY_REL
    value = json.loads(path.read_text())
    fn(value)
    if rehash:
        rehash_events(value)
    write_json_atomic(path, value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--json-output', default='reports/scenario-science-telemetry-mutations.json')
    args = parser.parse_args()
    source = Path(args.repo).resolve()
    cases: list[tuple[str, Callable[[Path], None] | None, bool, str | None]] = [
        ('baseline', None, True, None),
        ('phi-field-rejected', lambda r: mutate_telemetry(r, lambda t: t['events'][1]['payload'].__setitem__('patient_name', 'forbidden'), rehash=True), False, 'forbidden privacy field'),
        ('sequence-gap-rejected', lambda r: mutate_telemetry(r, lambda t: t['events'][2].__setitem__('sequence', 9)), False, 'event sequence is not contiguous'),
        ('logical-time-regression-rejected', lambda r: mutate_telemetry(r, lambda t: t['events'][2].__setitem__('logical_time_seconds', -1), rehash=True), False, 'event logical time invalid'),
        ('previous-hash-forgery-rejected', lambda r: mutate_telemetry(r, lambda t: t['events'][2].__setitem__('previous_event_sha256', '0' * 64)), False, 'event previous hash differs'),
        ('event-hash-forgery-rejected', lambda r: mutate_telemetry(r, lambda t: t['events'][2].__setitem__('event_sha256', '0' * 64)), False, 'event hash differs'),
        ('unknown-event-kind-rejected', lambda r: mutate_telemetry(r, lambda t: t['events'][2].__setitem__('event_kind', 'CLINICAL_OVERRIDE'), rehash=True), False, 'event kind is not allowed'),
        ('uncalibrated-timing-score-rejected', lambda r: mutate_telemetry(r, lambda t: t['events'][2].__setitem__('scoring_effect', 'BONUS'), rehash=True), False, 'uncalibrated timing changed score'),
        ('direct-care-policy-escalation-rejected', lambda r: mutate_policy(r, lambda p: p['telemetry_boundaries'].__setitem__('direct_patient_care', 'PERMITTED')), False, 'policy authority or telemetry boundary differs:direct_patient_care'),
        ('clinical-decision-support-escalation-rejected', lambda r: mutate_policy(r, lambda p: p['telemetry_boundaries'].__setitem__('clinical_decision_support', 'PERMITTED')), False, 'policy authority or telemetry boundary differs:clinical_decision_support'),
        ('calibration-ladder-shortcut-rejected', lambda r: mutate_policy(r, lambda p: p['calibration_state_order'].remove('SITE_HOLDOUT_PASSED')), False, 'policy compiled floor differs:calibration_state_order'),
        ('scoring-ladder-shortcut-rejected', lambda r: mutate_policy(r, lambda p: p['scoring_state_order'].remove('HELD_OUT_CALIBRATED')), False, 'policy compiled floor differs:scoring_state_order'),
        ('safety-overridden-by-statistics-rejected', lambda r: mutate_policy(r, lambda p: p['scoring_boundary'].__setitem__('critical_safety_failure_overridable_by_statistical_score', True)), False, 'statistical score may override critical safety failure'),
        ('cosmetic-novelty-promotion-rejected', lambda r: mutate_policy(r, lambda p: p['behavioral_novelty_boundary'].__setitem__('narrative_only_variant_creates_new_behavior', True)), False, 'cosmetic variant may create new behavior'),
        ('terminal-event-removal-rejected', lambda r: mutate_telemetry(r, lambda t: t['events'].pop(), rehash=True), False, 'terminal telemetry event missing'),
        ('duplicate-event-id-rejected', lambda r: mutate_telemetry(r, lambda t: t['events'][2].__setitem__('event_id', t['events'][1]['event_id']), rehash=True), False, 'event ID duplicated'),
        ('genome-binding-forgery-rejected', lambda r: mutate_telemetry(r, lambda t: t.__setitem__('scenario_genome_sha256', '0' * 64)), False, 'telemetry Scenario Genome hash differs'),
        ('event-root-forgery-rejected', lambda r: mutate_telemetry(r, lambda t: t.__setitem__('event_chain_root_sha256', '0' * 64)), False, 'event-chain root differs'),
    ]
    results = []
    errors = []
    for case_id, mutation, expected_pass, required_error in cases:
        with temporary_workspace('ask-st-') as workspace:
            repo = workspace / 'repo'
            shutil.copytree(source, repo, ignore=shutil.ignore_patterns('.git', 'node_modules', '.asklepios', '__pycache__', '*.pyc'))
            if mutation:
                mutation(repo)
            observed_pass, observed_errors = run_checker(repo)
            case_pass = observed_pass == expected_pass and (required_error is None or any(required_error in item for item in observed_errors))
            classification = 'PASS' if expected_pass and observed_pass else 'EXPECTED_REJECTION' if not expected_pass and not observed_pass else 'FAIL'
            results.append({'case_id': case_id, 'classification': classification, 'observed_pass': observed_pass, 'expected_pass': expected_pass, 'required_error': required_error, 'checker_errors': observed_errors, 'pass': case_pass})
            if not case_pass:
                errors.append(f'case failed:{case_id}')
    report = {'schema_version':'1.0.0','classification':'PASS' if not errors else 'FAIL','cases':len(results),'attacks':len(results)-1,'accepted_attacks':sum(1 for item in results[1:] if item['observed_pass']),'workspace_profile':WORKSPACE_PROFILE,'results':results,'errors':errors}
    write_json_atomic(source / args.json_output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 3


if __name__ == '__main__':
    raise SystemExit(main())
