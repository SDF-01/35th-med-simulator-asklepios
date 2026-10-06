import { merkleRoot } from '../scenario-core/certificate';
import { canonicalJson, sha256Canonical, sha256Text } from '../scenario-core/hash';
import type { ActionPriority, ExpectedAction, Scenario } from '../types';
import type {
  FacilityAar,
  FacilityActionDecisionTrace,
  FacilityActionSpec,
  FacilityActorId,
  FacilityArrivalSpec,
  FacilityCertificate,
  FacilityCertificateChecks,
  FacilityClaimLedger,
  FacilityClaimRecord,
  FacilityCommand,
  FacilityCommandReceipt,
  FacilityCommandResult,
  FacilityEventSpec,
  FacilitySession,
  FacilitySourceBinding,
  FacilitySourceContext,
  FacilityState,
  FacilityTransition,
  FacilityWitObservation,
} from './types';

const ALL_ACTOR_IDS: FacilityActorId[] = [
  'receiving_provider',
  'clinic_nurse',
  'diagnostics_tech',
  'wit_observer',
];

const DEMONSTRATED_GATES = [
  'source_scenario_block_binding',
  'source_action_only_clinical_scoring',
  'deterministic_event_sourced_replay',
  'per_transition_state_binding',
  'explicit_actor_knowledge_updates',
  'hidden_findings_withheld_until_diagnostics',
  'timeout_as_authenticated_system_event',
  'duplicate_action_and_command_rejection',
  'score_clamped_to_closed_basis_point_range',
  'wit_process_observation_separated_from_clinical_scoring',
  'exercise_assumptions_disclosed_as_uncalibrated',
] as const;

const OPEN_GATES = [
  'claim_level_clinical_entailment',
  'real_world_frequency_calibration',
  'human_team_policy_calibration',
  'facility_specific_workflow_calibration',
  'continuous_physiology_model',
  'concurrent_multi_casualty_resource_contention',
  'causal_identification_for_counterfactual_aar',
  'executable_to_lean_refinement',
  'independent_proof_kernel_acceptance',
  'formal_vva_for_specific_wing_intended_use',
] as const;

function uniqueSorted(values: readonly string[]): string[] {
  return [...new Set(values)].sort();
}

function cloneState(state: FacilityState): FacilityState {
  return structuredClone(state);
}

export function normalizeFacilityState(state: FacilityState): FacilityState {
  const actorKnowledge = Object.fromEntries(
    ALL_ACTOR_IDS.map((actorId) => [actorId, uniqueSorted(state.actor_knowledge[actorId] ?? [])]),
  ) as FacilityState['actor_knowledge'];
  return {
    ...state,
    completed_action_ids: uniqueSorted(state.completed_action_ids),
    completed_source_action_ids: uniqueSorted(state.completed_source_action_ids),
    unsafe_source_action_ids: uniqueSorted(state.unsafe_source_action_ids),
    fired_system_events: uniqueSorted(state.fired_system_events),
    revealed_hidden_findings: uniqueSorted(state.revealed_hidden_findings),
    actor_knowledge: actorKnowledge,
    alerts: uniqueSorted(state.alerts),
    source_action_completed_at: Object.fromEntries(
      Object.entries(state.source_action_completed_at).sort(([left], [right]) => left.localeCompare(right)),
    ),
    action_completed_at: Object.fromEntries(
      Object.entries(state.action_completed_at).sort(([left], [right]) => left.localeCompare(right)),
    ),
  };
}

export function facilityStateSha256(state: FacilityState): string {
  return sha256Canonical(normalizeFacilityState(state));
}

function flattenSourceActions(scenario: Scenario): Array<ExpectedAction & { priority: ActionPriority }> {
  const priorities: ActionPriority[] = ['critical', 'important', 'optional', 'unsafe'];
  return priorities.flatMap((priority) => scenario.expected_actions[priority].map((action) => ({ ...action, priority })));
}

function sourceActionMap(scenario: Scenario): Map<string, ExpectedAction & { priority: ActionPriority }> {
  return new Map(flattenSourceActions(scenario).map((action) => [action.id, action]));
}

function requiredSourceActionIds(context: FacilitySourceContext): string[] {
  const priorities = new Set(context.spec.completion.required_source_action_priorities);
  return flattenSourceActions(context.scenario)
    .filter((action) => priorities.has(action.priority as 'critical' | 'important'))
    .map((action) => action.id)
    .sort();
}

function optionalSourceActionIds(context: FacilitySourceContext): string[] {
  return context.scenario.expected_actions.optional.map((action) => action.id).sort();
}

function positivePointMaximum(scenario: Scenario): number {
  return flattenSourceActions(scenario).reduce((total, action) => total + Math.max(0, action.points), 0);
}

