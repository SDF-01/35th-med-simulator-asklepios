import { performance } from 'node:perf_hooks';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { facilityArrivalContext } from '../src/facility-arrival/context';
import { applyFacilityCommand, createFacilitySession, evaluateFacilityAction } from '../src/facility-arrival/engine';
import { FACILITY_DECISION_ALTERNATE_SEQUENCE } from '../src/facility-decision/fixtures';
import type { FacilitySession } from '../src/facility-arrival/types';

interface TimingPolicy {
  clock_domains: {
    software_response_time: {
      warmup_iterations: number;
      measured_iterations: number;
      budgets_ms: { p50: number; p95: number; p99: number };
    };
  };
}

function arg(name: string, fallback: string): string {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function percentile(sorted: readonly number[], fraction: number): number {
  if (sorted.length === 0) return Number.POSITIVE_INFINITY;
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * fraction) - 1));
  return sorted[index] ?? Number.POSITIVE_INFINITY;
}

function runSequence(sequence: readonly string[], prefix: string): FacilitySession {
  let session = createFacilitySession(facilityArrivalContext);
  sequence.forEach((actionId, index) => {
    session = applyFacilityCommand(session, {
      command_id: `${prefix}-${String(index + 1).padStart(2, '0')}-${actionId}`,
      action_id: actionId,
      expected_revision: session.final_state.revision,
    }, facilityArrivalContext).session;
  });
  return session;
}

function eventEvidence(session: FacilitySession) {
  const eventIndex = session.transitions.findIndex((transition) => transition.event_id === 'second_casualty_inbound');
  const transitions = session.transitions.filter((transition) => transition.event_id === 'second_casualty_inbound');
  const transition = transitions[0];
  const precedingLearnerAction = eventIndex > 0
    ? [...session.transitions.slice(0, eventIndex)].reverse().find((candidate) => candidate.kind === 'learner_action')
    : undefined;
  return {
    event_count: transitions.length,
    completed_at_seconds: transition?.completed_at_seconds ?? null,
    triggering_action_id: transition?.action_id ?? null,
    preceding_action_id: precedingLearnerAction?.action_id ?? null,
    early_fire: Boolean(transition && transition.completed_at_seconds < 240),
    fired_system_events_count: session.final_state.fired_system_events.filter((event) => event === 'second_casualty_inbound').length,
  };
}

function main(): number {
  const repo = resolve(arg('--repo', '.'));
  const output = resolve(repo, arg('--json-output', 'reports/simulation-timing-runtime.json'));
  const policy = JSON.parse(readFileSync(resolve(repo, 'config/release/SIMULATION_TIMING_POLICY.json'), 'utf8')) as TimingPolicy;
  const errors: string[] = [];

  const canonical = runSequence(facilityArrivalContext.spec.canonical_command_sequence, 'timing-canonical');
  const alternate = runSequence(FACILITY_DECISION_ALTERNATE_SEQUENCE, 'timing-alternate');
  const canonicalEvent = eventEvidence(canonical);
  const alternateEvent = eventEvidence(alternate);

  if (canonicalEvent.event_count !== 1 || canonicalEvent.fired_system_events_count !== 1) errors.push('canonical clock event did not fire exactly once');
  if (alternateEvent.event_count !== 1 || alternateEvent.fired_system_events_count !== 1) errors.push('alternate clock event did not fire exactly once');
  if (canonicalEvent.early_fire || alternateEvent.early_fire) errors.push('clock event fired early');
  const actionIdentityIndependent = (
    canonicalEvent.triggering_action_id === null
    && alternateEvent.triggering_action_id === null
    && canonicalEvent.preceding_action_id !== null
    && alternateEvent.preceding_action_id !== null
    && canonicalEvent.preceding_action_id !== alternateEvent.preceding_action_id
  );
  if (!actionIdentityIndependent) errors.push('clock event remained coupled to one action identity');
  if (canonicalEvent.completed_at_seconds !== alternateEvent.completed_at_seconds) {
    errors.push('clock event time differed across valid action orderings');
  }

  const benchmark = policy.clock_domains.software_response_time;
  const initial = createFacilitySession(facilityArrivalContext);
  const sample = () => {
    const started = performance.now();
    const trace = evaluateFacilityAction(initial, {
      command_id: 'timing-benchmark',
      action_id: 'receive_handoff',
      expected_revision: initial.final_state.revision,
    }, facilityArrivalContext);
    const elapsed = performance.now() - started;
    if (!trace.enabled) throw new Error('benchmark action unexpectedly disabled');
    return elapsed;
  };
  for (let index = 0; index < benchmark.warmup_iterations; index += 1) sample();
  const measurements: number[] = [];
  for (let index = 0; index < benchmark.measured_iterations; index += 1) measurements.push(sample());
  measurements.sort((left, right) => left - right);
  const response = {
    iterations: measurements.length,
    p50_ms: percentile(measurements, 0.50),
    p95_ms: percentile(measurements, 0.95),
    p99_ms: percentile(measurements, 0.99),
    max_ms: measurements.at(-1) ?? null,
    budgets_ms: benchmark.budgets_ms,
  };
  if (response.p50_ms > benchmark.budgets_ms.p50) errors.push('p50 engineering response budget exceeded');
  if (response.p95_ms > benchmark.budgets_ms.p95) errors.push('p95 engineering response budget exceeded');
  if (response.p99_ms > benchmark.budgets_ms.p99) errors.push('p99 engineering response budget exceeded');

  const classification = errors.length === 0 ? 'PASS' : 'FAIL';
  const report = {
    schema_version: '1.0.0',
    classification,
    status: classification,
    clock_domain: 'simulation_logical_clock',
    clinical_timing_calibrated: false,
    canonical: canonicalEvent,
    alternate: alternateEvent,
    action_identity_independent: actionIdentityIndependent,
    response_time: response,
    errors,
  };
  mkdirSync(dirname(output), { recursive: true });
  writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify(report, null, 2));
  return classification === 'PASS' ? 0 : 3;
}

process.exitCode = main();
