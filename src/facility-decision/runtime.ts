import { sha256Canonical } from '../scenario-core/hash';
import {
  applyFacilityCommand,
  createFacilitySession,
  evaluateFacilityAction,
  facilityCommandId,
} from '../facility-arrival/engine';
import type { FacilitySourceContext } from '../facility-arrival/types';
import { FACILITY_DECISION_PROFILE } from './contracts.generated';
import type {
  FacilityDecisionActionView,
  FacilityDecisionContext,
  FacilityDecisionContract,
  FacilityDecisionDimensionRecord,
  FacilityDecisionHandoffState,
  FacilityDecisionIntegritySession,
  FacilityDecisionLearnerView,
  FacilityDecisionOrder,
  FacilityDecisionProfile,
  FacilityDecisionPublicCategory,
  FacilityDecisionRecord,
  FacilityDecisionResourceState,
  FacilityDecisionResult,
  FacilityDecisionSubmission,
  FacilityDecisionUiMode,
  FacilityDecisionValidationResult,
  FacilityDecisionValue,
  FacilityDecisionWorldEvent,
  FacilityTreatmentPolicy,
} from './types';

const HIGH_RISK_DECISIONS = new Set(['discharge_without_workup', 'remove_tourniquet']);
const REASSESSMENT_DECISIONS = new Set(['primary_assessment', 'monitor_vitals', 'wait_for_diagnostics', 'review_diagnostics']);
const RESTRICTED_LEARNER_TOKENS = [
  'score_points',
  'normalized_source_score_bps',
  'source_action_id',
  'source_origin',
  'source_binding',
  'facility_certificate',
  'wit_observations',
  'autoplay_available',
  'completed_replay_available',
  'branch_controls',
  'high_risk',
  'must_equal',
  'required_values',
] as const;

function uniqueSorted(values: readonly string[]): string[] {
  return [...new Set(values)].sort();
}

function contractMap(profile: FacilityDecisionProfile): Map<string, FacilityDecisionContract> {
  return new Map(profile.decisions.map((contract) => [contract.decision_id, contract]));
}

function treatmentPolicyMap(profile: FacilityDecisionProfile): Map<string, FacilityTreatmentPolicy> {
  return new Map(profile.treatment_policies.map((policy) => [policy.treatment_id, policy]));
}

function diagnosticSpecMap(profile: FacilityDecisionProfile) {
  return new Map(profile.diagnostic_catalog.map((diagnostic) => [diagnostic.order_code, diagnostic]));
}

function resourceSpecMap(profile: FacilityDecisionProfile) {
  return new Map(profile.operational_model.resources.map((resource) => [resource.resource_id, resource]));
}

function normalizedValue(value: FacilityDecisionValue): FacilityDecisionValue {
  if (typeof value === 'string') return value.trim();
  if (Array.isArray(value)) return uniqueSorted(value.map((item) => item.trim()).filter(Boolean));
  return value;
}

function normalizeSubmission(submission: FacilityDecisionSubmission): FacilityDecisionSubmission {
  return {
    ...submission,
    values: Object.fromEntries(
      Object.entries(submission.values)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, value]) => [key, normalizedValue(value)]),
    ),
  };
}

function validateFieldValue(
  field: FacilityDecisionContract['fields'][number],
  value: FacilityDecisionValue | undefined,
): string[] {
  const errors: string[] = [];
  if (value === undefined) {
    if (field.required) errors.push('missing');
    return errors;
  }
  if (field.type === 'boolean') {
    if (typeof value !== 'boolean') errors.push('type');
  } else if (field.type === 'text' || field.type === 'choice') {
    if (typeof value !== 'string') errors.push('type');
    else {
      if (field.min_length !== undefined && value.trim().length < field.min_length) errors.push('min_length');
      if (field.allowed_values && !field.allowed_values.includes(value)) errors.push('allowed_values');
    }
  } else if (field.type === 'multi_choice' || field.type === 'list') {
    if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) errors.push('type');
    else {
      if (field.min_items !== undefined && uniqueSorted(value).length < field.min_items) errors.push('min_items');
      if (field.allowed_values && value.some((item) => !field.allowed_values?.includes(item))) errors.push('allowed_values');
      if (field.required_values && field.required_values.some((item) => !value.includes(item))) errors.push('required_values');
    }
  }
  if (field.must_equal !== undefined && value !== field.must_equal) errors.push('must_equal');
  return errors;
}