function sourceScenarioProjection(scenario: Scenario): unknown {
  return {
    scenario_id: scenario.scenario_id,
    title: scenario.title,
    version: scenario.version,
    target_section: scenario.target_section,
    target_role: scenario.target_role,
    patients: scenario.patients,
    expected_actions: scenario.expected_actions,
    end_conditions: scenario.end_conditions,
    aar_teaching_points: scenario.aar_teaching_points,
  };
}

export function buildFacilitySourceBinding(context: FacilitySourceContext): FacilitySourceBinding {
  return {
    source_scenario_id: context.scenario.scenario_id,
    source_scenario_sha256: sha256Canonical(sourceScenarioProjection(context.scenario)),
    source_action_ids: flattenSourceActions(context.scenario).map((action) => action.id).sort(),
    source_file_path: 'src/content/scenarios.ts',
    template_asset_id: 'template:ASK-D-001',
    template_record_sha256: context.template_record_sha256,
    content_registry_merkle_root: context.content_registry_merkle_root,
  };
}

function initialActorKnowledge(spec: FacilityArrivalSpec): FacilityState['actor_knowledge'] {
  return Object.fromEntries(
    ALL_ACTOR_IDS.map((actorId) => {
      const actor = spec.actors.find((candidate) => candidate.actor_id === actorId);
      return [actorId, uniqueSorted(actor?.initial_knowledge ?? [])];
    }),
  ) as FacilityState['actor_knowledge'];
}

export function createInitialFacilityState(context: FacilitySourceContext): FacilityState {
  return normalizeFacilityState({
    revision: 0,
    elapsed_seconds: 0,
    phase: 'pre_arrival',
    terminal_status: 'active',
    outcome: null,
    completed_action_ids: [],
    completed_source_action_ids: [],
    unsafe_source_action_ids: [],
    fired_system_events: [],
    source_action_completed_at: {},
    action_completed_at: {},
    revealed_hidden_findings: [],
    actor_knowledge: initialActorKnowledge(context.spec),
    alerts: [],
    score_points: 0,
    max_positive_points: positivePointMaximum(context.scenario),
  });
}

function grantKnowledge(
  state: FacilityState,
  grants: Partial<Record<FacilityActorId, string[]>>,
): void {
  for (const actorId of ALL_ACTOR_IDS) {
    const values = grants[actorId];
    if (values) state.actor_knowledge[actorId].push(...values);
  }
}

function actionMap(spec: FacilityArrivalSpec): Map<string, FacilityActionSpec> {
  return new Map(spec.actions.map((action) => [action.action_id, action]));
}

function eventMap(spec: FacilityArrivalSpec): Map<string, FacilityEventSpec> {
  return new Map(spec.events.map((event) => [event.event_id, event]));
}

function diagnosticsDueAt(state: FacilityState, context: FacilitySourceContext): number | null {
  const imaging = state.action_completed_at.order_imaging;
  const labs = state.action_completed_at.order_labs;
  if (imaging === undefined || labs === undefined) return null;
  return Math.max(imaging, labs) + context.spec.parameters.diagnostic_delay_seconds.value;
}

function actionDurationSeconds(
  state: FacilityState,
  action: FacilityActionSpec,
  context: FacilitySourceContext,
): number | null {
  if (action.duration_mode === 'fixed') return action.duration_seconds;
  const dueAt = diagnosticsDueAt(state, context);
  return dueAt === null ? null : Math.max(0, dueAt - state.elapsed_seconds);
}

function commandFingerprint(command: FacilityCommand): string {
  return sha256Canonical(command);
}

function existingReceipt(session: FacilitySession, commandId: string): FacilityCommandReceipt | undefined {
  return session.command_receipts.find((receipt) => receipt.command_id === commandId);
}

function sourceActionValid(action: FacilityActionSpec, context: FacilitySourceContext): boolean {
  if (action.origin === 'operational_workflow') return action.source_action_id === null;
  if (!action.source_action_id) return false;
  return sourceActionMap(context.scenario).has(action.source_action_id);
}

function completionRequirementsMet(state: FacilityState, context: FacilitySourceContext): boolean {
  const requiredSource = requiredSourceActionIds(context);
  return requiredSource.every((id) => state.completed_source_action_ids.includes(id))
    && context.spec.completion.required_operational_actions
      .filter((id) => id !== 'complete_handoff')
      .every((id) => state.completed_action_ids.includes(id))
    && context.spec.completion.required_event_ids.every((id) => state.fired_system_events.includes(id))
    && state.unsafe_source_action_ids.length === 0;
}

