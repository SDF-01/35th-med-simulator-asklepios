import test from 'node:test';
import assert from 'node:assert/strict';
import { facilityArrivalContext } from '../facility-arrival/context';
import {
  applyFacilityCommand,
  buildFacilityClaimLedger,
  createFacilitySession,
  facilityCommandId,
  runCanonicalFacilitySession,
} from '../facility-arrival/engine';
import { verifyFacilitySessionIndependent } from '../facility-arrival-checker/verify';
import type { FacilitySession } from '../facility-arrival/types';

const context = facilityArrivalContext;

function run(sequence: readonly string[]): FacilitySession {
  let session = createFacilitySession(context);
  sequence.forEach((action, index) => {
    session = applyFacilityCommand(session, {
      command_id: facilityCommandId(action, index + 1),
      action_id: action,
      expected_revision: session.final_state.revision,
    }, context).session;
  });
  return session;
}

test('independent diagnostic-order permutations converge after diagnostics-ready', () => {
  const prefix = ['receive_handoff', 'primary_assessment'];
  const first = run([...prefix, 'order_imaging', 'order_labs', 'wait_for_diagnostics']);
  const second = run([...prefix, 'order_labs', 'order_imaging', 'wait_for_diagnostics']);
  assert.ok(first.final_state.fired_system_events.includes('diagnostics_ready'));
  assert.ok(second.final_state.fired_system_events.includes('diagnostics_ready'));
  assert.deepEqual(first.final_state.revealed_hidden_findings, second.final_state.revealed_hidden_findings);
  assert.equal(first.final_state.elapsed_seconds, second.final_state.elapsed_seconds);
});

test('WIT observations never alter clinical score', () => {
  const session = runCanonicalFacilitySession(context);
  let prior = 0;
  for (const transition of session.transitions) {
    if (transition.kind === 'system_event' || transition.origin === 'operational_workflow') {
      assert.equal(transition.score_delta, 0);
    }
    assert.equal(transition.wit_observation.clinical_directive, null);
    assert.equal(transition.wit_observation.process_only, true);
    prior = transition.state_after.score_points;
  }
  assert.equal(prior, session.final_state.score_points);
});

test('different command identifiers preserve the same final operational state', () => {
  const sequence = context.spec.canonical_command_sequence;
  let first = createFacilitySession(context);
  let second = createFacilitySession(context);
  sequence.forEach((action, index) => {
    first = applyFacilityCommand(first, { command_id: `a-${index}`, action_id: action, expected_revision: first.final_state.revision }, context).session;
    second = applyFacilityCommand(second, { command_id: `b-${index}`, action_id: action, expected_revision: second.final_state.revision }, context).session;
  });
  assert.deepEqual(first.final_state, second.final_state);
  assert.equal(first.normalized_score_bps, second.normalized_score_bps);
});

test('globally rehashed transition semantic forgery remains rejected by independent checker', () => {
  const session = structuredClone(runCanonicalFacilitySession(context));
  session.transitions[1]!.label = 'Forged handoff semantics';
  const errors = verifyFacilitySessionIndependent(session, context, buildFacilityClaimLedger(context));
  assert.ok(errors.length > 0);
});
