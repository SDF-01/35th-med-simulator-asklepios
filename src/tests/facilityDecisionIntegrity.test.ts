import test from 'node:test';
import assert from 'node:assert/strict';
import { facilityArrivalContext } from '../facility-arrival/context';
import {
  applyFacilityDecisionSubmission,
  assertLearnerViewHasNoAnswerLeakage,
  buildFacilityDecisionView,
  createFacilityDecisionSession,
  decisionSessionIntegrityErrors,
  evaluateFacilityDecision,
  facilityDecisionContext,
  facilityDecisionProfile,
  validateFacilityDecisionSubmission,
} from '../facility-decision/runtime';
import {
  FACILITY_DECISION_ALTERNATE_SEQUENCE,
  FACILITY_DECISION_CANONICAL_SEQUENCE,
  facilityDecisionSubmission,
  facilityDecisionValues,
} from '../facility-decision/fixtures';
import { verifyFacilityDecisionSession } from '../facility-decision-checker/verify';
import { sha256Canonical } from '../scenario-core/hash';
import type { FacilityDecisionIntegritySession, FacilityDecisionSubmission } from '../facility-decision/types';

const context = facilityDecisionContext(facilityArrivalContext);
const profile = facilityDecisionProfile();

function run(sequence: readonly string[], mode: 'learner_assessment' | 'stakeholder_demo' = 'learner_assessment') {
  let session = createFacilityDecisionSession(facilityArrivalContext, mode, profile);
  sequence.forEach((decisionId, index) => {
    session = applyFacilityDecisionSubmission(
      session,
      facilityDecisionSubmission(decisionId, session.revision, index + 1),
      context,
    );
  });
  return session;
}

function submission(decisionId: string, revision: number, values?: Record<string, string | boolean | string[]>): FacilityDecisionSubmission {
  return {
    submission_id: `test-${decisionId}-${revision}`,
    decision_id: decisionId,
    expected_revision: revision,
    values: values ?? facilityDecisionValues(decisionId),
  };
}

function assertHealthy(session: FacilityDecisionIntegritySession): void {
  assert.deepEqual(decisionSessionIntegrityErrors(session, context), []);
  assert.deepEqual(verifyFacilityDecisionSession(session, profile), []);
}

test('every critical and important source objective has exactly one decision contract', () => {
  const expected = facilityArrivalContext.scenario.expected_actions.critical
    .concat(facilityArrivalContext.scenario.expected_actions.important)
    .map((action) => action.id)
    .sort();
  const bound = profile.decisions
    .filter((decision) => decision.source_action_id && expected.includes(decision.source_action_id))
    .map((decision) => decision.source_action_id as string)
    .sort();
  assert.deepEqual(bound, expected);
  assert.equal(new Set(bound).size, bound.length);
});

test('learner assessment view contains no score, source, WIT, provenance, or demo answer leakage', () => {
  const session = createFacilityDecisionSession(facilityArrivalContext, 'learner_assessment', profile);
  const view = buildFacilityDecisionView(session, context);
  assert.deepEqual(assertLearnerViewHasNoAnswerLeakage(view), []);
  assert.equal(view.instructor, undefined);
  assert.equal(view.demo, undefined);
  assert.equal(view.completed_decision_count, 0);
  assert.ok(view.actions.every((action) => action.source_action_id === undefined));
  assert.ok(view.actions.every((action) => action.source_origin === undefined));
  assert.ok(view.actions.every((action) => !/unsafe|wrong|correct/i.test(action.label)));
});

test('concrete medication, dose, route, procedure, and tourniquet activation fields fail closed', () => {
  for (const [decisionId, field] of [
    ['pain_management', 'medication'],
    ['pain_management', 'dose'],
    ['pain_management', 'route'],
    ['pain_management', 'procedure'],
    ['remove_tourniquet', 'remove_now'],
  ] as const) {
    const values = { ...facilityDecisionValues(decisionId), [field]: field === 'remove_now' ? true : 'forged' };
    const result = validateFacilityDecisionSubmission(submission(decisionId, 0, values), profile);
    assert.equal(result.valid, false, `${decisionId}:${field}`);
    assert.ok(result.errors.some((error) => error.includes('forbidden') || error.includes('unknown_field')));
  }
});