export function evaluateFacilityAction(
  session: FacilitySession,
  command: FacilityCommand,
  context: FacilitySourceContext,
): FacilityActionDecisionTrace {
  const action = actionMap(context.spec).get(command.action_id);
  const receipt = existingReceipt(session, command.command_id);
  const fingerprint = commandFingerprint(command);
  const prerequisitesComplete = Boolean(
    action && action.prerequisites.every((id) => session.final_state.completed_action_ids.includes(id)),
  );
  const requiredEventsComplete = Boolean(
    action && (action.required_event_ids ?? []).every((id) => session.final_state.fired_system_events.includes(id)),
  );
  const duration = action && prerequisitesComplete && requiredEventsComplete
    ? actionDurationSeconds(session.final_state, action, context)
    : null;
  const durationResolvable = Boolean(action && (action.duration_mode === 'fixed' || duration !== null));
  const timeout = context.spec.parameters.timeout_seconds.value;
  const conditions = {
    session_active: session.final_state.terminal_status === 'active',
    revision_matches: session.final_state.revision === command.expected_revision,
    command_id_unused_or_identical: !receipt || receipt.command_sha256 === fingerprint,
    action_known: Boolean(action),
    action_not_already_completed_or_repeatable: Boolean(
      action && (action.repeatable || !session.final_state.completed_action_ids.includes(action.action_id)),
    ),
    prerequisites_complete: prerequisitesComplete,
    required_events_complete: requiredEventsComplete,
    duration_resolvable: durationResolvable,
    source_binding_valid: Boolean(action && sourceActionValid(action, context)),
    action_can_finish_before_timeout_or_is_wait: Boolean(
      action && duration !== null && (
        session.final_state.elapsed_seconds + duration <= timeout
        || action.action_id === 'wait_60'
      ),
    ),
    completion_requirements_met: Boolean(
      action && (action.action_id !== 'complete_handoff' || completionRequirementsMet(session.final_state, context)),
    ),
  };
  const rejectionReasons = Object.entries(conditions)
    .filter(([, value]) => !value)
    .map(([name]) => name);
  return {
    action_id: command.action_id,
    enabled: rejectionReasons.length === 0,
    conditions,
    rejection_reasons: rejectionReasons,
  };
}

function witObservation(category: string, statement: string): FacilityWitObservation {
  return {
    category,
    statement,
    process_only: true,
    clinical_directive: null,
  };
}

function appendTransition(
  transitions: FacilityTransition[],
  input: Omit<FacilityTransition, 'sequence' | 'transition_id' | 'before_state_sha256' | 'after_state_sha256'>,
  beforeState: FacilityState,
): FacilityTransition {
  const sequence = transitions.length + 1;
  const normalizedAfter = normalizeFacilityState(input.state_after);
  const core = {
    ...input,
    sequence,
    state_after: normalizedAfter,
    before_state_sha256: facilityStateSha256(beforeState),
    after_state_sha256: facilityStateSha256(normalizedAfter),
  };
  const transition: FacilityTransition = {
    ...core,
    transition_id: `FAT-${sequence.toString().padStart(3, '0')}-${sha256Canonical(core).slice(0, 12)}`,
  };
  transitions.push(transition);
  return transition;
}

function eventTriggered(
  event: FacilityEventSpec,
  state: FacilityState,
  context: FacilitySourceContext,
  justCompletedActionId: string | null,
): boolean {
  if (state.fired_system_events.includes(event.event_id)) return false;
  switch (event.trigger.kind) {
    case 'initial':
      return state.revision === 0;
    case 'after_action':
      return justCompletedActionId === event.trigger.action_id;
    case 'elapsed_time_due':
      return state.elapsed_seconds >= event.trigger.at_elapsed_seconds;
    case 'diagnostics_due': {
      const dueAt = diagnosticsDueAt(state, context);
      return dueAt !== null && state.elapsed_seconds >= dueAt;
    }
    case 'timeout_due':
      return state.elapsed_seconds >= context.spec.parameters.timeout_seconds.value
        && state.terminal_status === 'active';
  }
}

