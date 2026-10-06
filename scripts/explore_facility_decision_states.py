#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import deque
from pathlib import Path
from typing import Any, NamedTuple

PROFILE = Path('config/facility-decision/ASK-D-001.json')
FACILITY = Path('config/facility-arrival/ASK-D-001.json')
DEFAULT_REPORT = Path('reports/facility-decision-state-exploration.json')
DEFAULT_FIXTURES = Path('reports/facility-decision-differential-fixtures.json')

ACTIVE, COMPLETED, FAILED, TIMEOUT = 0, 1, 2, 3
TERMINAL_NAMES = {ACTIVE: 'active', COMPLETED: 'completed', FAILED: 'failed', TIMEOUT: 'timeout'}
EVENT_PREARRIVAL = 1 << 0
EVENT_SECOND = 1 << 1
EVENT_DIAGNOSTICS = 1 << 2
EVENT_TIMEOUT = 1 << 3
RESULT_CHEST = 1 << 0
RESULT_LACTATE = 1 << 1
CLOCK_ABSENT = -1
CLOCK_SATURATED = 180


class State(NamedTuple):
    completed_mask: int
    elapsed: int
    terminal: int
    events_mask: int
    image_age: int
    lactate_age: int
    results_mask: int
    waits: int
    reassessment_age: int


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def advance_clock(value: int, duration: int) -> int:
    if value == CLOCK_ABSENT:
        return CLOCK_ABSENT
    return min(CLOCK_SATURATED, value + duration)