test('diagnostic results remain unavailable until exact matching orders and diagnostics event exist', () => {
  let session = createFacilityDecisionSession(facilityArrivalContext, 'learner_assessment', profile);
  for (const decisionId of ['receive_handoff', 'primary_assessment', 'order_imaging']) {
    session = applyFacilityDecisionSubmission(session, submission(decisionId, session.revision), context);
  }
  assert.equal(session.orders.some((order) => order.order_code === 'CHEST_IMAGING'), true);
  assert.equal(session.orders.some((order) => order.order_code === 'LACTATE'), false);
  assert.deepEqual(session.results, []);
  assert.equal(evaluateFacilityDecision(session, 'review_diagnostics', context).enabled, false);

  session = applyFacilityDecisionSubmission(session, submission('order_labs', session.revision), context);
  assert.deepEqual(session.results, []);
  session = applyFacilityDecisionSubmission(session, submission('wait_for_diagnostics', session.revision), context);
  assert.deepEqual(session.results.map((result) => result.result_id).sort(), ['CHEST_IMAGING_REPORT', 'LACTATE_RESULT']);
  assert.ok(session.results.every((result) => session.orders.some((order) => order.order_id === result.order_id && order.order_code === result.order_code)));
});

test('world surge event is clock-driven rather than action-triggered in the decision layer', () => {
  let imagingFirst = createFacilityDecisionSession(facilityArrivalContext, 'learner_assessment', profile);
  for (const id of ['receive_handoff', 'primary_assessment', 'order_imaging']) {
    imagingFirst = applyFacilityDecisionSubmission(imagingFirst, submission(id, imagingFirst.revision), context);
  }
  assert.equal(imagingFirst.visible_world_events.some((event) => event.event_id === 'second_casualty_inbound'), false);

  let labsFirst = createFacilityDecisionSession(facilityArrivalContext, 'learner_assessment', profile);
  for (const id of ['receive_handoff', 'primary_assessment', 'order_labs']) {
    labsFirst = applyFacilityDecisionSubmission(labsFirst, submission(id, labsFirst.revision), context);
  }
  assert.equal(labsFirst.visible_world_events.some((event) => event.event_id === 'second_casualty_inbound'), false);

  imagingFirst = applyFacilityDecisionSubmission(imagingFirst, submission('monitor_vitals', imagingFirst.revision), context);
  imagingFirst = applyFacilityDecisionSubmission(imagingFirst, submission('differential', imagingFirst.revision), context);
  assert.ok(imagingFirst.facility_session.final_state.elapsed_seconds >= 240);
  assert.equal(imagingFirst.visible_world_events.some((event) => event.event_id === 'second_casualty_inbound'), true);
});

test('closed-loop transfer cannot occur without receiver acknowledgment, questions, and sender confirmation', () => {
  const prefix = FACILITY_DECISION_CANONICAL_SEQUENCE.filter((id) => id !== 'complete_handoff');
  let session = run(prefix);
  const values = facilityDecisionValues('complete_handoff');
  values.receiver_acknowledged = false;
  const result = validateFacilityDecisionSubmission(submission('complete_handoff', session.revision, values), profile);
  assert.equal(result.valid, false);
  assert.ok(result.errors.includes('field:receiver_acknowledged:must_equal'));
  assert.equal(session.handoff.responsibility_transferred_at_seconds, null);
});

test('learner progress uses the role-safe projection rather than raw decision records', () => {
  let session = createFacilityDecisionSession(facilityArrivalContext, 'learner_assessment', profile);
  assert.equal(buildFacilityDecisionView(session, context).completed_decision_count, 0);
  session = applyFacilityDecisionSubmission(session, submission('receive_handoff', session.revision), context);
  const view = buildFacilityDecisionView(session, context);
  assert.equal(view.completed_decision_count, 1);
  assert.equal('decision_records' in view, false);
  assert.equal('submissions' in view, false);
});

