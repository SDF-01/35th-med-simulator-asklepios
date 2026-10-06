import { merkleRoot } from '../scenario-core/certificate';
import { canonicalJson, sha256Canonical } from '../scenario-core/hash';
import type { ActionPriority, ExpectedAction, Scenario } from '../types';
import type {
  FacilityActionSpec,
  FacilityActorId,
  FacilityArrivalSpec,
  FacilityClaimLedger,
  FacilityEventSpec,
  FacilitySession,
  FacilitySourceContext,
  FacilityState,
  FacilityTransition,
} from '../facility-arrival/types';

const ACTORS: FacilityActorId[] = ['receiving_provider', 'clinic_nurse', 'diagnostics_tech', 'wit_observer'];

function uniqueSorted(values: readonly string[]): string[] {
  return [...new Set(values)].sort();
}

function normalize(state: FacilityState): FacilityState {
  return {
    ...state,
    completed_action_ids: uniqueSorted(state.completed_action_ids),
    completed_source_action_ids: uniqueSorted(state.completed_source_action_ids),
    unsafe_source_action_ids: uniqueSorted(state.unsafe_source_action_ids),
    fired_system_events: uniqueSorted(state.fired_system_events),
    revealed_hidden_findings: uniqueSorted(state.revealed_hidden_findings),
    alerts: uniqueSorted(state.alerts),
    actor_knowledge: Object.fromEntries(ACTORS.map((actor) => [actor, uniqueSorted(state.actor_knowledge[actor] ?? [])])) as FacilityState['actor_knowledge'],
    source_action_completed_at: Object.fromEntries(Object.entries(state.source_action_completed_at).sort(([a], [b]) => a.localeCompare(b))),
    action_completed_at: Object.fromEntries(Object.entries(state.action_completed_at).sort(([a], [b]) => a.localeCompare(b))),
  };
}

function stateHash(state: FacilityState): string {
  return sha256Canonical(normalize(state));
}

function flatten(scenario: Scenario): Array<ExpectedAction & { priority: ActionPriority }> {
  const priorities: ActionPriority[] = ['critical', 'important', 'optional', 'unsafe'];
  return priorities.flatMap((priority) => scenario.expected_actions[priority].map((action) => ({ ...action, priority })));
}

function sourceMap(scenario: Scenario): Map<string, ExpectedAction & { priority: ActionPriority }> {
  return new Map(flatten(scenario).map((action) => [action.id, action]));
}