function applySystemEvent(
  state: FacilityState,
  event: FacilityEventSpec,
  context: FacilitySourceContext,
  transitions: FacilityTransition[],
  eventTimeSeconds?: number,
  triggeringCommand?: FacilityCommand,
): FacilityState {
  const before = normalizeFacilityState(state);
  const after = cloneState(before);
  if (eventTimeSeconds !== undefined) after.elapsed_seconds = eventTimeSeconds;
  after.revision += 1;
  after.fired_system_events.push(event.event_id);
  grantKnowledge(after, event.knowledge_grants);
  if (event.reveal_source_hidden_findings) {
    after.revealed_hidden_findings.push(...context.scenario.patients.flatMap((patient) => patient.hidden_findings));
  }
  if (event.event_id === 'prearrival_notice') {
    after.alerts.push('Pre-arrival notification received. Prepare for post-field-care reception.');
  }
  if (event.event_id === 'second_casualty_inbound') {
    after.alerts.push('Second casualty inbound. Preserve continuity while resources remain constrained.');
  }
  if (event.event_id === 'diagnostics_ready') {
    after.alerts.push('Ordered imaging and laboratory results are available for review.');
  }
  if (event.terminal_effect) {
    after.terminal_status = event.terminal_effect;
    after.phase = 'complete';
    after.outcome = event.terminal_effect === 'timeout'
      ? 'Exercise ended at the source-bound timeout before closed-loop receiving handoff.'
      : `Exercise ended: ${event.terminal_effect}`;
  }
  const normalizedAfter = normalizeFacilityState(after);
  appendTransition(
    transitions,
    {
      kind: 'system_event',
      actor_id: 'system',
      command_id: triggeringCommand?.command_id ?? null,
      action_id: triggeringCommand?.action_id ?? null,
      event_id: event.event_id,
      label: event.label,
      source_action_id: null,
      origin: 'system_event',
      started_at_seconds: before.elapsed_seconds,
      completed_at_seconds: normalizedAfter.elapsed_seconds,
      score_delta: 0,
      state_after: normalizedAfter,
      wit_observation: witObservation(event.wit_category, event.label),
    },
    before,
  );
  return normalizedAfter;
}

function processTriggeredEvents(
  state: FacilityState,
  context: FacilitySourceContext,
  transitions: FacilityTransition[],
  justCompletedActionId: string | null,
): FacilityState {
  let current = normalizeFacilityState(state);
  for (const event of context.spec.events) {
    if (eventTriggered(event, current, context, justCompletedActionId)) {
      current = applySystemEvent(current, event, context, transitions);
    }
  }
  return current;
}

function applyLearnerAction(
  state: FacilityState,
  action: FacilityActionSpec,
  command: FacilityCommand,
  context: FacilitySourceContext,
  transitions: FacilityTransition[],
): FacilityState {
  const before = normalizeFacilityState(state);
  const duration = actionDurationSeconds(before, action, context);
  if (duration === null) {
    throw new Error('Facility action duration was unresolved after admission.');
  }
  const timeout = context.spec.parameters.timeout_seconds.value;
  if (before.elapsed_seconds + duration > timeout) {
    const timeoutEvent = eventMap(context.spec).get('timeout_reached');
    if (!timeoutEvent) throw new Error('Timeout event missing from facility specification.');
    return applySystemEvent(before, timeoutEvent, context, transitions, timeout, command);
  }

  const after = cloneState(before);
  after.revision += 1;
  after.elapsed_seconds += duration;
  after.completed_action_ids.push(action.action_id);
  after.action_completed_at[action.action_id] = after.elapsed_seconds;
  if (action.phase_after) after.phase = action.phase_after;
  grantKnowledge(after, action.knowledge_grants);

  let scoreDelta = 0;
  if (action.source_action_id) {
    const source = sourceActionMap(context.scenario).get(action.source_action_id);
    if (!source) throw new Error(`Unknown source action: ${action.source_action_id}`);
    after.completed_source_action_ids.push(source.id);
    after.source_action_completed_at[source.id] = after.elapsed_seconds;
    scoreDelta = source.points;
    after.score_points += source.points;
    if (source.priority === 'unsafe') after.unsafe_source_action_ids.push(source.id);
  }

  if (action.action_id === 'review_diagnostics') {
    after.alerts.push('Diagnostic results reviewed and casualty reassessed.');
  }
  if (action.action_id === 'pain_management') {
    after.alerts.push('Source-defined pain-management objective addressed without generating a drug, dose, or route.');
  }
  if (action.terminal_effect) {
    after.terminal_status = action.terminal_effect;
    after.phase = 'complete';
    after.outcome = action.terminal_effect === 'completed'
      ? 'Closed-loop receiving handoff completed.'
      : `Unsafe source action selected: ${action.label}`;
  }

  const normalizedAfter = normalizeFacilityState(after);
  appendTransition(
    transitions,
    {
      kind: 'learner_action',
      actor_id: 'receiving_provider',
      command_id: command.command_id,
      action_id: action.action_id,
      event_id: null,
      label: action.label,
      source_action_id: action.source_action_id,
      origin: action.origin,
      started_at_seconds: before.elapsed_seconds,
      completed_at_seconds: normalizedAfter.elapsed_seconds,
      score_delta: scoreDelta,
      state_after: normalizedAfter,
      wit_observation: witObservation(action.wit_category, `${action.label} observed.`),
    },
    before,
  );
  return normalizedAfter;
}

function normalizedScoreBps(state: FacilityState): number {
  if (state.max_positive_points <= 0) return 0;
  const raw = Math.round((state.score_points * 10_000) / state.max_positive_points);
  return Math.min(10_000, Math.max(0, raw));
}