class Model:
    """Independent finite-region model of the RC3.6A decision layer.

    Absolute diagnostic timestamps are quotient-ed into timed-automata clock regions:
    absent, exact age below the 180-second service threshold, or saturated at/after
    180 seconds. The quotient preserves every comparison made by the executable
    runtime while avoiding millions of history-only timestamp variants.
    """

    def __init__(self, profile: dict[str, Any], facility: dict[str, Any]):
        self.profile = profile
        self.facility = facility
        self.decisions = profile['decisions']
        self.ids = [item['decision_id'] for item in self.decisions]
        self.index = {item: idx for idx, item in enumerate(self.ids)}
        self.actions = {item['action_id']: item for item in facility['actions']}
        self.timeout = int(facility['parameters']['timeout_seconds']['value'])
        self.stale_after = int(profile['operational_model']['information_staleness_seconds'])
        resources = {item['resource_id']: item for item in profile['operational_model']['resources']}
        diagnostics = {item['order_code']: item for item in profile['diagnostic_catalog']}
        self.image_duration = int(resources[diagnostics['CHEST_IMAGING']['resource_id']]['service_duration_seconds'])
        self.lactate_duration = int(resources[diagnostics['LACTATE']['resource_id']]['service_duration_seconds'])
        if self.image_duration != CLOCK_SATURATED or self.lactate_duration != CLOCK_SATURATED:
            raise ValueError('region abstraction currently requires both admitted diagnostic service durations to equal 180 seconds')
        self.second_event_at = int(profile['operational_model']['world_events'][0]['at_elapsed_seconds'])
        self.wait_index = self.index['wait_60']
        self.reassessment_indices = {self.index[item] for item in ['primary_assessment','monitor_vitals','wait_for_diagnostics','review_diagnostics']}

        self.prereq_masks: list[int] = []
        self.required_event_masks: list[int] = []
        self.required_result_masks: list[int] = []
        self.repeatable: list[bool] = []
        self.duration_modes: list[str] = []
        self.durations: list[int] = []
        self.terminal_effects: list[int] = []
        self.create_order: list[int] = []

        action_to_decision = {item['facility_action_id']: item['decision_id'] for item in self.decisions}
        event_bits = {'second_casualty_inbound': EVENT_SECOND, 'diagnostics_ready': EVENT_DIAGNOSTICS, 'timeout_reached': EVENT_TIMEOUT, 'prearrival_notice': EVENT_PREARRIVAL}
        result_bits = {'CHEST_IMAGING_REPORT': RESULT_CHEST, 'LACTATE_RESULT': RESULT_LACTATE}
        for decision in self.decisions:
            action = self.actions[decision['facility_action_id']]
            prereqs = set(decision.get('prerequisites', []))
            prereqs.update(action_to_decision[item] for item in action.get('prerequisites', []) if item in action_to_decision)
            mask = sum(1 << self.index[item] for item in prereqs)
            self.prereq_masks.append(mask)
            event_mask = 0
            for item in [*decision.get('required_world_events', []), *action.get('required_event_ids', [])]:
                event_mask |= event_bits[item]
            self.required_event_masks.append(event_mask)
            result_mask = 0
            for item in decision.get('requires_results', []):
                result_mask |= result_bits[item]
            self.required_result_masks.append(result_mask)
            self.repeatable.append(bool(decision.get('repeatable', False)))
            self.duration_modes.append(action['duration_mode'])
            self.durations.append(int(action['duration_seconds']))
            terminal = action.get('terminal_effect')
            self.terminal_effects.append(COMPLETED if terminal == 'completed' else FAILED if terminal == 'failed' else ACTIVE)
            creates = set(decision.get('creates_orders', []))
            self.create_order.append(1 if 'CHEST_IMAGING' in creates else 2 if 'LACTATE' in creates else 0)

        self.complete_index = self.index['complete_handoff']
        required_decisions = {
            action_to_decision[action_id]
            for action_id in facility['completion']['required_operational_actions']
            if action_id != 'complete_handoff' and action_id in action_to_decision
        }
        required_decisions.update(['primary_assessment','monitor_vitals','differential','order_imaging','order_labs','escalation'])
        self.completion_mask = sum(1 << self.index[item] for item in required_decisions)
        self.completion_events_mask = sum(event_bits[item] for item in facility['completion']['required_event_ids'])

    def initial(self) -> State:
        return self.sync(State(0, 0, ACTIVE, EVENT_PREARRIVAL, CLOCK_ABSENT, CLOCK_ABSENT, 0, 0, CLOCK_ABSENT))

    def sync(self, state: State) -> State:
        mask, elapsed, terminal, events, image_age, lactate_age, results, waits, reassessment_age = state
        if elapsed >= self.second_event_at:
            events |= EVENT_SECOND
        if image_age == CLOCK_SATURATED and lactate_age == CLOCK_SATURATED:
            events |= EVENT_DIAGNOSTICS
            results |= RESULT_CHEST | RESULT_LACTATE
        if elapsed >= self.timeout and terminal == ACTIVE:
            elapsed = self.timeout
            terminal = TIMEOUT
            events |= EVENT_TIMEOUT
        return State(mask, elapsed, terminal, events, image_age, lactate_age, results, waits, reassessment_age)

    def duration_for(self, state: State, idx: int) -> int:
        if self.duration_modes[idx] == 'until_diagnostics':
            if state.image_age == CLOCK_ABSENT or state.lactate_age == CLOCK_ABSENT:
                return 0
            return max(0, CLOCK_SATURATED - min(state.image_age, state.lactate_age))
        return self.durations[idx]

    def enabled_indices(self, state: State) -> tuple[int, ...]:
        if state.terminal != ACTIVE:
            return ()
        enabled: list[int] = []
        for idx in range(len(self.ids)):
            bit = 1 << idx
            if not self.repeatable[idx] and state.completed_mask & bit:
                continue
            if state.completed_mask & self.prereq_masks[idx] != self.prereq_masks[idx]:
                continue
            if state.events_mask & self.required_event_masks[idx] != self.required_event_masks[idx]:
                continue
            if state.results_mask & self.required_result_masks[idx] != self.required_result_masks[idx]:
                continue
            if idx == self.complete_index:
                if state.completed_mask & self.completion_mask != self.completion_mask:
                    continue
                if state.events_mask & self.completion_events_mask != self.completion_events_mask:
                    continue
            duration = self.duration_for(state, idx)
            if idx != self.wait_index and state.elapsed + duration > self.timeout:
                continue
            enabled.append(idx)
        return tuple(enabled)

    def step(self, state: State, idx: int) -> State:
        if idx not in self.enabled_indices(state):
            raise ValueError(f'disabled:{self.ids[idx]}')
        mask, elapsed, terminal, events, image_age, lactate_age, results, waits, reassessment_age = state
        duration = self.duration_for(state, idx)
        target = elapsed + duration
        if target > self.timeout:
            duration = self.timeout - elapsed
            target = self.timeout
        image_age = advance_clock(image_age, duration)
        lactate_age = advance_clock(lactate_age, duration)
        reassessment_age = advance_clock(reassessment_age, duration)
        mask |= 1 << idx
        if self.create_order[idx] == 1 and image_age == CLOCK_ABSENT:
            image_age = 0
        elif self.create_order[idx] == 2 and lactate_age == CLOCK_ABSENT:
            lactate_age = 0
        if idx == self.wait_index:
            waits += 1
        if idx in self.reassessment_indices:
            reassessment_age = 0
        effect = self.terminal_effects[idx]
        if effect != ACTIVE:
            terminal = effect
        return self.sync(State(mask, target, terminal, events, image_age, lactate_age, results, waits, reassessment_age))

    def projection(self, state: State) -> dict[str, Any]:
        completed = [self.ids[idx] for idx in range(len(self.ids)) if state.completed_mask & (1 << idx)]
        events = []
        for bit, name in [(EVENT_PREARRIVAL,'prearrival_notice'),(EVENT_SECOND,'second_casualty_inbound'),(EVENT_DIAGNOSTICS,'diagnostics_ready'),(EVENT_TIMEOUT,'timeout_reached')]:
            if state.events_mask & bit:
                events.append(name)
        results = []
        if state.results_mask & RESULT_CHEST: results.append('CHEST_IMAGING_REPORT')
        if state.results_mask & RESULT_LACTATE: results.append('LACTATE_RESULT')
        orders = []
        for code, resource, age, result_bit in [
            ('CHEST_IMAGING','CHEST_IMAGING_SERVICE',state.image_age,RESULT_CHEST),
            ('LACTATE','LABORATORY_SERVICE',state.lactate_age,RESULT_LACTATE),
        ]:
            if age != CLOCK_ABSENT:
                status = 'result_available' if state.results_mask & result_bit else 'completed_pending_release' if age == CLOCK_SATURATED else 'in_progress'
                orders.append({'order_code':code,'resource_id':resource,'age_region_seconds':age,'status':status})
        staleness = state.elapsed if state.reassessment_age == CLOCK_ABSENT else state.reassessment_age
        return {
            'completed_decision_ids': sorted(completed),
            'elapsed_seconds': state.elapsed,
            'terminal_status': TERMINAL_NAMES[state.terminal],
            'visible_world_event_ids': ['second_casualty_inbound'] if state.events_mask & EVENT_SECOND else [],
            'fired_facility_event_ids': sorted(events),
            'orders': sorted(orders, key=lambda item: item['order_code']),
            'result_ids': sorted(results),
            'wait_count': state.waits,
            'reassessment_due': state.terminal == ACTIVE and staleness >= self.stale_after,
            'staleness_region_seconds': min(CLOCK_SATURATED, staleness),
            'available_decision_ids': sorted(self.ids[idx] for idx in self.enabled_indices(state)),
            'timeout_seconds': self.timeout,
        }