export function validateFacilityDecisionSubmission(
  submission: FacilityDecisionSubmission,
  profile: FacilityDecisionProfile = FACILITY_DECISION_PROFILE,
): FacilityDecisionValidationResult {
  const contract = contractMap(profile).get(submission.decision_id);
  const errors: string[] = [];
  const missingFields: string[] = [];
  const forbiddenFields: string[] = [];
  if (!contract) {
    return {
      decision_id: submission.decision_id,
      valid: false,
      errors: ['decision_unknown'],
      missing_fields: [],
      forbidden_fields: [],
    };
  }
  const allowed = new Set(contract.fields.map((field) => field.field_id));
  for (const key of Object.keys(submission.values)) {
    if (!allowed.has(key)) errors.push(`unknown_field:${key}`);
  }
  for (const field of contract.fields) {
    const fieldErrors = validateFieldValue(field, submission.values[field.field_id]);
    if (fieldErrors.includes('missing')) missingFields.push(field.field_id);
    for (const reason of fieldErrors) errors.push(`field:${field.field_id}:${reason}`);
  }
  if (contract.treatment_policy_id) {
    const policy = treatmentPolicyMap(profile).get(contract.treatment_policy_id);
    if (!policy) errors.push('treatment_policy_unknown');
    else {
      for (const forbidden of policy.forbidden_submission_keys) {
        if (Object.prototype.hasOwnProperty.call(submission.values, forbidden)) {
          forbiddenFields.push(forbidden);
          errors.push(`concrete_treatment_field_forbidden:${forbidden}`);
        }
      }
      if (policy.concrete_treatment_allowed !== false) errors.push('concrete_treatment_activation_forbidden');
    }
  }
  if (contract.high_risk) {
    if (submission.values.deliberate_confirmation !== true) errors.push('high_risk_confirmation_required');
    const rationale = submission.values.rationale;
    if (typeof rationale !== 'string' || rationale.trim().length < 15) errors.push('high_risk_rationale_required');
  }
  return {
    decision_id: submission.decision_id,
    valid: errors.length === 0,
    errors: uniqueSorted(errors),
    missing_fields: uniqueSorted(missingFields),
    forbidden_fields: uniqueSorted(forbiddenFields),
  };
}

function synchronizeWorldEvents(
  session: FacilityDecisionIntegritySession,
  profile: FacilityDecisionProfile,
): FacilityDecisionWorldEvent[] {
  const current = new Map(session.visible_world_events.map((event) => [event.event_id, event]));
  for (const spec of profile.operational_model.world_events) {
    if (session.facility_session.final_state.elapsed_seconds >= spec.at_elapsed_seconds && !current.has(spec.event_id)) {
      current.set(spec.event_id, {
        event_id: spec.event_id,
        visible_at_seconds: spec.at_elapsed_seconds,
        observed_at_seconds: session.facility_session.final_state.elapsed_seconds,
        calibration_status: spec.calibration_status,
        note: spec.note,
      });
    }
  }
  return [...current.values()].sort((left, right) => left.visible_at_seconds - right.visible_at_seconds || left.event_id.localeCompare(right.event_id));
}

function scheduleOrders(
  orders: FacilityDecisionOrder[],
  profile: FacilityDecisionProfile,
  elapsedSeconds: number,
): FacilityDecisionOrder[] {
  const resources = resourceSpecMap(profile);
  const byResource = new Map<string, FacilityDecisionOrder[]>();
  for (const order of orders) {
    const list = byResource.get(order.resource_id) ?? [];
    list.push(order);
    byResource.set(order.resource_id, list);
  }
  const scheduled: FacilityDecisionOrder[] = [];
  for (const [resourceId, resourceOrders] of [...byResource.entries()].sort(([left], [right]) => left.localeCompare(right))) {
    const resource = resources.get(resourceId);
    if (!resource) throw new Error(`Unknown decision resource: ${resourceId}`);
    const slots = Array.from({ length: resource.capacity }, () => 0);
    for (const order of [...resourceOrders].sort((left, right) => left.placed_at_seconds - right.placed_at_seconds || left.order_id.localeCompare(right.order_id))) {
      let slotIndex = 0;
      for (let index = 1; index < slots.length; index += 1) {
        if (slots[index] < slots[slotIndex]) slotIndex = index;
      }
      const startedAt = Math.max(order.placed_at_seconds, slots[slotIndex]);
      const dueAt = startedAt + resource.service_duration_seconds;
      slots[slotIndex] = dueAt;
      const completedAt = elapsedSeconds >= dueAt ? dueAt : null;
      const status = elapsedSeconds < startedAt
        ? 'queued' as const
        : elapsedSeconds < dueAt
          ? 'in_progress' as const
          : 'completed_pending_release' as const;
      scheduled.push({
        ...order,
        queued_at_seconds: order.placed_at_seconds,
        started_at_seconds: startedAt,
        due_at_seconds: dueAt,
        completed_at_seconds: completedAt,
        status,
      });
    }
  }
  return scheduled.sort((left, right) => left.order_id.localeCompare(right.order_id));
}

