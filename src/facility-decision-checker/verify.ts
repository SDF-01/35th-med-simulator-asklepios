import { sha256Canonical } from '../scenario-core/hash';
import type {
  FacilityDecisionIntegritySession,
  FacilityDecisionLearnerView,
  FacilityDecisionProfile,
  FacilityDecisionSubmission,
  FacilityDecisionValue,
} from '../facility-decision/types';

const REQUIRED_SOURCE_ACTIONS = new Set([
  'primary_assessment',
  'order_imaging',
  'order_labs',
  'differential',
  'monitor_vitals',
  'escalation',
]);

function unique(values: readonly string[]): string[] {
  return [...new Set(values)].sort();
}

function rootPayload(session: FacilityDecisionIntegritySession): unknown {
  const { decision_root_sha256: _root, ...withoutRoot } = session;
  return withoutRoot;
}

function validateSubmissionShape(
  submission: FacilityDecisionSubmission,
  profile: FacilityDecisionProfile,
): string[] {
  const errors: string[] = [];
  const contract = profile.decisions.find((candidate) => candidate.decision_id === submission.decision_id);
  if (!contract) return [`unknown decision:${submission.decision_id}`];
  const allowed = new Set(contract.fields.map((field) => field.field_id));
  for (const key of Object.keys(submission.values)) if (!allowed.has(key)) errors.push(`unknown submission field:${submission.decision_id}:${key}`);
  for (const field of contract.fields) {
    const value = submission.values[field.field_id];
    if (value === undefined) {
      if (field.required) errors.push(`missing field:${submission.decision_id}:${field.field_id}`);
      continue;
    }
    if (field.type === 'boolean' && typeof value !== 'boolean') errors.push(`field type:${submission.decision_id}:${field.field_id}`);
    if ((field.type === 'text' || field.type === 'choice') && typeof value !== 'string') errors.push(`field type:${submission.decision_id}:${field.field_id}`);
    if ((field.type === 'multi_choice' || field.type === 'list') && (!Array.isArray(value) || value.some((item) => typeof item !== 'string'))) {
      errors.push(`field type:${submission.decision_id}:${field.field_id}`);
    }
    if (typeof value === 'string') {
      if (field.min_length !== undefined && value.trim().length < field.min_length) errors.push(`field min length:${submission.decision_id}:${field.field_id}`);
      if (field.allowed_values && !field.allowed_values.includes(value)) errors.push(`field allowed value:${submission.decision_id}:${field.field_id}`);
    }
    if (Array.isArray(value)) {
      if (field.min_items !== undefined && unique(value).length < field.min_items) errors.push(`field min items:${submission.decision_id}:${field.field_id}`);
      if (field.allowed_values && value.some((item) => !field.allowed_values?.includes(item))) errors.push(`field allowed values:${submission.decision_id}:${field.field_id}`);
      if (field.required_values && field.required_values.some((item) => !value.includes(item))) errors.push(`field required values:${submission.decision_id}:${field.field_id}`);
    }
    if (field.must_equal !== undefined && value !== field.must_equal) errors.push(`field exact value:${submission.decision_id}:${field.field_id}`);
  }
  if (contract.treatment_policy_id) {
    const policy = profile.treatment_policies.find((candidate) => candidate.treatment_id === contract.treatment_policy_id);
    if (!policy) errors.push(`unknown treatment policy:${contract.treatment_policy_id}`);
    else {
      for (const forbidden of policy.forbidden_submission_keys) {
        if (Object.prototype.hasOwnProperty.call(submission.values, forbidden)) errors.push(`forbidden treatment field:${forbidden}`);
      }
      if (policy.concrete_treatment_allowed !== false) errors.push(`concrete treatment policy active:${policy.treatment_id}`);
    }
  }
  return errors;
}

