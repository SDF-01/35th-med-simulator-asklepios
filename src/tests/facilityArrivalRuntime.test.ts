import test from 'node:test';
import assert from 'node:assert/strict';
import { facilityArrivalContext } from '../facility-arrival/context';
import {
  applyFacilityCommand,
  buildFacilityClaimLedger,
  createFacilitySession,
  evaluateFacilityAction,
  facilityCommandId,
  runCanonicalFacilitySession,
  validateFacilitySession,
} from '../facility-arrival/engine';
import { verifyFacilitySessionIndependent } from '../facility-arrival-checker/verify';
import type { FacilitySession } from '../facility-arrival/types';

const context = facilityArrivalContext;

function apply(session: FacilitySession, actionId: string, ordinal: number): FacilitySession {
  return applyFacilityCommand(session, {
    command_id: facilityCommandId(actionId, ordinal),
    action_id: actionId,
    expected_revision: session.final_state.revision,
  }, context).session;
}

test('canonical facility run completes with a bound 100 percent source score', () => {
  const session = runCanonicalFacilitySession(context);
  assert.equal(session.final_state.terminal_status, 'completed');
  assert.equal(session.normalized_score_bps, 10_000);
  assert.equal(validateFacilitySession(session, context).length, 0);
  assert.equal(verifyFacilitySessionIndependent(session, context, buildFacilityClaimLedger(context)).length, 0);
  assert.equal(session.transitions.at(-1)?.action_id, 'complete_handoff');
  assert.ok(session.final_state.revealed_hidden_findings.length > 0);
});

test('hidden source findings remain hidden until diagnostics-ready event', () => {
  let session = createFacilitySession(context);
  const path = ['receive_handoff', 'primary_assessment', 'order_imaging', 'order_labs'];
  path.forEach((action, index) => { session = apply(session, action, index + 1); });
  assert.deepEqual(session.final_state.revealed_hidden_findings, []);
  session = apply(session, 'wait_for_diagnostics', 5);
  assert.ok(session.final_state.fired_system_events.includes('diagnostics_ready'));
  assert.deepEqual(
    session.final_state.revealed_hidden_findings,
    context.scenario.patients.flatMap((patient) => patient.hidden_findings).sort(),
  );
});

test('source-bound timeout is an explicit final system transition', () => {
  let session = createFacilitySession(context);
  let ordinal = 1;
  while (session.final_state.terminal_status === 'active' && ordinal < 30) {
    session = apply(session, 'wait_60', ordinal);
    ordinal += 1;
  }
  assert.equal(session.final_state.terminal_status, 'timeout');
  assert.equal(session.final_state.elapsed_seconds, context.spec.parameters.timeout_seconds.value);
  assert.equal(session.transitions.at(-1)?.kind, 'system_event');
  assert.equal(session.transitions.at(-1)?.event_id, 'timeout_reached');
  assert.equal(validateFacilitySession(session, context).length, 0);
});

test('unsafe source actions fail closed and cannot produce a passing score', () => {
  for (const unsafe of ['discharge_without_workup', 'remove_tourniquet']) {
    let session = createFacilitySession(context);
    session = apply(session, 'receive_handoff', 1);
    session = apply(session, unsafe, 2);
    assert.equal(session.final_state.terminal_status, 'failed');
    assert.ok(session.normalized_score_bps >= 0);
    assert.ok(session.normalized_score_bps < context.spec.parameters.pass_threshold_bps.value);
    assert.equal(validateFacilitySession(session, context).length, 0);
  }
});

test('duplicate command is idempotent but command-ID reuse with changed content is rejected', () => {
  const initial = createFacilitySession(context);
  const command = {
    command_id: 'stable-command-001',
    action_id: 'receive_handoff',
    expected_revision: initial.final_state.revision,
  };
  const first = applyFacilityCommand(initial, command, context);
  const repeated = applyFacilityCommand(first.session, command, context);
  assert.equal(repeated.idempotent, true);
  assert.deepEqual(repeated.session, first.session);
  assert.throws(() => applyFacilityCommand(first.session, { ...command, action_id: 'wait_60' }, context));
});

test('nonrepeatable action cannot be completed twice even with a fresh command ID', () => {
  let session = createFacilitySession(context);
  session = apply(session, 'receive_handoff', 1);
  const trace = evaluateFacilityAction(session, {
    command_id: 'new-command',
    action_id: 'receive_handoff',
    expected_revision: session.final_state.revision,
  }, context);
  assert.equal(trace.enabled, false);
  assert.ok(trace.rejection_reasons.includes('action_not_already_completed_or_repeatable'));
});