function synchronizeResults(
  session: FacilityDecisionIntegritySession,
  profile: FacilityDecisionProfile,
): FacilityDecisionResult[] {
  if (!session.facility_session.final_state.fired_system_events.includes('diagnostics_ready')) return session.results;
  const existing = new Map(session.results.map((result) => [result.result_id, result]));
  for (const diagnostic of profile.diagnostic_catalog) {
    const order = session.orders.find((candidate) => candidate.order_code === diagnostic.order_code);
    if (!order || order.completed_at_seconds === null || existing.has(diagnostic.result_id)) continue;
    existing.set(diagnostic.result_id, {
      result_id: diagnostic.result_id,
      order_id: order.order_id,
      order_code: diagnostic.order_code,
      available_at_seconds: Math.max(order.completed_at_seconds, session.facility_session.final_state.elapsed_seconds),
      learner_result: diagnostic.learner_result,
      source_pointer: diagnostic.source_pointer,
      granularity: diagnostic.result_granularity,
      limitation: diagnostic.limitation,
    });
  }
  return [...existing.values()].sort((left, right) => left.result_id.localeCompare(right.result_id));
}

function synchronizeOrders(
  prior: FacilityDecisionOrder[],
  contract: FacilityDecisionContract,
  submission: FacilityDecisionSubmission,
  elapsedSeconds: number,
  profile: FacilityDecisionProfile,
): FacilityDecisionOrder[] {
  const next = [...prior];
  const diagnostics = diagnosticSpecMap(profile);
  for (const orderCode of contract.creates_orders ?? []) {
    if (next.some((order) => order.order_code === orderCode)) continue;
    const diagnostic = diagnostics.get(orderCode);
    if (!diagnostic) throw new Error(`Unknown diagnostic order code: ${orderCode}`);
    next.push({
      order_id: `ORD-${submission.submission_id}-${orderCode}`,
      order_code: orderCode,
      decision_id: contract.decision_id,
      placed_at_seconds: elapsedSeconds,
      status: 'queued',
      resource_id: diagnostic.resource_id,
      queued_at_seconds: elapsedSeconds,
      started_at_seconds: elapsedSeconds,
      due_at_seconds: elapsedSeconds,
      completed_at_seconds: null,
      source_pointer: `config/facility-decision/ASK-D-001.json#diagnostic_catalog[order_code=${orderCode}]`,
    });
  }
  return scheduleOrders(next, profile, elapsedSeconds);
}

function bindResultsToOrders(
  orders: FacilityDecisionOrder[],
  results: FacilityDecisionResult[],
): FacilityDecisionOrder[] {
  const readyOrders = new Set(results.map((result) => result.order_id));
  return orders.map((order) => ({
    ...order,
    status: readyOrders.has(order.order_id) ? 'result_available' as const : order.status,
  }));
}

function resourceStates(
  orders: FacilityDecisionOrder[],
  profile: FacilityDecisionProfile,
): FacilityDecisionResourceState[] {
  return profile.operational_model.resources
    .map((resource) => ({
      resource_id: resource.resource_id,
      capacity: resource.capacity,
      active_order_ids: orders
        .filter((order) => order.resource_id === resource.resource_id && (order.status === 'in_progress' || order.status === 'completed_pending_release'))
        .map((order) => order.order_id)
        .sort(),
      queued_order_ids: orders
        .filter((order) => order.resource_id === resource.resource_id && order.status === 'queued')
        .map((order) => order.order_id)
        .sort(),
      calibration_status: resource.calibration_status,
    }))
    .sort((left, right) => left.resource_id.localeCompare(right.resource_id));
}