export function verifyFacilityDecisionProfile(profile: FacilityDecisionProfile): string[] {
  const errors: string[] = [];
  if (profile.source_scenario_id !== 'ASK-D-001') errors.push('source scenario differs');
  if (profile.authority.patient_care_use !== 'PROHIBITED') errors.push('patient-care authority escalated');
  if (profile.authority.concrete_treatment_activation !== false) errors.push('concrete treatment activation escalated');
  if (profile.authority.operational_parameters_calibrated !== false) errors.push('operational parameters falsely calibrated');
  const learner = profile.ui_modes.learner_assessment;
  for (const [key, value] of Object.entries(learner)) if (value !== false) errors.push(`learner assessment leakage policy:${key}`);
  const mapped = new Set(profile.decisions.map((decision) => decision.source_action_id).filter((value): value is string => typeof value === 'string'));
  for (const sourceAction of REQUIRED_SOURCE_ACTIONS) if (!mapped.has(sourceAction)) errors.push(`required source decision missing:${sourceAction}`);
  for (const event of profile.operational_model.world_events) {
    if (event.calibration_status !== 'NOT_CALIBRATED') errors.push(`world event falsely calibrated:${event.event_id}`);
    if (Object.prototype.hasOwnProperty.call(event, 'trigger_action_id')) errors.push(`world event action-coupled:${event.event_id}`);
  }
  for (const policy of profile.treatment_policies) {
    if (policy.concrete_treatment_allowed !== false) errors.push(`concrete treatment allowed:${policy.treatment_id}`);
    if (policy.governing_rule_status !== 'NOT_ADJUDICATED') errors.push(`treatment rule self-adjudicated:${policy.treatment_id}`);
    if (policy.effect_model_status !== 'BLOCKED') errors.push(`treatment effect model activated:${policy.treatment_id}`);
  }
  if (profile.operational_model.patient_observation_policy.dynamic_physiology_validated !== false) errors.push('dynamic physiology falsely validated');
  if (profile.operational_model.patient_observation_policy.latent_state_exposed_to_learner !== false) errors.push('latent state exposed to learner');
  const resourceIds = new Set<string>();
  for (const resource of profile.operational_model.resources) {
    if (resourceIds.has(resource.resource_id)) errors.push(`duplicate resource:${resource.resource_id}`);
    resourceIds.add(resource.resource_id);
    if (!Number.isInteger(resource.capacity) || resource.capacity < 1) errors.push(`resource capacity invalid:${resource.resource_id}`);
    if (resource.queue_policy !== 'FIFO') errors.push(`resource queue policy differs:${resource.resource_id}`);
    if (resource.calibration_status !== 'NOT_CALIBRATED') errors.push(`resource falsely calibrated:${resource.resource_id}`);
  }
  for (const diagnostic of profile.diagnostic_catalog) if (!resourceIds.has(diagnostic.resource_id)) errors.push(`diagnostic resource missing:${diagnostic.order_code}`);
  const repeatable = profile.decisions.filter((decision) => decision.repeatable).map((decision) => decision.decision_id).sort();
  if (repeatable.length !== 1 || repeatable[0] !== 'wait_60') errors.push('repeatable decision inventory differs');
  const sequenceNames = Object.keys(profile.assurance.reference_sequences).sort();
  if (sequenceNames.join(',') !== 'alternate,canonical') errors.push('reference sequence inventory differs');
  if (profile.assurance.ordered_pair_obligations.length < 10) errors.push('ordered pair obligations weakened');
  if (profile.assurance.ordered_triple_obligations.length < 5) errors.push('ordered triple obligations weakened');
  return unique(errors);
}