function actorKnowledgeAuthorized(session: FacilitySession, context: FacilitySourceContext): boolean {
  const allowed = new Map<FacilityActorId, Set<string>>();
  for (const actor of context.spec.actors) allowed.set(actor.actor_id, new Set(actor.initial_knowledge));
  for (const action of context.spec.actions) {
    for (const actorId of ALL_ACTOR_IDS) {
      for (const token of action.knowledge_grants[actorId] ?? []) allowed.get(actorId)?.add(token);
    }
  }
  for (const event of context.spec.events) {
    for (const actorId of ALL_ACTOR_IDS) {
      for (const token of event.knowledge_grants[actorId] ?? []) allowed.get(actorId)?.add(token);
    }
  }
  return ALL_ACTOR_IDS.every((actorId) => (
    session.final_state.actor_knowledge[actorId].every((token) => allowed.get(actorId)?.has(token))
  ));
}

function transitionStatesBound(session: FacilitySession): boolean {
  let previous = facilityStateSha256(session.initial_state);
  for (const transition of session.transitions) {
    if (transition.before_state_sha256 !== previous) return false;
    if (transition.after_state_sha256 !== facilityStateSha256(transition.state_after)) return false;
    previous = transition.after_state_sha256;
  }
  return previous === facilityStateSha256(session.final_state);
}

function diagnosticsPrecedeHiddenFindings(session: FacilitySession): boolean {
  const diagnosticSequence = session.transitions.find((transition) => transition.event_id === 'diagnostics_ready')?.sequence;
  for (const transition of session.transitions) {
    if (transition.state_after.revealed_hidden_findings.length > 0) {
      if (diagnosticSequence === undefined || transition.sequence < diagnosticSequence) return false;
    }
  }
  return true;
}

function timeoutIsEventSourced(session: FacilitySession): boolean {
  if (session.final_state.terminal_status !== 'timeout') return true;
  const last = session.transitions.at(-1);
  return last?.kind === 'system_event'
    && last.event_id === 'timeout_reached'
    && last.state_after.terminal_status === 'timeout';
}

function replayChainComplete(session: FacilitySession): boolean {
  if (!transitionStatesBound(session)) return false;
  const last = session.transitions.at(-1);
  return Boolean(last && canonicalJson(last.state_after) === canonicalJson(session.final_state));
}

function certificateChecks(
  session: FacilitySession,
  context: FacilitySourceContext,
  claimLedger: FacilityClaimLedger,
): FacilityCertificateChecks {
  const expectedBinding = buildFacilitySourceBinding(context);
  const required = requiredSourceActionIds(context);
  const diagnosticsSequence = session.transitions.find((transition) => transition.event_id === 'diagnostics_ready')?.sequence;
  const handoff = session.transitions.find((transition) => transition.action_id === 'complete_handoff');
  const allWitProcessOnly = session.transitions.every((transition) => (
    transition.wit_observation.process_only && transition.wit_observation.clinical_directive === null
  ));
  return {
    source_binding_matches: canonicalJson(session.source_binding) === canonicalJson(expectedBinding),
    source_action_subset_preserved: session.final_state.completed_source_action_ids.every((id) => expectedBinding.source_action_ids.includes(id)),
    required_source_actions_complete: session.final_state.terminal_status !== 'completed'
      || required.every((id) => session.final_state.completed_source_action_ids.includes(id)),
    unsafe_source_actions_fail_closed: session.final_state.unsafe_source_action_ids.length === 0
      || session.final_state.terminal_status === 'failed',
    diagnostics_precede_hidden_findings: diagnosticsPrecedeHiddenFindings(session),
    terminal_handoff_reached: session.final_state.terminal_status !== 'completed'
      || Boolean(handoff && diagnosticsSequence !== undefined && handoff.sequence > diagnosticsSequence),
    patient_care_use_prohibited: session.authority.patient_care_use === 'PROHIBITED',
    wit_observations_process_only: allWitProcessOnly,
    replay_chain_complete: replayChainComplete(session),
    timeout_is_event_sourced: timeoutIsEventSourced(session),
    transition_states_bound: transitionStatesBound(session),
    score_within_bounds: session.normalized_score_bps >= 0 && session.normalized_score_bps <= 10_000,
    actor_knowledge_authorized: actorKnowledgeAuthorized(session, context),
    uncalibrated_parameters_disclosed: Object.values(context.spec.parameters).every((parameter) => (
      parameter.calibration_status === 'NOT_CALIBRATED' || parameter.calibration_status === 'SOURCE_BOUND'
    )) && claimLedger.records.some((record) => record.origin_class === 'exercise_assumption'),
  };
}

function stripFacilityCertificate(session: FacilitySession): Omit<FacilitySession, 'certificate'> {
  const { certificate: _certificate, ...withoutCertificate } = session;
  return withoutCertificate;
}