function buildHandoff(
  prior: FacilityDecisionHandoffState,
  contract: FacilityDecisionContract,
  submission: FacilityDecisionSubmission,
  elapsedSeconds: number,
): FacilityDecisionHandoffState {
  if (contract.category !== 'closed_loop_handoff') return prior;
  const receiverAcknowledged = submission.values.receiver_acknowledged === true;
  const questionsOffered = submission.values.questions_offered === true;
  const senderConfirmed = submission.values.sender_confirmed === true;
  return {
    sender_identity: typeof submission.values.sender_identity === 'string' ? submission.values.sender_identity : null,
    receiver_identity: typeof submission.values.receiver_identity === 'string' ? submission.values.receiver_identity : null,
    receiver_acknowledged: receiverAcknowledged,
    questions_offered: questionsOffered,
    sender_confirmed: senderConfirmed,
    responsibility_transferred_at_seconds: receiverAcknowledged && questionsOffered && senderConfirmed ? elapsedSeconds : null,
  };
}

function dimensionRecords(
  profile: FacilityDecisionProfile,
  completedDecisionIds: string[],
  facilitySession: FacilityDecisionIntegritySession['facility_session'],
): FacilityDecisionDimensionRecord[] {
  return profile.dimension_policy.dimensions.map((dimension) => ({
    dimension_id: dimension,
    completed_decision_ids: profile.decisions
      .filter((contract) => contract.scoring_dimensions.includes(dimension) && completedDecisionIds.includes(contract.decision_id))
      .map((contract) => contract.decision_id)
      .sort(),
    safety_events: dimension === 'safety'
      ? [...facilitySession.final_state.unsafe_source_action_ids].sort()
      : [],
    calibration_status: 'NOT_CALIBRATED',
  }));
}

function lastReassessmentSeconds(
  submissions: FacilityDecisionSubmission[],
  profile: FacilityDecisionProfile,
  facilitySession: FacilityDecisionIntegritySession['facility_session'],
): number | null {
  const contracts = contractMap(profile);
  const actionIds = new Set(
    submissions
      .filter((submission) => REASSESSMENT_DECISIONS.has(submission.decision_id))
      .map((submission) => contracts.get(submission.decision_id)?.facility_action_id)
      .filter((value): value is string => Boolean(value)),
  );
  let latest: number | null = null;
  for (const transition of facilitySession.transitions) {
    if (transition.action_id && actionIds.has(transition.action_id)) latest = transition.completed_at_seconds;
  }
  return latest;
}

function decisionStateProjection(
  session: Omit<FacilityDecisionIntegritySession, 'decision_root_sha256'> | FacilityDecisionIntegritySession,
): unknown {
  return {
    profile_id: session.profile_id,
    ui_mode: session.ui_mode,
    revision: session.revision,
    facility_final_state: session.facility_session.final_state,
    completed_decision_ids: session.completed_decision_ids,
    orders: session.orders,
    resources: session.resources,
    results: session.results,
    visible_world_events: session.visible_world_events,
    handoff: session.handoff,
    information_state: session.information_state,
  };
}

function recordPayload(record: Omit<FacilityDecisionRecord, 'record_sha256'>): unknown {
  return record;
}

function chainRoot(records: FacilityDecisionRecord[]): string {
  return records.length === 0 ? sha256Canonical([]) : records[records.length - 1].record_sha256;
}

function integrityPayload(session: Omit<FacilityDecisionIntegritySession, 'decision_root_sha256'>): unknown {
  return session;
}