export function verifyFacilityDecisionSession(
  session: FacilityDecisionIntegritySession,
  profile: FacilityDecisionProfile,
): string[] {
  const errors = verifyFacilityDecisionProfile(profile);
  if (session.profile_id !== profile.profile_id) errors.push('profile id mismatch');
  if (session.decision_root_sha256 !== sha256Canonical(rootPayload(session))) errors.push('decision root mismatch');
  const submissionIds = new Set<string>();
  const decisionIds = new Set<string>();
  for (const submission of session.submissions) {
    if (submissionIds.has(submission.submission_id)) errors.push(`duplicate submission id:${submission.submission_id}`);
    submissionIds.add(submission.submission_id);
    const contract = profile.decisions.find((candidate) => candidate.decision_id === submission.decision_id);
    if (decisionIds.has(submission.decision_id) && !contract?.repeatable) errors.push(`duplicate decision submission:${submission.decision_id}`);
    decisionIds.add(submission.decision_id);
    errors.push(...validateSubmissionShape(submission, profile));
  }
  const completedDecisionIds = new Set(session.completed_decision_ids);
  const completedFacilityActionIds = new Set(session.facility_session.final_state.completed_action_ids);
  for (const decisionId of completedDecisionIds) {
    const contract = profile.decisions.find((candidate) => candidate.decision_id === decisionId);
    if (!contract) errors.push(`completed decision unknown:${decisionId}`);
    else if (!completedFacilityActionIds.has(contract.facility_action_id)) {
      errors.push(`decision/facility completion mismatch:${decisionId}`);
    }
  }
  for (const actionId of completedFacilityActionIds) {
    const contract = profile.decisions.find((candidate) => candidate.facility_action_id === actionId);
    if (!contract || !completedDecisionIds.has(contract.decision_id)) {
      errors.push(`facility/decision completion mismatch:${actionId}`);
    }
  }
  let priorRecordSha256 = sha256Canonical([]);
  if (session.decision_records.length !== session.submissions.length) errors.push('decision record/submission count differs');
  for (let index = 0; index < session.decision_records.length; index += 1) {
    const record = session.decision_records[index];
    const { record_sha256: _recordHash, ...recordWithoutHash } = record;
    if (record.sequence !== index + 1) errors.push(`decision record sequence mismatch:${record.record_id}`);
    if (record.prior_record_sha256 !== priorRecordSha256) errors.push(`decision record predecessor mismatch:${record.record_id}`);
    if (record.record_sha256 !== sha256Canonical(recordWithoutHash)) errors.push(`decision record hash mismatch:${record.record_id}`);
    const submission = session.submissions.find((candidate) => candidate.submission_id === record.submission_id);
    if (!submission || sha256Canonical(submission) !== record.payload_sha256) errors.push(`decision record payload mismatch:${record.record_id}`);
    priorRecordSha256 = record.record_sha256;
  }
  if (session.decision_chain_root_sha256 !== priorRecordSha256) errors.push('decision chain root mismatch');
  for (const order of session.orders) {
    const resource = profile.operational_model.resources.find((candidate) => candidate.resource_id === order.resource_id);
    if (!resource) errors.push(`order resource unknown:${order.order_id}`);
    if (order.started_at_seconds < order.placed_at_seconds) errors.push(`order starts before placement:${order.order_id}`);
    if (order.due_at_seconds < order.started_at_seconds) errors.push(`order due before start:${order.order_id}`);
    if (order.status === 'result_available' && order.completed_at_seconds === null) errors.push(`available order lacks completion:${order.order_id}`);
  }
  for (const resourceState of session.resources) {
    const spec = profile.operational_model.resources.find((candidate) => candidate.resource_id === resourceState.resource_id);
    if (!spec) errors.push(`unknown resource state:${resourceState.resource_id}`);
    if (resourceState.active_order_ids.length > resourceState.capacity) errors.push(`resource capacity exceeded:${resourceState.resource_id}`);
  }
  for (const result of session.results) {
    if (!session.orders.some((order) => order.order_id === result.order_id && order.order_code === result.order_code && order.status === 'result_available')) {
      errors.push(`result lacks matching order:${result.result_id}`);
    }
  }
  if (session.results.length > 0 && !session.facility_session.final_state.fired_system_events.includes('diagnostics_ready')) {
    errors.push('results exist before facility diagnostics event');
  }
  const handoffComplete = session.handoff.responsibility_transferred_at_seconds !== null;
  if (handoffComplete && (!session.handoff.receiver_acknowledged || !session.handoff.questions_offered || !session.handoff.sender_confirmed)) {
    errors.push('handoff responsibility transferred without closed loop');
  }
  if (session.facility_session.final_state.terminal_status === 'completed' && !handoffComplete) {
    errors.push('completed facility session lacks closed-loop handoff');
  }
  for (const result of session.results) {
    const catalog = profile.diagnostic_catalog.find((candidate) => candidate.result_id === result.result_id);
    if (!catalog) errors.push(`unknown diagnostic result:${result.result_id}`);
    else if (catalog.order_code !== result.order_code) errors.push(`diagnostic order/result mismatch:${result.result_id}`);
  }
  const scheduledIds = new Set(profile.operational_model.world_events.map((event) => event.event_id));
  for (const event of session.visible_world_events) {
    if (!scheduledIds.has(event.event_id)) errors.push(`unknown world event:${event.event_id}`);
    if (event.observed_at_seconds < event.visible_at_seconds) errors.push(`world event visible too early:${event.event_id}`);
  }
  return unique(errors);
}

export function verifyFacilityDecisionLearnerView(view: FacilityDecisionLearnerView): string[] {
  if (view.ui_mode !== 'learner_assessment' && view.ui_mode !== 'learner_teaching') return [];
  const errors: string[] = [];
  if (view.instructor !== undefined) errors.push('learner view contains instructor data');
  if (view.demo !== undefined) errors.push('learner view contains demo controls');
  const serialized = JSON.stringify(view);
  const forbidden = [
    'normalized_source_score_bps', 'source_binding', 'facility_certificate',
    'wit_observations', 'source_action_id', 'source_origin',
    'autoplay_available', 'completed_replay_available', 'branch_controls',
  ];
  for (const token of forbidden) if (serialized.includes(`\"${token}\"`)) errors.push(`learner leakage:${token}`);
  return unique(errors);
}

export function containsConcreteTreatmentFields(values: Record<string, FacilityDecisionValue>): boolean {
  const keys = new Set(Object.keys(values));
  return ['medication', 'medication_name', 'dose', 'dose_unit', 'route', 'procedure', 'procedure_code', 'device_setting']
    .some((key) => keys.has(key));
}