function buildCertificate(
  sessionWithoutCertificate: Omit<FacilitySession, 'certificate'>,
  context: FacilitySourceContext,
  claimLedger: FacilityClaimLedger,
): FacilityCertificate {
  const provisional = { ...sessionWithoutCertificate, certificate: {} as FacilityCertificate } as FacilitySession;
  const checks = certificateChecks(provisional, context, claimLedger);
  const transitionHashes = sessionWithoutCertificate.transitions.map((transition) => transition.after_state_sha256);
  const sessionSha256 = sha256Canonical(sessionWithoutCertificate);
  return {
    certificate_version: '1.0.0',
    source_binding_sha256: sha256Canonical(sessionWithoutCertificate.source_binding),
    spec_sha256: sha256Canonical(context.spec),
    initial_state_sha256: facilityStateSha256(sessionWithoutCertificate.initial_state),
    final_state_sha256: facilityStateSha256(sessionWithoutCertificate.final_state),
    transition_root_sha256: merkleRoot(transitionHashes),
    replay_root_sha256: sha256Canonical({
      initial_state: sessionWithoutCertificate.initial_state,
      transitions: sessionWithoutCertificate.transitions.map((transition) => ({
        transition_id: transition.transition_id,
        before_state_sha256: transition.before_state_sha256,
        after_state_sha256: transition.after_state_sha256,
      })),
      final_state: sessionWithoutCertificate.final_state,
    }),
    claim_ledger_sha256: claimLedger.ledger_sha256,
    checks,
    session_sha256: sessionSha256,
  };
}

function rebuildSession(
  base: Omit<FacilitySession, 'certificate' | 'normalized_score_bps'>,
  context: FacilitySourceContext,
  claimLedger: FacilityClaimLedger,
): FacilitySession {
  const normalized = normalizedScoreBps(base.final_state);
  const withoutCertificate: Omit<FacilitySession, 'certificate'> = {
    ...base,
    normalized_score_bps: normalized,
  };
  const certificate = buildCertificate(withoutCertificate, context, claimLedger);
  return { ...withoutCertificate, certificate };
}

function recordHash(record: Omit<FacilityClaimRecord, 'record_sha256'>): string {
  return sha256Canonical(record);
}

export function buildFacilityClaimLedger(context: FacilitySourceContext): FacilityClaimLedger {
  const records: FacilityClaimRecord[] = [];
  const add = (record: Omit<FacilityClaimRecord, 'record_sha256'>) => {
    records.push({ ...record, record_sha256: recordHash(record) });
  };
  add({
    claim_id: 'claim-source-template-ASK-D-001',
    field_path: 'source_binding.source_scenario_id',
    atomic_claim: 'Clinical actions, points, patient presentation, hidden findings, unsafe actions, and timeout are inherited from ASK-D-001.',
    origin_class: 'inherited_source_template',
    relation: 'INHERITED',
    evidence_entailment: 'NOT_APPLICABLE',
    contradiction_status: 'NOT_APPLICABLE',
    clinical_authority: 'INHERITED_ONLY',
    source_pointer: 'src/content/scenarios.ts#ASK-D-001',
  });
  for (const [name, parameter] of Object.entries(context.spec.parameters)) {
    if (parameter.origin === 'exercise_assumption' || parameter.origin === 'exercise_policy') {
      add({
        claim_id: `claim-parameter-${name}`,
        field_path: `spec.parameters.${name}`,
        atomic_claim: `${name} is a declared exercise parameter, not an empirically calibrated real-world frequency.`,
        origin_class: 'exercise_assumption',
        relation: 'ASSUMPTION',
        evidence_entailment: 'NOT_ADJUDICATED',
        contradiction_status: 'NOT_SEARCHED',
        clinical_authority: 'NOT_GRANTED',
        source_pointer: 'config/facility-arrival/ASK-D-001.json',
      });
    }
  }
  for (const sourceId of ['JTS-CPG-INDEX-2026-07-28', 'JTS-PI-2026-04-02', 'JTS-DCOT-2026-04-03', 'USAF-WIT-CRE-2026']) {
    add({
      claim_id: `claim-scope-${sourceId}`,
      field_path: `source_truth.records.${sourceId}`,
      atomic_claim: `${sourceId} is used only to frame care-continuum, performance-improvement, or inspection process scope.`,
      origin_class: 'scope_reference',
      relation: 'SCOPE_AND_PROCESS_REFERENCE',
      evidence_entailment: 'NOT_ADJUDICATED',
      contradiction_status: 'NOT_SEARCHED',
      clinical_authority: 'NOT_GRANTED',
      source_pointer: `examples/facility-arrival/source-truth.json#${sourceId}`,
    });
  }
  records.sort((left, right) => left.claim_id.localeCompare(right.claim_id));
  const payload = { schema_version: '1.0.0' as const, example_id: context.spec.example_id, records };
  return { ...payload, ledger_sha256: sha256Canonical(payload) };
}