function sourceProjection(scenario: Scenario): unknown {
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

function initialState(context: FacilitySourceContext): FacilityState {
  const maxPoints = flatten(context.scenario).reduce((sum, action) => sum + Math.max(0, action.points), 0);
  return normalize({
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
    actor_knowledge: Object.fromEntries(ACTORS.map((actor) => [
      actor,
      context.spec.actors.find((candidate) => candidate.actor_id === actor)?.initial_knowledge ?? [],
    ])) as FacilityState['actor_knowledge'],
    alerts: [],
    score_points: 0,
    max_positive_points: maxPoints,
  });
}

function grant(state: FacilityState, grants: Partial<Record<FacilityActorId, string[]>>): void {
  for (const actor of ACTORS) state.actor_knowledge[actor].push(...(grants[actor] ?? []));
}

function actionMap(spec: FacilityArrivalSpec): Map<string, FacilityActionSpec> {
  return new Map(spec.actions.map((action) => [action.action_id, action]));
}

function eventMap(spec: FacilityArrivalSpec): Map<string, FacilityEventSpec> {
  return new Map(spec.events.map((event) => [event.event_id, event]));
}

function diagnosticsDue(state: FacilityState, context: FacilitySourceContext): number | null {
  const imaging = state.action_completed_at.order_imaging;
  const labs = state.action_completed_at.order_labs;
  if (imaging === undefined || labs === undefined) return null;
  return Math.max(imaging, labs) + context.spec.parameters.diagnostic_delay_seconds.value;
}

function duration(state: FacilityState, action: FacilityActionSpec, context: FacilitySourceContext): number {
  if (action.duration_mode === 'fixed') return action.duration_seconds;
  const due = diagnosticsDue(state, context);
  if (due === null) return -1;
  return Math.max(0, due - state.elapsed_seconds);
}

function addActionTransition(
  state: FacilityState,
  transition: FacilityTransition,
  action: FacilityActionSpec,
  context: FacilitySourceContext,
  errors: string[],
): FacilityState {
  const after = structuredClone(state);
  const expectedDuration = duration(state, action, context);
  if (expectedDuration < 0) errors.push(`action duration unavailable:${action.action_id}`);
  if (transition.completed_at_seconds - transition.started_at_seconds !== expectedDuration) {
    errors.push(`action duration mismatch:${action.action_id}`);
  }
  if (transition.started_at_seconds !== state.elapsed_seconds) errors.push(`action start time mismatch:${action.action_id}`);
  if (state.completed_action_ids.includes(action.action_id) && !action.repeatable) errors.push(`duplicate nonrepeatable action:${action.action_id}`);
  for (const prerequisite of action.prerequisites) {
    if (!state.completed_action_ids.includes(prerequisite)) errors.push(`missing prerequisite:${action.action_id}:${prerequisite}`);
  }
  for (const eventId of action.required_event_ids ?? []) {
    if (!state.fired_system_events.includes(eventId)) errors.push(`missing required event:${action.action_id}:${eventId}`);
  }
  after.revision += 1;
  after.elapsed_seconds += Math.max(0, expectedDuration);
  after.completed_action_ids.push(action.action_id);
  after.action_completed_at[action.action_id] = after.elapsed_seconds;
  if (action.phase_after) after.phase = action.phase_after;
  grant(after, action.knowledge_grants);
  let scoreDelta = 0;
  if (action.origin === 'operational_workflow') {
    if (action.source_action_id !== null) errors.push(`operational action has source binding:${action.action_id}`);
  } else {
    const sourceId = action.source_action_id;
    const source = sourceId ? sourceMap(context.scenario).get(sourceId) : undefined;
    if (!sourceId || !source) errors.push(`invalid source action binding:${action.action_id}`);
    if (source) {
      scoreDelta = source.points;
      after.score_points += source.points;
      after.completed_source_action_ids.push(source.id);
      after.source_action_completed_at[source.id] = after.elapsed_seconds;
      if (source.priority === 'unsafe') after.unsafe_source_action_ids.push(source.id);
    }
  }
  if (transition.score_delta !== scoreDelta) errors.push(`score delta mismatch:${action.action_id}`);
  if (action.action_id === 'review_diagnostics') after.alerts.push('Diagnostic results reviewed and casualty reassessed.');
  if (action.action_id === 'pain_management') after.alerts.push('Source-defined pain-management objective addressed without generating a drug, dose, or route.');
  if (action.terminal_effect) {
    after.terminal_status = action.terminal_effect;
    after.phase = 'complete';
    after.outcome = action.terminal_effect === 'completed'
      ? 'Closed-loop receiving handoff completed.'
      : `Unsafe source action selected: ${action.label}`;
  }
  return normalize(after);
}

function eventTriggerValid(
  state: FacilityState,
  transition: FacilityTransition,
  event: FacilityEventSpec,
  previous: FacilityTransition | undefined,
  context: FacilitySourceContext,
): boolean {
  switch (event.trigger.kind) {
    case 'initial': return transition.sequence === 1 && state.revision === 0;
    case 'after_action': return previous?.action_id === event.trigger.action_id;
    case 'elapsed_time_due': return state.elapsed_seconds >= event.trigger.at_elapsed_seconds
      && transition.completed_at_seconds >= event.trigger.at_elapsed_seconds;
    case 'diagnostics_due': {
      const due = diagnosticsDue(state, context);
      return due !== null && transition.completed_at_seconds >= due;
    }
    case 'timeout_due': return transition.completed_at_seconds === context.spec.parameters.timeout_seconds.value;
  }
}

function addEventTransition(
  state: FacilityState,
  transition: FacilityTransition,
  event: FacilityEventSpec,
  previous: FacilityTransition | undefined,
  context: FacilitySourceContext,
  errors: string[],
): FacilityState {
  if (!eventTriggerValid(state, transition, event, previous, context)) errors.push(`event trigger mismatch:${event.event_id}`);
  if (state.fired_system_events.includes(event.event_id)) errors.push(`duplicate system event:${event.event_id}`);
  const after = structuredClone(state);
  if (transition.completed_at_seconds < state.elapsed_seconds) errors.push(`event time regressed:${event.event_id}`);
  after.elapsed_seconds = transition.completed_at_seconds;
  after.revision += 1;
  after.fired_system_events.push(event.event_id);
  grant(after, event.knowledge_grants);
  if (event.reveal_source_hidden_findings) {
    after.revealed_hidden_findings.push(...context.scenario.patients.flatMap((patient) => patient.hidden_findings));
  }
  if (event.event_id === 'prearrival_notice') after.alerts.push('Pre-arrival notification received. Prepare for post-field-care reception.');
  if (event.event_id === 'second_casualty_inbound') after.alerts.push('Second casualty inbound. Preserve continuity while resources remain constrained.');
  if (event.event_id === 'diagnostics_ready') after.alerts.push('Ordered imaging and laboratory results are available for review.');
  if (event.terminal_effect) {
    after.terminal_status = event.terminal_effect;
    after.phase = 'complete';
    after.outcome = event.terminal_effect === 'timeout'
      ? 'Exercise ended at the source-bound timeout before closed-loop receiving handoff.'
      : `Exercise ended: ${event.terminal_effect}`;
  }
  return normalize(after);
}

function expectedSourceBinding(context: FacilitySourceContext): FacilitySession['source_binding'] {
  return {
    source_scenario_id: context.scenario.scenario_id,
    source_scenario_sha256: sha256Canonical(sourceProjection(context.scenario)),
    source_action_ids: flatten(context.scenario).map((action) => action.id).sort(),
    source_file_path: 'src/content/scenarios.ts',
    template_asset_id: 'template:ASK-D-001',
    template_record_sha256: context.template_record_sha256,
    content_registry_merkle_root: context.content_registry_merkle_root,
  };
}

function scoreBps(state: FacilityState): number {
  if (state.max_positive_points <= 0) return 0;
  return Math.min(10_000, Math.max(0, Math.round((state.score_points * 10_000) / state.max_positive_points)));
}

function stripCertificate(session: FacilitySession): Omit<FacilitySession, 'certificate'> {
  const { certificate: _certificate, ...rest } = session;
  return rest;
}

export function verifyFacilitySessionIndependent(
  session: FacilitySession,
  context: FacilitySourceContext,
  claimLedger: FacilityClaimLedger,
): string[] {
  const errors: string[] = [];
  if (session.schema_version !== '1.1.0') errors.push('session schema mismatch');
  if (canonicalJson(session.source_binding) !== canonicalJson(expectedSourceBinding(context))) errors.push('source binding mismatch');
  if (session.spec_sha256 !== sha256Canonical(context.spec)) errors.push('spec hash mismatch');
  if (session.certificate.claim_ledger_sha256 !== claimLedger.ledger_sha256) errors.push('claim ledger mismatch');
  if (session.authority.patient_care_use !== 'PROHIBITED') errors.push('patient-care boundary escalated');
  if (session.authority.automatic_clinical_rule_generation !== false) errors.push('automatic clinical rule generation enabled');

  let state = initialState(context);
  if (canonicalJson(state) !== canonicalJson(session.initial_state)) errors.push('initial state mismatch');
  const actions = actionMap(context.spec);
  const events = eventMap(context.spec);
  let previous: FacilityTransition | undefined;
  for (let index = 0; index < session.transitions.length; index += 1) {
    const transition = session.transitions[index]!;
    if (transition.sequence !== index + 1) errors.push(`transition sequence mismatch:${index + 1}`);
    if (transition.before_state_sha256 !== stateHash(state)) errors.push(`before hash mismatch:${transition.sequence}`);
    let expected: FacilityState;
    if (transition.kind === 'learner_action') {
      const action = transition.action_id ? actions.get(transition.action_id) : undefined;
      if (!action) {
        errors.push(`unknown learner action:${transition.action_id ?? 'null'}`);
        expected = state;
      } else {
        expected = addActionTransition(state, transition, action, context, errors);
      }
    } else {
      const event = transition.event_id ? events.get(transition.event_id) : undefined;
      if (!event) {
        errors.push(`unknown system event:${transition.event_id ?? 'null'}`);
        expected = state;
      } else {
        expected = addEventTransition(state, transition, event, previous, context, errors);
      }
    }
    if (!transition.wit_observation.process_only || transition.wit_observation.clinical_directive !== null) {
      errors.push(`WIT observation exceeded process-only scope:${transition.sequence}`);
    }
    if (transition.after_state_sha256 !== stateHash(expected)) errors.push(`after hash mismatch:${transition.sequence}`);
    if (canonicalJson(transition.state_after) !== canonicalJson(expected)) errors.push(`state snapshot mismatch:${transition.sequence}`);
    state = expected;
    previous = transition;
  }
  if (canonicalJson(state) !== canonicalJson(session.final_state)) errors.push('final state mismatch');
  if (session.normalized_score_bps !== scoreBps(state)) errors.push('score normalization mismatch');
  if (state.revealed_hidden_findings.length > 0 && !state.fired_system_events.includes('diagnostics_ready')) errors.push('hidden findings exposed before diagnostics');
  if (state.terminal_status === 'timeout' && session.transitions.at(-1)?.event_id !== 'timeout_reached') errors.push('timeout not event-sourced');
  if (state.terminal_status === 'completed' && session.transitions.at(-1)?.action_id !== 'complete_handoff') errors.push('completion lacks terminal handoff');

  const transitionRoot = merkleRoot(session.transitions.map((transition) => transition.after_state_sha256));
  if (session.certificate.transition_root_sha256 !== transitionRoot) errors.push('transition root mismatch');
  if (session.certificate.initial_state_sha256 !== stateHash(session.initial_state)) errors.push('initial certificate hash mismatch');
  if (session.certificate.final_state_sha256 !== stateHash(session.final_state)) errors.push('final certificate hash mismatch');
  if (session.certificate.session_sha256 !== sha256Canonical(stripCertificate(session))) errors.push('session certificate hash mismatch');
  if (!Object.values(session.certificate.checks).every(Boolean)) errors.push('certificate contains failed checks');

  const receiptIds = new Set<string>();
  for (const receipt of session.command_receipts) {
    if (receiptIds.has(receipt.command_id)) errors.push(`duplicate command receipt:${receipt.command_id}`);
    receiptIds.add(receipt.command_id);
    const matching = session.transitions.filter((transition) => transition.command_id === receipt.command_id);
    if (matching.length === 0) errors.push(`receipt has no transition:${receipt.command_id}`);
    if (matching.some((transition) => transition.action_id !== receipt.action_id)) errors.push(`receipt action mismatch:${receipt.command_id}`);
  }
  return uniqueSorted(errors);
}
