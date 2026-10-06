#!/usr/bin/env python3
"""Adversarial semantic-mutation suite for the facility-arrival release.

At least fifteen attacks are fully rehashed after mutation.  Rejection therefore
cannot rely only on stale checksums.  Each case is evaluated by the independent
Python and Node reconstruction checkers.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from release_result import finalize_adversarial_report

from facility_arrival_verifier import (
    canonical_json,
    merkle_root,
    normalize_state,
    sha256_canonical,
    state_hash,
    verify_repository,
)

REPORT = Path('reports/facility-arrival-semantic-mutations.json')


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rehash_bundle(repo: Path) -> None:
    base = repo / 'examples/facility-arrival'
    spec = load(repo / 'config/facility-arrival/ASK-D-001.json')
    session = load(base / 'interaction.json')
    ledger = load(base / 'claim-ledger.json')
    snapshot = load(base / 'source-snapshot.json')
    truth = load(base / 'source-truth.json')
    aar = load(base / 'aar.json')

    previous = state_hash(session['initial_state'])
    for index, transition in enumerate(session['transitions'], start=1):
        transition['sequence'] = index
        transition['before_state_sha256'] = previous
        transition['state_after'] = normalize_state(transition['state_after'])
        transition['after_state_sha256'] = state_hash(transition['state_after'])
        core = {key: value for key, value in transition.items() if key != 'transition_id'}
        transition['transition_id'] = f"FAT-{index:03d}-{sha256_canonical(core)[:12]}"
        previous = transition['after_state_sha256']
    if session['transitions']:
        session['final_state'] = copy.deepcopy(session['transitions'][-1]['state_after'])
    maximum = int(session['final_state'].get('max_positive_points', 0))
    points = int(session['final_state'].get('score_points', 0))
    session['normalized_score_bps'] = 0 if maximum <= 0 else min(10_000, max(0, round(points * 10_000 / maximum)))

    for record in ledger['records']:
        payload = {key: value for key, value in record.items() if key != 'record_sha256'}
        record['record_sha256'] = sha256_canonical(payload)
    ledger_payload = {key: value for key, value in ledger.items() if key != 'ledger_sha256'}
    ledger['ledger_sha256'] = sha256_canonical(ledger_payload)

    snapshot_payload = {key: value for key, value in snapshot.items() if key != 'snapshot_sha256'}
    snapshot['snapshot_sha256'] = sha256_canonical(snapshot_payload)
    for record in truth['records']:
        payload = {key: value for key, value in record.items() if key != 'source_record_sha256'}
        record['source_record_sha256'] = sha256_canonical(payload)
    truth_payload = {key: value for key, value in truth.items() if key != 'source_truth_root_sha256'}
    truth['source_truth_root_sha256'] = sha256_canonical(truth_payload)

    without_certificate = {key: value for key, value in session.items() if key != 'certificate'}
    transition_hashes = [item['after_state_sha256'] for item in session['transitions']]
    replay = {
        'initial_state': session['initial_state'],
        'transitions': [{
            'transition_id': item['transition_id'],
            'before_state_sha256': item['before_state_sha256'],
            'after_state_sha256': item['after_state_sha256'],
        } for item in session['transitions']],
        'final_state': session['final_state'],
    }
    checks = {key: True for key in session['certificate']['checks']}
    session['certificate'] = {
        'certificate_version': '1.0.0',
        'source_binding_sha256': sha256_canonical(session['source_binding']),
        'spec_sha256': sha256_canonical(spec),
        'initial_state_sha256': state_hash(session['initial_state']),
        'final_state_sha256': state_hash(session['final_state']),
        'transition_root_sha256': merkle_root(transition_hashes),
        'replay_root_sha256': sha256_canonical(replay),
        'claim_ledger_sha256': ledger['ledger_sha256'],
        'checks': checks,
        'session_sha256': sha256_canonical(without_certificate),
    }

    aar['session_sha256'] = session['certificate']['session_sha256']
    aar['terminal_status'] = session['final_state']['terminal_status']
    aar['normalized_score_bps'] = session['normalized_score_bps']
    aar_payload = {key: value for key, value in aar.items() if key != 'aar_sha256'}
    aar['aar_sha256'] = sha256_canonical(aar_payload)

    dump(base / 'interaction.json', session)
    dump(base / 'claim-ledger.json', ledger)
    dump(base / 'source-snapshot.json', snapshot)
    dump(base / 'source-truth.json', truth)
    dump(base / 'aar.json', aar)

    manifest = load(base / 'manifest.json')
    manifest['authority'] = session['authority']
    manifest['source_binding'] = session['source_binding']
    manifest['certificate'] = session['certificate']
    manifest['counts'] = {
        'transitions': len(session['transitions']),
        'learner_actions': sum(item['kind'] == 'learner_action' for item in session['transitions']),
        'system_events': sum(item['kind'] == 'system_event' for item in session['transitions']),
        'wit_observations': len(session['transitions']),
        'claim_records': len(ledger['records']),
        'demonstrated_gates': len(aar['validity_ledger']['demonstrated']),
        'open_gates': len(aar['validity_ledger']['open']),
    }
    manifest['hashes'] = {
        'interaction_sha256': file_sha(base / 'interaction.json'),
        'aar_sha256': file_sha(base / 'aar.json'),
        'claim_ledger_sha256': file_sha(base / 'claim-ledger.json'),
        'source_snapshot_sha256': file_sha(base / 'source-snapshot.json'),
        'source_truth_sha256': file_sha(base / 'source-truth.json'),
        'documentation_sha256': file_sha(base / 'README.md'),
    }
    manifest['generated_from']['spec_sha256'] = sha256_canonical(spec)
    manifest['generated_from']['source_snapshot_sha256'] = snapshot['snapshot_sha256']
    manifest['generated_from']['content_registry_root'] = session['source_binding']['content_registry_merkle_root']
    manifest_payload = {key: value for key, value in manifest.items() if key != 'manifest_sha256'}
    manifest['manifest_sha256'] = sha256_canonical(manifest_payload)
    dump(base / 'manifest.json', manifest)


def mutate_json(repo: Path, relative: str, operation: Callable[[Any], None]) -> None:
    path = repo / relative
    value = load(path)
    operation(value)
    dump(path, value)


def node_check(repo: Path) -> dict[str, Any]:
    run = subprocess.run(
        ['node', 'scripts/check_facility_arrival_example.mjs', '--repo', str(repo)],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    try:
        parsed = json.loads(run.stdout)
    except Exception:
        return {
            'healthy': False,
            'status': 'INTERNAL_ERROR',
            'errors': ['node checker output was not structured JSON'],
            'returncode': run.returncode,
        }
    if not isinstance(parsed, dict):
        return {
            'healthy': False,
            'status': 'INTERNAL_ERROR',
            'errors': ['node checker JSON was not an object'],
            'returncode': run.returncode,
        }
    errors = parsed.get('errors', [])
    if not isinstance(errors, list):
        return {
            'healthy': False,
            'status': 'INTERNAL_ERROR',
            'errors': ['node checker returned malformed errors'],
            'returncode': run.returncode,
        }
    internal_error = parsed.get('internal_error') is not False
    status = parsed.get('status')
    healthy = not internal_error and status in {'PASS', 'FAIL'}
    return {
        'healthy': healthy,
        'status': status if isinstance(status, str) else 'INTERNAL_ERROR',
        'errors': [str(item) for item in errors[:16]],
        'returncode': run.returncode,
    }


def copy_repo(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('.git', 'node_modules', 'dist', '.lake', '*.tsbuildinfo'))


def cases() -> list[tuple[str, bool, Callable[[Path], None]]]:
    def session_mut(fn: Callable[[dict[str, Any]], None]) -> Callable[[Path], None]:
        return lambda repo: mutate_json(repo, 'examples/facility-arrival/interaction.json', fn)
    def spec_mut(fn: Callable[[dict[str, Any]], None]) -> Callable[[Path], None]:
        return lambda repo: mutate_json(repo, 'config/facility-arrival/ASK-D-001.json', fn)
    def ledger_mut(fn: Callable[[dict[str, Any]], None]) -> Callable[[Path], None]:
        return lambda repo: mutate_json(repo, 'examples/facility-arrival/claim-ledger.json', fn)

    def surge_before_notice(repo: Path) -> None:
        path = repo / 'examples/facility-arrival/interaction.json'
        value = load(path)
        transitions = value['transitions']
        event_index = next(index for index, item in enumerate(transitions) if item.get('event_id') == 'second_casualty_inbound')
        action_index = next(index for index, item in enumerate(transitions) if item.get('action_id') == 'confirm_surge_roles')
        action = transitions.pop(action_index)
        # Insert the acknowledgement immediately before the notice it requires.
        event_index = next(index for index, item in enumerate(transitions) if item.get('event_id') == 'second_casualty_inbound')
        transitions.insert(event_index, action)
        dump(path, value)

    return [
        ('early_hidden_findings', True, session_mut(lambda x: x['transitions'][1]['state_after'].__setitem__('revealed_hidden_findings', ['forged']))),
        ('score_inflation', True, session_mut(lambda x: x['transitions'][-1]['state_after'].__setitem__('score_points', 999))),
        ('unauthorized_actor_knowledge', True, session_mut(lambda x: x['transitions'][-1]['state_after']['actor_knowledge']['wit_observer'].append('secret_clinical_fact'))),
        ('wit_authority_escalation', True, session_mut(lambda x: x['transitions'][1]['wit_observation'].__setitem__('clinical_directive', 'Treat now'))),
        ('reordered_transitions', True, session_mut(lambda x: x['transitions'].__setitem__(slice(2, 4), [x['transitions'][3], x['transitions'][2]]))),
        ('removed_timeout_event', True, spec_mut(lambda x: x.__setitem__('events', [e for e in x['events'] if e['event_id'] != 'timeout_reached']))),
        ('source_point_forgery', True, lambda repo: mutate_json(repo, 'examples/facility-arrival/source-snapshot.json', lambda x: x['source_actions'][0].__setitem__('points', 999))),
        ('calibration_promotion', True, spec_mut(lambda x: x['parameters']['diagnostic_delay_seconds'].__setitem__('calibration_status', 'SOURCE_BOUND'))),
        ('claim_entailment_promotion', True, ledger_mut(lambda x: x['records'][1].__setitem__('evidence_entailment', 'VERIFIED'))),
        ('command_id_collision', True, session_mut(lambda x: x['command_receipts'][1].__setitem__('command_id', x['command_receipts'][0]['command_id']))),
        ('premature_diagnostics_event', True, session_mut(lambda x: x['transitions'][10].__setitem__('completed_at_seconds', 200))),
        ('surge_ack_before_notice', True, surge_before_notice),
        ('authority_escalation', True, session_mut(lambda x: x['authority'].__setitem__('patient_care_use', 'ALLOWED'))),
        ('operational_source_binding', True, spec_mut(lambda x: next(a for a in x['actions'] if a['action_id'] == 'receive_handoff').__setitem__('source_action_id', 'primary_assessment'))),
        ('operational_score_delta', True, session_mut(lambda x: x['transitions'][1].__setitem__('score_delta', 20))),
        ('unknown_source_action_binding', True, spec_mut(lambda x: next(a for a in x['actions'] if a['action_id'] == 'primary_assessment').__setitem__('source_action_id', 'unknown_source_action'))),
        ('post_terminal_transition', True, session_mut(lambda x: x['transitions'].append(copy.deepcopy(x['transitions'][-1])))),
        ('manifest_path_traversal', False, lambda repo: mutate_json(repo, 'examples/facility-arrival/manifest.json', lambda x: x['files'].__setitem__('interaction', '../interaction.json'))),
        ('generated_spec_divergence', False, lambda repo: (repo / 'src/facility-arrival/specification.generated.ts').write_text('export const FORGED = true;\n', encoding='utf-8')),
        ('registry_source_hash_forgery', False, lambda repo: mutate_json(repo, 'public/data/content_registry/content_registry.json', lambda x: next(a for a in x['assets'] if a['asset_id'] == 'template:ASK-D-001')['source'].__setitem__('file_sha256', '0' * 64))),
        ('licensed_text_in_manifest', True, lambda repo: mutate_json(repo, 'examples/facility-arrival/manifest.json', lambda x: x.__setitem__('licensed_text', 'forbidden'))),
        ('duplicate_transition', True, session_mut(lambda x: x['transitions'].insert(4, copy.deepcopy(x['transitions'][3])))),
        ('removed_diagnostics_event', True, spec_mut(lambda x: x.__setitem__('events', [e for e in x['events'] if e['event_id'] != 'diagnostics_ready']))),
        ('state_snapshot_mismatch', False, session_mut(lambda x: x['transitions'][2]['state_after'].__setitem__('elapsed_seconds', 999))),
        ('source_scenario_id_forgery', True, session_mut(lambda x: x['source_binding'].__setitem__('source_scenario_id', 'ASK-FORGED'))),
        ('registry_root_forgery', True, session_mut(lambda x: x['source_binding'].__setitem__('content_registry_merkle_root', 'f' * 64))),
        ('pass_threshold_calibration_promotion', True, spec_mut(lambda x: x['parameters']['pass_threshold_bps'].__setitem__('calibration_status', 'SOURCE_BOUND'))),
        ('wit_process_flag_removed', True, session_mut(lambda x: x['transitions'][2]['wit_observation'].__setitem__('process_only', False))),
        ('timeout_terminal_without_event', True, session_mut(lambda x: (x['transitions'][-1]['state_after'].__setitem__('terminal_status', 'timeout'), x['transitions'][-1].__setitem__('event_id', None)))),
        ('readme_link_removed', False, lambda repo: (repo / 'README.md').write_text((repo / 'README.md').read_text(encoding='utf-8').replace('examples/facility-arrival/README.md', 'examples/removed/README.md', 1), encoding='utf-8')),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=Path('.'))
    args = parser.parse_args()
    source = args.repo.resolve()
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix='asklepios-facility-mutations-') as temp:
        temp_root = Path(temp)
        for index, (case_id, globally_rehashed, mutate) in enumerate(cases(), start=1):
            candidate = temp_root / f'{index:02d}-{case_id}'
            copy_repo(source, candidate)
            mutate(candidate)
            if globally_rehashed:
                rehash_bundle(candidate)
            python_report = verify_repository(candidate)
            node_report = node_check(candidate)
            python_rejected = python_report.get('status') == 'FAIL'
            node_rejected = node_report.get('healthy') is True and node_report.get('status') == 'FAIL'
            passed = python_rejected and node_rejected
            results.append({
                'case_id': case_id,
                'globally_rehashed': globally_rehashed,
                'python_rejected': python_rejected,
                'node_rejected': node_rejected,
                'node_checker_healthy': node_report.get('healthy') is True,
                'node_checker_internal_error': node_report.get('healthy') is not True,
                'pass': passed,
                'python_errors': python_report.get('errors', [])[:12],
                'node_errors': node_report.get('errors', []),
            })
    report = {
        'schema_version': '1.0.0',
        'status': 'PASS' if all(item['pass'] for item in results) else 'FAIL',
        'attacks': len(results),
        'cases': len(results),
        'globally_rehashed_attacks': sum(item['globally_rehashed'] for item in results),
        'globally_rehashed_cases': sum(item['globally_rehashed'] for item in results),
        'rejected_by_python': sum(item['python_rejected'] for item in results),
        'rejected_by_node': sum(item['node_rejected'] for item in results),
        'rejected_by_both': sum(item['python_rejected'] and item['node_rejected'] for item in results),
        'rejected_by_both_independent_checkers': sum(item['python_rejected'] and item['node_rejected'] for item in results),
        'node_checker_internal_errors': sum(item['node_checker_internal_error'] for item in results),
        'anti_circular_note': 'Globally rehashed attacks recalculate transition, session, AAR, and manifest digests before independent checking. A checker crash or malformed report is a suite failure, never a valid rejection.',
        'results': results,
    }
    report = finalize_adversarial_report(report, baseline_case_ids=())
    output = source / REPORT
    output.parent.mkdir(parents=True, exist_ok=True)
    dump(output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['status'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