export function createFacilitySession(context: FacilitySourceContext): FacilitySession {
  const claimLedger = buildFacilityClaimLedger(context);
  const initialState = createInitialFacilityState(context);
  const transitions: FacilityTransition[] = [];
  let current = processTriggeredEvents(initialState, context, transitions, null);
  const sourceBinding = buildFacilitySourceBinding(context);
  return rebuildSession({
    schema_version: '1.1.0',
    example_id: context.spec.example_id,
    title: 'Post-CUF/TFC blast casualty reception at a constrained base clinic',
    facility_profile: context.spec.profile_id,
    care_continuum_phase: context.spec.care_continuum_phase,
    authority: context.spec.authority,
    source_binding: sourceBinding,
    spec_sha256: sha256Canonical(context.spec),
    initial_patient_snapshot: {
      presentation: context.scenario.patients[0]?.initial_presentation ?? '',
      vitals: context.scenario.patients[0]?.initial_vitals ?? {
        hr: 0,
        bp_systolic: 0,
        bp_diastolic: 0,
        rr: 0,
        spo2: 0,
        temp_c: 0,
        gcs: 0,
      },
      hidden_findings_count: context.scenario.patients.reduce((total, patient) => total + patient.hidden_findings.length, 0),
    },
    initial_state: initialState,
    transitions,
    command_receipts: [],
    final_state: current,
  }, context, claimLedger);
}

export function applyFacilityCommand(
  session: FacilitySession,
  command: FacilityCommand,
  context: FacilitySourceContext,
): FacilityCommandResult {
  const prior = existingReceipt(session, command.command_id);
  const fingerprint = commandFingerprint(command);
  if (prior) {
    if (prior.command_sha256 !== fingerprint) throw new Error('Command ID was reused with different content.');
    return { session, idempotent: true };
  }

  const decision = evaluateFacilityAction(session, command, context);
  if (!decision.enabled) {
    throw new Error(`Facility action rejected: ${decision.rejection_reasons.join(',')}`);
  }
  const action = actionMap(context.spec).get(command.action_id);
  if (!action) throw new Error(`Unknown facility action: ${command.action_id}`);

  const transitions = structuredClone(session.transitions);
  const firstSequence = transitions.length + 1;
  let current = applyLearnerAction(session.final_state, action, command, context, transitions);
  if (current.terminal_status === 'active') {
    current = processTriggeredEvents(current, context, transitions, action.action_id);
  }
  const finalSequence = transitions.length;
  const receipts = [...session.command_receipts, {
    command_id: command.command_id,
    action_id: command.action_id,
    command_sha256: fingerprint,
    first_transition_sequence: firstSequence <= finalSequence ? firstSequence : null,
    final_transition_sequence: firstSequence <= finalSequence ? finalSequence : null,
  }].sort((left, right) => left.command_id.localeCompare(right.command_id));
  const claimLedger = buildFacilityClaimLedger(context);
  const next = rebuildSession({
    schema_version: session.schema_version,
    example_id: session.example_id,
    title: session.title,
    facility_profile: session.facility_profile,
    care_continuum_phase: session.care_continuum_phase,
    authority: session.authority,
    source_binding: session.source_binding,
    spec_sha256: session.spec_sha256,
    initial_patient_snapshot: session.initial_patient_snapshot,
    initial_state: session.initial_state,
    transitions,
    command_receipts: receipts,
    final_state: current,
  }, context, claimLedger);
  return { session: next, idempotent: false };
}

export function runCanonicalFacilitySession(context: FacilitySourceContext): FacilitySession {
  let session = createFacilitySession(context);
  context.spec.canonical_command_sequence.forEach((actionId, index) => {
    session = applyFacilityCommand(session, {
      command_id: `canonical-${(index + 1).toString().padStart(2, '0')}-${actionId}`,
      action_id: actionId,
      expected_revision: session.final_state.revision,
    }, context).session;
  });
  return session;
}

export function replayFacilityCommands(
  commands: readonly FacilityCommand[],
  context: FacilitySourceContext,
): FacilitySession {
  let session = createFacilitySession(context);
  for (const command of commands) session = applyFacilityCommand(session, command, context).session;
  return session;
}