test('instructor timeline is projected deliberately and remains absent from learner views', () => {
  let learner = createFacilityDecisionSession(facilityArrivalContext, 'learner_assessment', profile);
  learner = applyFacilityDecisionSubmission(learner, submission('receive_handoff', learner.revision), context);
  const learnerView = buildFacilityDecisionView(learner, context);
  assert.equal(learnerView.instructor, undefined);
  assert.equal('decision_timeline' in learnerView, false);

  let instructor = createFacilityDecisionSession(facilityArrivalContext, 'instructor', profile);
  instructor = applyFacilityDecisionSubmission(instructor, submission('receive_handoff', instructor.revision), context);
  const instructorView = buildFacilityDecisionView(instructor, context);
  assert.equal(instructorView.instructor?.decision_timeline.length, 1);
  assert.deepEqual(instructorView.instructor?.decision_timeline[0], {
    record_id: instructor.decision_records[0].record_id,
    sequence: 1,
    decision_id: 'receive_handoff',
    started_at_seconds: instructor.decision_records[0].started_at_seconds,
    completed_at_seconds: instructor.decision_records[0].completed_at_seconds,
  });
  assert.equal('payload_sha256' in (instructorView.instructor?.decision_timeline[0] ?? {}), false);
  assert.equal('record_sha256' in (instructorView.instructor?.decision_timeline[0] ?? {}), false);
});

test('two materially different valid decision orderings complete with the same source-bound objectives', () => {
  const canonical = run(FACILITY_DECISION_CANONICAL_SEQUENCE);
  const alternate = run(FACILITY_DECISION_ALTERNATE_SEQUENCE);
  assert.equal(canonical.facility_session.final_state.terminal_status, 'completed');
  assert.equal(alternate.facility_session.final_state.terminal_status, 'completed');
  assert.equal(canonical.facility_session.normalized_score_bps, 10_000);
  assert.equal(alternate.facility_session.normalized_score_bps, 10_000);
  assert.notDeepEqual(canonical.submissions.map((item) => item.decision_id), alternate.submissions.map((item) => item.decision_id));
  assert.deepEqual(canonical.facility_session.final_state.completed_source_action_ids, alternate.facility_session.final_state.completed_source_action_ids);
  assertHealthy(canonical);
  assertHealthy(alternate);
});

test('delay without a new structured reassessment produces an observable information-staleness consequence', () => {
  let session = createFacilityDecisionSession(facilityArrivalContext, 'learner_assessment', profile);
  for (const id of ['receive_handoff', 'primary_assessment']) {
    session = applyFacilityDecisionSubmission(session, submission(id, session.revision), context);
  }
  const before = session.information_state.staleness_seconds;
  for (let index = 0; index < 3; index += 1) {
    session = applyFacilityDecisionSubmission(session, submission('wait_60', session.revision), context);
  }
  assert.ok(session.information_state.staleness_seconds > before);
  assert.equal(session.information_state.staleness_seconds, 180);
  assert.equal(session.information_state.reassessment_due, true);
});

test('high-risk branches use neutral learner language and remain deliberate, rationale-bound choices', () => {
  const view = buildFacilityDecisionView(createFacilityDecisionSession(facilityArrivalContext, 'learner_assessment', profile), context);
  for (const id of ['discharge_without_workup', 'remove_tourniquet']) {
    const action = view.actions.find((candidate) => candidate.decision_id === id);
    if (!action) throw new Error(`Missing learner action: ${id}`);
    assert.equal(action.requires_deliberate_confirmation, true);
    assert.equal('high_risk' in action, false);
    assert.notEqual(action.category, 'high_risk_disposition');
    assert.notEqual(action.category, 'high_risk_treatment_change');
    assert.equal(action.fields.some((field) => 'must_equal' in field || 'required_values' in field), false);
    assert.ok(!/unsafe|wrong|fail/i.test(action.label));
    const bad = facilityDecisionValues(id);
    bad.deliberate_confirmation = false;
    const validation = validateFacilityDecisionSubmission(submission(id, 0, bad), profile);
    assert.equal(validation.valid, false);
    assert.ok(validation.errors.includes('high_risk_confirmation_required'));
  }
});