function rebuildDecisionSession(
  session: Omit<FacilityDecisionIntegritySession, 'decision_root_sha256'> | FacilityDecisionIntegritySession,
  profile: FacilityDecisionProfile,
): FacilityDecisionIntegritySession {
  // JavaScript object spreads preserve runtime properties even when a TypeScript
  // Omit<> annotation says otherwise. Always remove any prior root explicitly so
  // an old or forged root can never become part of the next root's hash payload.
  const { decision_root_sha256: _discardedRoot, ...rootlessSession } = session as FacilityDecisionIntegritySession;
  let provisional: FacilityDecisionIntegritySession = { ...rootlessSession, decision_root_sha256: '' };
  const visibleWorldEvents = synchronizeWorldEvents(provisional, profile);
  provisional = { ...provisional, visible_world_events: visibleWorldEvents };
  const scheduledOrders = scheduleOrders(provisional.orders, profile, provisional.facility_session.final_state.elapsed_seconds);
  provisional = { ...provisional, orders: scheduledOrders };
  const results = synchronizeResults(provisional, profile);
  const orders = bindResultsToOrders(scheduledOrders, results);
  const resources = resourceStates(orders, profile);
  const last = lastReassessmentSeconds(provisional.submissions, profile, provisional.facility_session);
  const elapsed = provisional.facility_session.final_state.elapsed_seconds;
  const staleness = last === null ? elapsed : Math.max(0, elapsed - last);
  const informationState = {
    last_structured_reassessment_seconds: last,
    reassessment_due: provisional.facility_session.final_state.terminal_status === 'active'
      && staleness >= profile.operational_model.information_staleness_seconds,
    staleness_seconds: staleness,
  };
  const dimensions = dimensionRecords(profile, provisional.completed_decision_ids, provisional.facility_session);
  const { decision_root_sha256: _emptyRoot, ...provisionalWithoutRoot } = provisional;
  const withoutRoot: Omit<FacilityDecisionIntegritySession, 'decision_root_sha256'> = {
    ...provisionalWithoutRoot,
    orders,
    resources,
    results,
    information_state: informationState,
    dimensions,
    decision_chain_root_sha256: chainRoot(provisional.decision_records),
  };
  return { ...withoutRoot, decision_root_sha256: sha256Canonical(integrityPayload(withoutRoot)) };
}

export function createFacilityDecisionSession(
  facilityContext: FacilitySourceContext,
  uiMode: FacilityDecisionUiMode = 'learner_assessment',
  profile: FacilityDecisionProfile = FACILITY_DECISION_PROFILE,
): FacilityDecisionIntegritySession {
  return rebuildDecisionSession({
    schema_version: '1.0.0',
    profile_id: profile.profile_id,
    ui_mode: uiMode,
    revision: 0,
    facility_session: createFacilitySession(facilityContext),
    submissions: [],
    decision_records: [],
    completed_decision_ids: [],
    orders: [],
    resources: resourceStates([], profile),
    results: [],
    visible_world_events: [],
    handoff: {
      sender_identity: null,
      receiver_identity: null,
      receiver_acknowledged: false,
      questions_offered: false,
      sender_confirmed: false,
      responsibility_transferred_at_seconds: null,
    },
    information_state: {
      last_structured_reassessment_seconds: null,
      reassessment_due: false,
      staleness_seconds: 0,
    },
    dimensions: [],
    decision_chain_root_sha256: sha256Canonical([]),
  }, profile);
}

export interface FacilityDecisionAvailability {
  decision_id: string;
  enabled: boolean;
  reasons: string[];
}

export function evaluateFacilityDecision(
  session: FacilityDecisionIntegritySession,
  decisionId: string,
  context: FacilityDecisionContext,
): FacilityDecisionAvailability {
  const contract = contractMap(context.profile).get(decisionId);
  if (!contract) return { decision_id: decisionId, enabled: false, reasons: ['decision_unknown'] };
  const reasons: string[] = [];
  if (session.facility_session.final_state.terminal_status !== 'active') reasons.push('session_terminal');
  if (!contract.repeatable && session.completed_decision_ids.includes(decisionId)) reasons.push('decision_already_completed');
  for (const prerequisite of contract.prerequisites) {
    if (!session.completed_decision_ids.includes(prerequisite)) reasons.push(`prerequisite_missing:${prerequisite}`);
  }
  for (const event of contract.required_world_events) {
    if (!session.visible_world_events.some((candidate) => candidate.event_id === event)) reasons.push(`world_event_missing:${event}`);
  }
  for (const result of contract.requires_results ?? []) {
    if (!session.results.some((candidate) => candidate.result_id === result)) reasons.push(`result_missing:${result}`);
  }
  // Availability is a total, side-effect-free query. Do not ask the lower-level
  // facility engine to resolve dynamic duration while this decision is already
  // blocked by prerequisites, events, or required results.
  if (reasons.length === 0) {
    try {
      const facilityTrace = evaluateFacilityAction(session.facility_session, {
        command_id: `decision-preview-${session.revision}-${contract.facility_action_id}`,
        action_id: contract.facility_action_id,
        expected_revision: session.facility_session.final_state.revision,
      }, context.facility);
      if (!facilityTrace.enabled) {
        for (const reason of facilityTrace.rejection_reasons) reasons.push(`facility:${reason}`);
      }
    } catch {
      // Fail closed with a stable, non-sensitive reason. A malformed or internally
      // inconsistent state must not crash learner rendering or artifact validation.
      reasons.push('facility:evaluation_failed_closed');
    }
  }
  return { decision_id: decisionId, enabled: reasons.length === 0, reasons: uniqueSorted(reasons) };
}

