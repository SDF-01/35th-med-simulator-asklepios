import test from 'node:test';
import assert from 'node:assert/strict';
import { facilityArrivalContext } from '../facility-arrival/context';
import { applyFacilityCommand, createFacilitySession, evaluateFacilityAction } from '../facility-arrival/engine';

const context = facilityArrivalContext;

test('each admission condition independently blocks an otherwise admissible action', () => {
  const initial = createFacilitySession(context);
  const baseline = {
    command_id: 'baseline',
    action_id: 'receive_handoff',
    expected_revision: initial.final_state.revision,
  };
  assert.equal(evaluateFacilityAction(initial, baseline, context).enabled, true);

  const stale = evaluateFacilityAction(initial, { ...baseline, expected_revision: 99 }, context);
  assert.ok(stale.rejection_reasons.includes('revision_matches'));

  const unknown = evaluateFacilityAction(initial, { ...baseline, action_id: 'unknown' }, context);
  assert.ok(unknown.rejection_reasons.includes('action_known'));

  const noEvent = structuredClone(initial);
  noEvent.final_state.fired_system_events = [];
  const missingEvent = evaluateFacilityAction(noEvent, baseline, context);
  assert.ok(missingEvent.rejection_reasons.includes('required_events_complete'));

  const terminal = structuredClone(initial);
  terminal.final_state.terminal_status = 'failed';
  const afterTerminal = evaluateFacilityAction(terminal, baseline, context);
  assert.ok(afterTerminal.rejection_reasons.includes('session_active'));
});

test('completion cannot be admitted before its source and operational requirements', () => {
  const session = createFacilitySession(context);
  const trace = evaluateFacilityAction(session, {
    command_id: 'premature-completion',
    action_id: 'complete_handoff',
    expected_revision: session.final_state.revision,
  }, context);
  assert.equal(trace.enabled, false);
  assert.ok(trace.rejection_reasons.includes('prerequisites_complete'));
  assert.ok(trace.rejection_reasons.includes('required_events_complete'));
  assert.ok(trace.rejection_reasons.includes('completion_requirements_met'));
});

test('post-terminal command is rejected by the reducer, not only hidden by the UI', () => {
  let session = createFacilitySession(context);
  session = applyFacilityCommand(session, {
    command_id: 'receive', action_id: 'receive_handoff', expected_revision: session.final_state.revision,
  }, context).session;
  session = applyFacilityCommand(session, {
    command_id: 'unsafe', action_id: 'discharge_without_workup', expected_revision: session.final_state.revision,
  }, context).session;
  assert.throws(() => applyFacilityCommand(session, {
    command_id: 'after-terminal', action_id: 'wait_60', expected_revision: session.final_state.revision,
  }, context));
});

test('dynamic-duration availability is total before and during diagnostic ordering', () => {
  const initial = createFacilitySession(context);
  const preview = (session: ReturnType<typeof createFacilitySession>, commandId: string) => evaluateFacilityAction(session, {
    command_id: commandId,
    action_id: 'wait_for_diagnostics',
    expected_revision: session.final_state.revision,
  }, context);

  const beforeOrders = preview(initial, 'preview-before-orders');
  assert.equal(beforeOrders.enabled, false);
  assert.ok(beforeOrders.rejection_reasons.includes('prerequisites_complete'));
  assert.ok(beforeOrders.rejection_reasons.includes('duration_resolvable'));

  let imagingOnly = initial;
  for (const actionId of ['receive_handoff', 'primary_assessment', 'order_imaging']) {
    imagingOnly = applyFacilityCommand(imagingOnly, {
      command_id: `setup-${actionId}`,
      action_id: actionId,
      expected_revision: imagingOnly.final_state.revision,
    }, context).session;
  }
  const afterOneOrder = preview(imagingOnly, 'preview-after-imaging');
  assert.equal(afterOneOrder.enabled, false);
  assert.ok(afterOneOrder.rejection_reasons.includes('prerequisites_complete'));
  assert.ok(afterOneOrder.rejection_reasons.includes('duration_resolvable'));

  let bothOrders = applyFacilityCommand(imagingOnly, {
    command_id: 'setup-order-labs',
    action_id: 'order_labs',
    expected_revision: imagingOnly.final_state.revision,
  }, context).session;
  const ready = preview(bothOrders, 'preview-ready');
  assert.equal(ready.enabled, true);
  assert.equal(ready.rejection_reasons.includes('duration_resolvable'), false);

  const inconsistent = structuredClone(bothOrders);
  delete inconsistent.final_state.action_completed_at.order_labs;
  const failClosed = preview(inconsistent, 'preview-inconsistent');
  assert.equal(failClosed.enabled, false);
  assert.ok(failClosed.rejection_reasons.includes('duration_resolvable'));
  assert.throws(
    () => applyFacilityCommand(inconsistent, {
      command_id: 'execute-inconsistent',
      action_id: 'wait_for_diagnostics',
      expected_revision: inconsistent.final_state.revision,
    }, context),
    /duration_resolvable/,
  );
});