export function validateFacilitySession(
  session: FacilitySession,
  context: FacilitySourceContext,
  claimLedger = buildFacilityClaimLedger(context),
): string[] {
  const errors: string[] = [];
  const expectedBinding = buildFacilitySourceBinding(context);
  if (canonicalJson(session.source_binding) !== canonicalJson(expectedBinding)) errors.push('source binding mismatch');
  if (session.spec_sha256 !== sha256Canonical(context.spec)) errors.push('spec hash mismatch');
  const withoutCertificate = stripFacilityCertificate(session);
  if (session.certificate.session_sha256 !== sha256Canonical(withoutCertificate)) {
    errors.push('session hash mismatch');
  }
  const expectedCertificate = buildCertificate(withoutCertificate, context, claimLedger);
  if (canonicalJson(session.certificate) !== canonicalJson(expectedCertificate)) errors.push('certificate mismatch');
  if (!Object.values(session.certificate.checks).every(Boolean)) {
    for (const [name, value] of Object.entries(session.certificate.checks)) if (!value) errors.push(`certificate check failed:${name}`);
  }
  if (!transitionStatesBound(session)) errors.push('transition chain or state binding mismatch');
  if (session.normalized_score_bps !== normalizedScoreBps(session.final_state)) errors.push('normalized score mismatch');
  if (session.final_state.terminal_status === 'completed' && !completionRequirementsMet(session.final_state, context)) {
    errors.push('completed session does not meet completion requirements');
  }
  if (session.final_state.revealed_hidden_findings.length > 0 && !session.final_state.fired_system_events.includes('diagnostics_ready')) {
    errors.push('hidden findings revealed before diagnostics');
  }
  return uniqueSorted(errors);
}

export function buildFacilityAar(session: FacilitySession, context: FacilitySourceContext): FacilityAar {
  const required = requiredSourceActionIds(context);
  const optional = optionalSourceActionIds(context);
  const requiredCompleted = required.filter((id) => session.final_state.completed_source_action_ids.includes(id));
  const optionalCompleted = optional.filter((id) => session.final_state.completed_source_action_ids.includes(id));
  const witSummary = session.transitions.map((transition) => transition.wit_observation);
  const strengths: string[] = [];
  const improvements: string[] = [];
  if (requiredCompleted.length === required.length) strengths.push('All required source-template actions were completed.');
  else improvements.push(`Complete missing required source actions: ${required.filter((id) => !requiredCompleted.includes(id)).join(', ')}.`);
  if (session.final_state.unsafe_source_action_ids.length === 0) strengths.push('No source-defined unsafe action was selected.');
  else improvements.push(`Avoid unsafe source actions: ${session.final_state.unsafe_source_action_ids.join(', ')}.`);
  if (session.final_state.fired_system_events.includes('diagnostics_ready')) strengths.push('Diagnostic results were processed through an explicit system event before disclosure.');
  if (session.final_state.terminal_status !== 'completed') improvements.push('Reach a closed-loop receiving handoff before timeout or failure.');
  const optionalMissing = optional.filter((id) => !optionalCompleted.includes(id));
  if (optionalMissing.length > 0) improvements.push(`Optional source objectives not exercised: ${optionalMissing.join(', ')}.`);
  const payload = {
    schema_version: '1.1.0' as const,
    example_id: session.example_id,
    session_sha256: session.certificate.session_sha256,
    terminal_status: session.final_state.terminal_status,
    normalized_score_bps: session.normalized_score_bps,
    passed: session.final_state.terminal_status === 'completed'
      && session.normalized_score_bps >= context.spec.parameters.pass_threshold_bps.value,
    pass_threshold_bps: context.spec.parameters.pass_threshold_bps.value,
    source_action_coverage: {
      required_completed: requiredCompleted,
      required_missing: required.filter((id) => !requiredCompleted.includes(id)),
      optional_completed: optionalCompleted,
      optional_not_exercised: optionalMissing,
    },
    strengths,
    improvement_opportunities: improvements,
    wit_observation_summary: witSummary,
    counterfactual_boundaries: {
      available_branches: ['unsafe_discharge', 'unsafe_tourniquet_removal', 'source_bound_timeout'],
      causal_claims_allowed: false as const,
      note: 'Alternative branches are deterministic replay comparisons. They are not identified causal effects.',
    },
    validity_ledger: {
      demonstrated: [...DEMONSTRATED_GATES],
      open: [...OPEN_GATES],
    },
  };
  return { ...payload, aar_sha256: sha256Canonical(payload) };
}

export function facilitySessionSummary(session: FacilitySession): Record<string, unknown> {
  return {
    example_id: session.example_id,
    terminal_status: session.final_state.terminal_status,
    elapsed_seconds: session.final_state.elapsed_seconds,
    transitions: session.transitions.length,
    learner_actions: session.transitions.filter((transition) => transition.kind === 'learner_action').length,
    system_events: session.transitions.filter((transition) => transition.kind === 'system_event').length,
    normalized_score_bps: session.normalized_score_bps,
    session_sha256: session.certificate.session_sha256,
    checks: session.certificate.checks,
  };
}

export function facilityCommandId(actionId: string, ordinal: number): string {
  return `cmd-${ordinal.toString().padStart(3, '0')}-${sha256Text(actionId).slice(0, 8)}`;
}