export function applyFacilityDecisionSubmission(
  session: FacilityDecisionIntegritySession,
  rawSubmission: FacilityDecisionSubmission,
  context: FacilityDecisionContext,
): FacilityDecisionIntegritySession {
  const incomingErrors = decisionSessionIntegrityErrors(session, context);
  if (incomingErrors.length > 0) {
    throw new Error(`Decision session integrity failed before transition: ${incomingErrors.join(',')}`);
  }
  if (rawSubmission.expected_revision !== session.revision) throw new Error('Decision revision mismatch.');
  if (session.submissions.some((submission) => submission.submission_id === rawSubmission.submission_id)) {
    throw new Error('Decision submission ID was reused.');
  }
  const submission = normalizeSubmission(rawSubmission);
  const contract = contractMap(context.profile).get(submission.decision_id);
  if (!contract) throw new Error(`Unknown decision: ${submission.decision_id}`);
  const validation = validateFacilityDecisionSubmission(submission, context.profile);
  if (!validation.valid) throw new Error(`Decision submission invalid: ${validation.errors.join(',')}`);
  const availability = evaluateFacilityDecision(session, submission.decision_id, context);
  if (!availability.enabled) throw new Error(`Decision unavailable: ${availability.reasons.join(',')}`);

  const beforeStateSha256 = sha256Canonical(decisionStateProjection(session));
  const startedAt = session.facility_session.final_state.elapsed_seconds;
  const nextFacility = applyFacilityCommand(session.facility_session, {
    command_id: facilityCommandId(contract.facility_action_id, session.facility_session.command_receipts.length + 1),
    action_id: contract.facility_action_id,
    expected_revision: session.facility_session.final_state.revision,
  }, context.facility).session;
  const orders = synchronizeOrders(session.orders, contract, submission, nextFacility.final_state.elapsed_seconds, context.profile);
  const handoff = buildHandoff(session.handoff, contract, submission, nextFacility.final_state.elapsed_seconds);
  const completed = uniqueSorted([...session.completed_decision_ids, contract.decision_id]);
  const provisional = rebuildDecisionSession({
    ...session,
    revision: session.revision + 1,
    facility_session: nextFacility,
    submissions: [...session.submissions, submission],
    decision_records: session.decision_records,
    completed_decision_ids: completed,
    orders,
    handoff,
    decision_chain_root_sha256: session.decision_chain_root_sha256,
  }, context.profile);
  const priorRecordSha256 = session.decision_records.length === 0
    ? sha256Canonical([])
    : session.decision_records[session.decision_records.length - 1].record_sha256;
  const recordWithoutHash: Omit<FacilityDecisionRecord, 'record_sha256'> = {
    sequence: session.decision_records.length + 1,
    record_id: `DREC-${(session.decision_records.length + 1).toString().padStart(4, '0')}`,
    submission_id: submission.submission_id,
    decision_id: submission.decision_id,
    actor_id: 'receiving_provider',
    payload_sha256: sha256Canonical(submission),
    prior_record_sha256: priorRecordSha256,
    before_state_sha256: beforeStateSha256,
    after_state_sha256: sha256Canonical(decisionStateProjection(provisional)),
    started_at_seconds: startedAt,
    completed_at_seconds: nextFacility.final_state.elapsed_seconds,
  };
  const record: FacilityDecisionRecord = {
    ...recordWithoutHash,
    record_sha256: sha256Canonical(recordPayload(recordWithoutHash)),
  };
  return rebuildDecisionSession({
    ...provisional,
    decision_records: [...session.decision_records, record],
    decision_chain_root_sha256: record.record_sha256,
  }, context.profile);
}

function publicDecisionCategory(category: FacilityDecisionContract['category']): FacilityDecisionPublicCategory {
  if (category === 'high_risk_disposition') return 'disposition';
  if (category === 'high_risk_treatment_change') return 'treatment_intent';
  return category;
}