test('decision root excludes prior root material and every accepted transition remains self-consistent', () => {
  const profile = facilityDecisionProfile();
  const context = facilityDecisionContext(facilityArrivalContext);
  let session = createFacilityDecisionSession(facilityArrivalContext, 'learner_assessment', profile);
  assert.deepEqual(decisionSessionIntegrityErrors(session, context), []);
  session = applyFacilityDecisionSubmission(
    session,
    facilityDecisionSubmission('receive_handoff', session.revision, 1),
    context,
  );
  assert.deepEqual(decisionSessionIntegrityErrors(session, context), []);
  assert.deepEqual(verifyFacilityDecisionSession(session, profile), []);
});

test('a forged incoming decision root is rejected rather than laundered by a later transition', () => {
  const profile = facilityDecisionProfile();
  const context = facilityDecisionContext(facilityArrivalContext);
  const session = createFacilityDecisionSession(facilityArrivalContext, 'learner_assessment', profile);
  const forged = { ...session, decision_root_sha256: '0'.repeat(64) };
  assert.throws(
    () => applyFacilityDecisionSubmission(
      forged,
      facilityDecisionSubmission('receive_handoff', forged.revision, 1),
      context,
    ),
    /Decision session integrity failed before transition: decision root mismatch/,
  );
});

test('availability evaluation is total when diagnostics-dependent duration is not yet resolvable', () => {
  const profile = facilityDecisionProfile();
  const context = facilityDecisionContext(facilityArrivalContext);
  const initial = createFacilityDecisionSession(facilityArrivalContext, 'learner_assessment', profile);

  const initialAvailability = evaluateFacilityDecision(initial, 'wait_for_diagnostics', context);
  assert.equal(initialAvailability.enabled, false);
  assert.ok(initialAvailability.reasons.includes('prerequisite_missing:order_imaging'));
  assert.ok(initialAvailability.reasons.includes('prerequisite_missing:order_labs'));
  assert.equal(initialAvailability.reasons.includes('facility:evaluation_failed_closed'), false);
  assert.doesNotThrow(() => buildFacilityDecisionView(initial, context));

  let imagingOnly = initial;
  for (const decisionId of ['receive_handoff', 'primary_assessment', 'order_imaging']) {
    imagingOnly = applyFacilityDecisionSubmission(
      imagingOnly,
      submission(decisionId, imagingOnly.revision),
      context,
    );
  }
  const partialAvailability = evaluateFacilityDecision(imagingOnly, 'wait_for_diagnostics', context);
  assert.equal(partialAvailability.enabled, false);
  assert.ok(partialAvailability.reasons.includes('prerequisite_missing:order_labs'));
  assert.equal(partialAvailability.reasons.includes('facility:evaluation_failed_closed'), false);
  assert.doesNotThrow(() => buildFacilityDecisionView(imagingOnly, context));

  // A semantically inconsistent but fully rehashed session must fail closed rather
  // than crash rendering. Both implementations must expose the alignment error.
  const forgedWithoutRoot = {
    ...imagingOnly,
    completed_decision_ids: [...imagingOnly.completed_decision_ids, 'order_labs'].sort(),
  };
  const { decision_root_sha256: _oldRoot, ...forgedPayload } = forgedWithoutRoot;
  const forged: FacilityDecisionIntegritySession = {
    ...forgedPayload,
    decision_root_sha256: sha256Canonical(forgedPayload),
  };
  const forgedAvailability = evaluateFacilityDecision(forged, 'wait_for_diagnostics', context);
  assert.equal(forgedAvailability.enabled, false);
  assert.ok(forgedAvailability.reasons.includes('facility:prerequisites_complete'));
  assert.ok(forgedAvailability.reasons.includes('facility:duration_resolvable'));
  assert.equal(forgedAvailability.reasons.includes('facility:evaluation_failed_closed'), false);
  assert.ok(decisionSessionIntegrityErrors(forged, context).includes('decision/facility completion mismatch:order_labs'));
  assert.ok(verifyFacilityDecisionSession(forged, profile).includes('decision/facility completion mismatch:order_labs'));
});
