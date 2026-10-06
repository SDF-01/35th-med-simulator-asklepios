#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROFILE = Path('config/facility-decision/ASK-D-001.json')
FACILITY = Path('config/facility-arrival/ASK-D-001.json')
DEFAULT_REPORT = Path('reports/facility-decision-sequence-assurance.json')


@dataclass(frozen=True)
class TraceResult:
    trace_id: str
    sequence: tuple[str, ...]
    terminal: str
    elapsed_seconds: int
    errors: tuple[str, ...]


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def ordered_contains(sequence: tuple[str, ...], obligation: tuple[str, ...]) -> bool:
    position = -1
    for item in obligation:
        try:
            position = sequence.index(item, position + 1)
        except ValueError:
            return False
    return True


def simulate(trace_id: str, sequence: list[str], profile: dict[str, Any], facility: dict[str, Any]) -> TraceResult:
    decisions = {item['decision_id']: item for item in profile['decisions']}
    actions = {item['action_id']: item for item in facility['actions']}
    resources = {item['resource_id']: item for item in profile['operational_model']['resources']}
    diagnostics = {item['order_code']: item for item in profile['diagnostic_catalog']}
    completed: set[str] = set()
    elapsed = 0
    world_events: set[str] = set()
    results: set[str] = set()
    orders: dict[str, dict[str, int | str]] = {}
    terminal = 'active'
    errors: list[str] = []
    timeout = int(facility['parameters']['timeout_seconds']['value'])

    def sync_world() -> None:
        for event in profile['operational_model']['world_events']:
            if elapsed >= int(event['at_elapsed_seconds']):
                world_events.add(event['event_id'])

    def create_orders(decision: dict[str, Any]) -> None:
        nonlocal orders
        for code in decision.get('creates_orders', []):
            spec = diagnostics[code]
            resource = resources[spec['resource_id']]
            earlier_due = [int(order['due']) for order in orders.values() if order['resource'] == spec['resource_id']]
            start = max([elapsed, *earlier_due]) if earlier_due else elapsed
            orders[code] = {
                'resource': spec['resource_id'],
                'start': start,
                'due': start + int(resource['service_duration_seconds']),
            }

    for ordinal, decision_id in enumerate(sequence, 1):
        if terminal != 'active':
            errors.append(f'post-terminal decision:{ordinal}:{decision_id}')
            break
        decision = decisions.get(decision_id)
        if not decision:
            errors.append(f'unknown decision:{decision_id}')
            continue
        if not decision.get('repeatable', False) and decision_id in completed:
            errors.append(f'duplicate nonrepeatable decision:{decision_id}')
        for prerequisite in decision.get('prerequisites', []):
            if prerequisite not in completed:
                errors.append(f'prerequisite missing:{decision_id}:{prerequisite}')
        for event_id in decision.get('required_world_events', []):
            if event_id not in world_events:
                errors.append(f'world event missing:{decision_id}:{event_id}')
        for result_id in decision.get('requires_results', []):
            if result_id not in results:
                errors.append(f'result missing:{decision_id}:{result_id}')

        action = actions[decision['facility_action_id']]
        if decision_id == 'wait_for_diagnostics':
            if set(orders) != set(diagnostics):
                errors.append('diagnostic wait before exact orders')
                duration = 0
            else:
                resource_due = max(int(order['due']) for order in orders.values())
                # Resource service durations intentionally mirror the source-bound diagnostic delay.
                # Do not add the delay twice.
                duration = max(0, resource_due - elapsed)
        else:
            duration = int(action['duration_seconds'])

        if elapsed + duration > timeout or (decision_id == 'wait_60' and elapsed + duration >= timeout):
            elapsed = timeout
            terminal = 'timeout'
            world_events.add('timeout_reached')
            continue

        elapsed += duration
        completed.add(decision_id)
        create_orders(decision)
        sync_world()

        if decision_id == 'wait_for_diagnostics' and set(orders) == set(diagnostics):
            results.update(item['result_id'] for item in diagnostics.values())
            world_events.add('diagnostics_ready')
        if decision_id in {'discharge_without_workup', 'remove_tourniquet'}:
            terminal = 'failed'
        elif decision_id == 'complete_handoff':
            terminal = 'completed'

    return TraceResult(trace_id, tuple(sequence), terminal, elapsed, tuple(sorted(set(errors))))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--json-output', default=DEFAULT_REPORT.as_posix())
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    profile = load(repo / PROFILE)
    facility = load(repo / FACILITY)
    refs = profile['assurance']['reference_sequences']

    traces: list[TraceResult] = []
    traces.append(simulate('canonical', list(refs['canonical']), profile, facility))
    traces.append(simulate('alternate', list(refs['alternate']), profile, facility))

    # Additional valid orderings are predeclared here and independently checked rather than derived from coverage gaps.
    traces.extend([
        simulate('imaging_before_monitoring', [
            'receive_handoff','primary_assessment','order_imaging','differential','monitor_vitals',
            'order_labs','documentation','pain_management','wait_for_diagnostics','review_diagnostics',
            'confirm_surge_roles','escalation','complete_handoff',
        ], profile, facility),
        simulate('labs_before_imaging', [
            'receive_handoff','primary_assessment','order_labs','differential','monitor_vitals',
            'order_imaging','pain_management','documentation','wait_for_diagnostics','review_diagnostics',
            'confirm_surge_roles','escalation','complete_handoff',
        ], profile, facility),
        simulate('unsafe_discharge', ['receive_handoff','discharge_without_workup'], profile, facility),
        simulate('unsafe_tourniquet', ['receive_handoff','remove_tourniquet'], profile, facility),
        simulate('timeout', ['receive_handoff'] + ['wait_60'] * 20, profile, facility),
    ])

    pair_obligations = [tuple(item) for item in profile['assurance']['ordered_pair_obligations']]
    triple_obligations = [tuple(item) for item in profile['assurance']['ordered_triple_obligations']]
    successful = [trace for trace in traces if trace.terminal == 'completed' and not trace.errors]
    pair_coverage = {
        ' > '.join(obligation): sorted(trace.trace_id for trace in successful if ordered_contains(trace.sequence, obligation))
        for obligation in pair_obligations
    }
    triple_coverage = {
        ' > '.join(obligation): sorted(trace.trace_id for trace in successful if ordered_contains(trace.sequence, obligation))
        for obligation in triple_obligations
    }

    errors: list[str] = []
    expected_terminals = {
        'canonical': 'completed',
        'alternate': 'completed',
        'unsafe_discharge': 'failed',
        'unsafe_tourniquet': 'failed',
        'timeout': 'timeout',
    }
    by_id = {trace.trace_id: trace for trace in traces}
    for trace_id, expected in expected_terminals.items():
        trace = by_id[trace_id]
        if trace.terminal != expected:
            errors.append(f'terminal mismatch:{trace_id}:{trace.terminal}:{expected}')
        if trace.errors:
            errors.extend(f'trace invalid:{trace_id}:{error}' for error in trace.errors)
    if refs['canonical'] == refs['alternate']:
        errors.append('canonical and alternate reference sequences are identical')
    for key, covering in pair_coverage.items():
        if not covering:
            errors.append(f'uncovered ordered pair:{key}')
    for key, covering in triple_coverage.items():
        if not covering:
            errors.append(f'uncovered ordered triple:{key}')

    report = {
        'schema_version': '1.0.0',
        'status': 'PASS' if not errors else 'FAIL',
        'trace_count': len(traces),
        'successful_completion_traces': len(successful),
        'required_ordered_pairs': len(pair_obligations),
        'covered_ordered_pairs': sum(bool(value) for value in pair_coverage.values()),
        'required_ordered_triples': len(triple_obligations),
        'covered_ordered_triples': sum(bool(value) for value in triple_coverage.values()),
        'pair_coverage': pair_coverage,
        'triple_coverage': triple_coverage,
        'traces': [
            {
                'trace_id': trace.trace_id,
                'terminal': trace.terminal,
                'elapsed_seconds': trace.elapsed_seconds,
                'sequence': list(trace.sequence),
                'errors': list(trace.errors),
            }
            for trace in traces
        ],
        'anti_gaming_note': 'Obligations and trace fixtures are declared before coverage measurement. Coverage is measured over ordered subsequences, not inferred from a passing report field.',
        'errors': sorted(set(errors)),
    }
    output = repo / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