function actionView(
  session: FacilityDecisionIntegritySession,
  contract: FacilityDecisionContract,
  context: FacilityDecisionContext,
): FacilityDecisionActionView {
  const availability = evaluateFacilityDecision(session, contract.decision_id, context);
  const policy = context.profile.ui_modes[session.ui_mode];
  const view: FacilityDecisionActionView = {
    decision_id: contract.decision_id,
    label: session.ui_mode === 'stakeholder_demo' ? contract.demo_label : contract.learner_label,
    category: publicDecisionCategory(contract.category),
    enabled: availability.enabled,
    fields: contract.fields.map(({ field_id, label, type, required, allowed_values }) => ({
      field_id,
      label,
      type,
      required,
      ...(allowed_values === undefined ? {} : { allowed_values }),
    })),
  };
  if (contract.high_risk) view.requires_deliberate_confirmation = true;
  if (policy.show_disabled_reasons) view.disabled_reasons = availability.reasons;
  if (policy.show_source_origin) {
    view.source_action_id = contract.source_action_id;
    view.source_origin = contract.governing_source;
  }
  return view;
}

export function buildFacilityDecisionView(
  session: FacilityDecisionIntegritySession,
  context: FacilityDecisionContext,
): FacilityDecisionLearnerView {
  const policy = context.profile.ui_modes[session.ui_mode];
  const view: FacilityDecisionLearnerView = {
    schema_version: '1.0.0',
    ui_mode: session.ui_mode,
    terminal_status: session.facility_session.final_state.terminal_status,
    elapsed_seconds: session.facility_session.final_state.elapsed_seconds,
    phase: session.facility_session.final_state.phase,
    completed_decision_count: session.completed_decision_ids.length,
    initial_patient_snapshot: session.facility_session.initial_patient_snapshot,
    actions: context.profile.decisions.map((contract) => actionView(session, contract, context)),
    orders: session.orders.map(({ order_code, status, placed_at_seconds, resource_id, started_at_seconds, due_at_seconds }) => ({
      order_code,
      status,
      placed_at_seconds,
      resource_id,
      started_at_seconds,
      due_at_seconds,
    })),
    resources: session.resources.map(({ resource_id, active_order_ids, queued_order_ids }) => ({
      resource_id,
      active_order_count: active_order_ids.length,
      queued_order_count: queued_order_ids.length,
    })),
    results: session.results.map(({ result_id, order_code, available_at_seconds, learner_result, limitation }) => ({
      result_id,
      order_code,
      available_at_seconds,
      learner_result,
      limitation,
    })),
    visible_world_events: session.visible_world_events,
    information_state: session.information_state,
    handoff_status: {
      receiver_acknowledged: session.handoff.receiver_acknowledged,
      questions_offered: session.handoff.questions_offered,
      sender_confirmed: session.handoff.sender_confirmed,
      responsibility_transferred: session.handoff.responsibility_transferred_at_seconds !== null,
    },
  };
  if (session.facility_session.final_state.terminal_status !== 'active') {
    view.terminal_summary = {
      completed_decisions: session.completed_decision_ids,
      dimensions: session.dimensions,
    };
  }
  if (policy.show_provenance || policy.show_wit || policy.show_live_score || policy.show_source_points) {
    view.instructor = {
      normalized_source_score_bps: session.facility_session.normalized_score_bps,
      source_binding: session.facility_session.source_binding,
      facility_certificate: session.facility_session.certificate,
      wit_observations: session.facility_session.transitions.map((transition) => transition.wit_observation),
      profile_authority: context.profile.authority,
      completed_replay_available: policy.show_completed_replay,
      decision_timeline: session.decision_records.map(({ record_id, sequence, decision_id, started_at_seconds, completed_at_seconds }) => ({
        record_id,
        sequence,
        decision_id,
        started_at_seconds,
        completed_at_seconds,
      })),
    };
  }
  if (policy.show_autoplay || policy.show_completed_replay) {
    view.demo = {
      autoplay_available: true,
      completed_replay_available: true,
      branch_controls: ['timeout', 'discharge', 'tourniquet_change'],
    };
  }
  return view;
}

export function assertLearnerViewHasNoAnswerLeakage(view: FacilityDecisionLearnerView): string[] {
  if (view.ui_mode !== 'learner_assessment' && view.ui_mode !== 'learner_teaching') return [];
  const serialized = JSON.stringify(view);
  return RESTRICTED_LEARNER_TOKENS.filter((token) => serialized.includes(`\"${token}\"`));
}