def replay(model: Model, sequence: list[str]) -> State:
    state = model.initial()
    for decision_id in sequence:
        state = model.step(state, model.index[decision_id])
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--json-output', default=DEFAULT_REPORT.as_posix())
    parser.add_argument('--fixtures-output', default=DEFAULT_FIXTURES.as_posix())
    parser.add_argument('--differential-samples', type=int, default=300)
    parser.add_argument('--state-limit', type=int, default=1_000_000)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    profile = load(repo / PROFILE)
    facility = load(repo / FACILITY)
    model = Model(profile, facility)
    bounds = profile['assurance']['bounded_exploration']
    max_depth = int(bounds['max_decision_depth'])
    max_waits = int(bounds['max_repeatable_waits'])

    start = model.initial()
    queue: deque[tuple[State, int]] = deque([(start, 0)])
    visited: set[State] = {start}
    transitions = 0
    dead_ends: list[dict[str, Any]] = []
    limit_reached = False

    while queue:
        state, depth = queue.popleft()
        if state.terminal != ACTIVE:
            continue
        enabled = model.enabled_indices(state)
        if not enabled:
            dead_ends.append({'state': model.projection(state), 'reason': 'no_enabled_decision'})
            continue
        if depth >= max_depth:
            if model.wait_index not in enabled:
                dead_ends.append({'state': model.projection(state), 'reason': 'frontier_without_timeout_continuation'})
            continue
        for idx in enabled:
            if idx == model.wait_index and state.waits >= max_waits:
                continue
            next_state = model.step(state, idx)
            transitions += 1
            if next_state not in visited:
                visited.add(next_state)
                if len(visited) >= args.state_limit:
                    limit_reached = True
                    queue.clear()
                    break
                queue.append((next_state, depth + 1))
        if limit_reached:
            break

    refs = profile['assurance']['reference_sequences']
    named_sequences = {
        'completed_canonical': list(refs['canonical']),
        'completed_alternate': list(refs['alternate']),
        'failed_discharge': ['receive_handoff','discharge_without_workup'],
        'failed_tourniquet': ['receive_handoff','remove_tourniquet'],
        'timeout': ['receive_handoff'] + ['wait_60'] * max_waits,
    }
    expected = {'completed_canonical':'completed','completed_alternate':'completed','failed_discharge':'failed','failed_tourniquet':'failed','timeout':'timeout'}
    witnesses: dict[str, Any] = {}
    errors: list[str] = []
    for witness_id, sequence in named_sequences.items():
        try:
            state = replay(model, sequence)
            observed = TERMINAL_NAMES[state.terminal]
            if observed != expected[witness_id]:
                errors.append(f'witness terminal mismatch:{witness_id}:{observed}:{expected[witness_id]}')
            witnesses[witness_id] = {'sequence':sequence,'terminal_status':observed,'final_projection':model.projection(state)}
        except Exception as exc:
            errors.append(f'witness failed:{witness_id}:{type(exc).__name__}:{exc}')
    if dead_ends:
        errors.append(f'reachable active dead ends:{len(dead_ends)}')
    if limit_reached:
        errors.append(f'state limit reached:{args.state_limit}')

    # Generate deterministic differential walks after exhaustive exploration so each
    # fixture carries the exact sequence needed by the independent TypeScript runtime.
    selected: list[dict[str, Any]] = []
    seen_fixture_keys: set[str] = set()
    attempt = 0
    while len(selected) < args.differential_samples and attempt < args.differential_samples * 50:
        state = model.initial()
        sequence: list[str] = []
        target_depth = 1 + (attempt % max_depth)
        for step_index in range(target_depth):
            enabled = [idx for idx in model.enabled_indices(state) if not (idx == model.wait_index and state.waits >= max_waits)]
            if not enabled or state.terminal != ACTIVE:
                break
            digest = hashlib.sha256(f'{attempt}:{step_index}:{state}'.encode('utf-8')).digest()
            idx = enabled[int.from_bytes(digest[:8], 'big') % len(enabled)]
            if step_index == target_depth - 1:
                next_state = model.step(state, idx)
                fixture = {
                    'sequence_before': list(sequence),
                    'state_before': model.projection(state),
                    'decision_id': model.ids[idx],
                    'expected_after': model.projection(next_state),
                }
                key = stable_hash(fixture)
                if key not in seen_fixture_keys:
                    seen_fixture_keys.add(key)
                    selected.append(fixture)
                break
            state = model.step(state, idx)
            sequence.append(model.ids[idx])
        attempt += 1
    if len(selected) < args.differential_samples:
        errors.append(f'differential fixture generation incomplete:{len(selected)}:{args.differential_samples}')

    fixtures = {
        'schema_version':'1.0.0',
        'profile_id':profile['profile_id'],
        'abstraction':'timed_automata_region_quotient_v1',
        'sample_count':len(selected),
        'cases':[{'case_id':f'DIFF-{i+1:04d}',**item} for i,item in enumerate(selected)],
    }
    fixture_path = repo / args.fixtures_output
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(json.dumps(fixtures,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')

    report = {
        'schema_version':'1.0.0',
        'status':'PASS' if not errors else 'FAIL',
        'abstraction':'timed_automata_region_quotient_v1',
        'clock_regions':{'diagnostic_age_seconds':'absent | exact 0..179 | saturated >=180','reassessment_age_seconds':'absent | exact 0..179 | saturated >=180'},
        'max_decision_depth':max_depth,
        'max_repeatable_waits':max_waits,
        'state_limit':args.state_limit,
        'state_limit_reached':limit_reached,
        'semantic_states':len(visited),
        'transitions_explored':transitions,
        'reachable_active_dead_ends':len(dead_ends),
        'named_terminal_witnesses':witnesses,
        'differential_fixture_count':len(selected),
        'differential_fixture_sha256':hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        'soundness_scope':'The quotient preserves all executable comparisons against the 180-second diagnostic and information-staleness thresholds while discarding history-only absolute completion timestamps after those thresholds are crossed.',
        'independence_note':'The Python region model reconstructs decision and facility prerequisites, time-based events, diagnostic resources, results, timeout, and terminal behavior from JSON without importing the TypeScript runtime. A separate TypeScript differential checker must replay the committed fixtures.',
        'dead_end_examples':dead_ends[:10],
        'errors':sorted(set(errors)),
    }
    output=repo/args.json_output
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if not errors else 1

if __name__=='__main__':
    raise SystemExit(main())