export function decisionSessionIntegrityErrors(
  session: FacilityDecisionIntegritySession,
  context: FacilityDecisionContext,
): string[] {
  const errors: string[] = [];
  const { decision_root_sha256: _root, ...withoutRoot } = session;
  if (session.decision_root_sha256 !== sha256Canonical(integrityPayload(withoutRoot))) errors.push('decision root mismatch');
  let priorRecordSha256 = sha256Canonical([]);
  for (let index = 0; index < session.decision_records.length; index += 1) {
    const record = session.decision_records[index];
    const { record_sha256: _recordSha, ...recordWithoutHash } = record;
    if (record.sequence !== index + 1) errors.push(`decision record sequence mismatch:${record.record_id}`);
    if (record.prior_record_sha256 !== priorRecordSha256) errors.push(`decision record predecessor mismatch:${record.record_id}`);
    if (record.record_sha256 !== sha256Canonical(recordPayload(recordWithoutHash))) errors.push(`decision record hash mismatch:${record.record_id}`);
    const submission = session.submissions.find((candidate) => candidate.submission_id === record.submission_id);
    if (!submission || sha256Canonical(submission) !== record.payload_sha256) errors.push(`decision record payload mismatch:${record.record_id}`);
    priorRecordSha256 = record.record_sha256;
  }
  if (session.decision_chain_root_sha256 !== priorRecordSha256) errors.push('decision chain root mismatch');
  for (const order of session.orders) {
    if (!context.profile.operational_model.resources.some((resource) => resource.resource_id === order.resource_id)) {
      errors.push(`order resource unknown:${order.order_id}`);
    }
    if (order.started_at_seconds < order.placed_at_seconds || order.due_at_seconds < order.started_at_seconds) {
      errors.push(`order schedule invalid:${order.order_id}`);
    }
  }
  for (const result of session.results) {
    const order = session.orders.find((candidate) => candidate.order_id === result.order_id && candidate.order_code === result.order_code);
    if (!order) errors.push(`result without matching order:${result.result_id}`);
  }
  for (const resource of session.resources) {
    if (resource.active_order_ids.length > resource.capacity) {
      errors.push(`resource capacity exceeded:${resource.resource_id}`);
    }
  }
  if (session.handoff.responsibility_transferred_at_seconds !== null) {
    if (!session.handoff.receiver_acknowledged || !session.handoff.questions_offered || !session.handoff.sender_confirmed) {
      errors.push('handoff transferred without complete closed loop');
    }
  }
  const completedDecisionIds = new Set(session.completed_decision_ids);
  const completedFacilityActionIds = new Set(session.facility_session.final_state.completed_action_ids);
  for (const decisionId of completedDecisionIds) {
    const contract = contractMap(context.profile).get(decisionId);
    if (!contract) errors.push(`completed decision unknown:${decisionId}`);
    else if (!completedFacilityActionIds.has(contract.facility_action_id)) {
      errors.push(`decision/facility completion mismatch:${decisionId}`);
    }
  }
  for (const actionId of completedFacilityActionIds) {
    const contract = context.profile.decisions.find((candidate) => candidate.facility_action_id === actionId);
    if (!contract || !completedDecisionIds.has(contract.decision_id)) {
      errors.push(`facility/decision completion mismatch:${actionId}`);
    }
  }
  for (const submission of session.submissions) {
    const validation = validateFacilityDecisionSubmission(submission, context.profile);
    if (!validation.valid) errors.push(`invalid committed submission:${submission.submission_id}`);
  }
  if (context.profile.authority.concrete_treatment_activation !== false) errors.push('concrete treatment authority escalated');
  if (context.profile.authority.patient_care_use !== 'PROHIBITED') errors.push('patient-care authority escalated');
  if (session.ui_mode === 'learner_assessment' || session.ui_mode === 'learner_teaching') {
    errors.push(...assertLearnerViewHasNoAnswerLeakage(buildFacilityDecisionView(session, context)).map((token) => `learner leakage:${token}`));
  }
  return uniqueSorted(errors);
}

export function facilityDecisionSubmissionId(decisionId: string, ordinal: number): string {
  return `DEC-${ordinal.toString().padStart(3, '0')}-${sha256Canonical(decisionId).slice(0, 10)}`;
}

export function facilityDecisionContext(facility: FacilitySourceContext): FacilityDecisionContext {
  return { facility, profile: FACILITY_DECISION_PROFILE };
}

export function facilityDecisionProfile(): FacilityDecisionProfile {
  return FACILITY_DECISION_PROFILE;
}

export function highRiskDecisionIds(): string[] {
  return [...HIGH_RISK_DECISIONS].sort();
}
