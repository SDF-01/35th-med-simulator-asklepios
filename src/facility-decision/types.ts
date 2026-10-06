import type { FacilitySession, FacilitySourceContext } from '../facility-arrival/types';

export type FacilityDecisionUiMode =
  | 'learner_assessment'
  | 'learner_teaching'
  | 'instructor'
  | 'stakeholder_demo';

export type FacilityDecisionCategory =
  | 'handoff_reception'
  | 'assessment'
  | 'monitoring'
  | 'clinical_reasoning'
  | 'diagnostic_order'
  | 'treatment_intent'
  | 'team_coordination'
  | 'operational_wait'
  | 'result_interpretation'
  | 'disposition'
  | 'documentation'
  | 'closed_loop_handoff'
  | 'high_risk_disposition'
  | 'high_risk_treatment_change';

export type FacilityDecisionPublicCategory = Exclude<
  FacilityDecisionCategory,
  'high_risk_disposition' | 'high_risk_treatment_change'
>;

export type FacilityDecisionFieldType = 'text' | 'boolean' | 'choice' | 'multi_choice' | 'list';
export type FacilityDecisionValue = string | boolean | string[];

export interface FacilityDecisionFieldSpec {
  field_id: string;
  label: string;
  type: FacilityDecisionFieldType;
  required: boolean;
  min_length?: number;
  min_items?: number;
  allowed_values?: string[];
  required_values?: string[];
  must_equal?: string | boolean;
}

export interface FacilityDecisionGoverningSource {
  authority_class:
    | 'INHERITED_TEMPLATE'
    | 'OPERATIONAL_STANDARD'
    | 'EXERCISE_WORKFLOW'
    | 'SOURCE_RESULT_INTERPRETATION';
  source_id: string;
  status:
    | 'SOURCE_BOUND'
    | 'STRUCTURAL_ONLY'
    | 'NOT_CALIBRATED'
    | 'ABSTRACT_OBJECTIVE_ONLY'
    | 'SOURCE_BOUND_LIMITED_GRANULARITY'
    | 'SOURCE_DEFINED_UNSAFE';
}

export interface FacilityDecisionContract {
  decision_id: string;
  facility_action_id: string;
  source_action_id: string | null;
  category: FacilityDecisionCategory;
  learner_label: string;
  demo_label: string;
  prerequisites: string[];
  required_world_events: string[];
  fields: FacilityDecisionFieldSpec[];
  creates_orders?: string[];
  requires_results?: string[];
  treatment_policy_id?: string;
  scoring_dimensions: string[];
  high_risk: boolean;
  repeatable: boolean;
  governing_source: FacilityDecisionGoverningSource;
}

export interface FacilityDecisionUiPolicy {
  show_live_score: boolean;
  show_source_points: boolean;
  show_source_origin: boolean;
  show_provenance: boolean;
  show_wit: boolean;
  show_autoplay: boolean;
  show_completed_replay: boolean;
  show_correctness_labels: boolean;
  show_disabled_reasons: boolean;
}

export interface FacilityDecisionWorldEventSpec {
  event_id: string;
  at_elapsed_seconds: number;
  calibration_status: 'NOT_CALIBRATED';
  note: string;
}

export interface FacilityDecisionResourceSpec {
  resource_id: string;
  capacity: number;
  queue_policy: 'FIFO';
  service_duration_seconds: number;
  calibration_status: 'NOT_CALIBRATED';
  note: string;
}

export interface FacilityDecisionResourceState {
  resource_id: string;
  capacity: number;
  active_order_ids: string[];
  queued_order_ids: string[];
  calibration_status: 'NOT_CALIBRATED';
}

export interface FacilityDecisionDiagnosticSpec {
  order_code: string;
  facility_action_id: string;
  resource_id: string;
  result_id: string;
  source_pointer: string;
  result_granularity: 'SOURCE_DIAGNOSIS_SUMMARY_ONLY' | 'SOURCE_QUALITATIVE_SUMMARY_ONLY';
  learner_result: string;
  limitation: string;
}

export interface FacilityTreatmentPolicy {
  treatment_id: string;
  facility_action_id: string;
  activation_state: 'ABSTRACT_OBJECTIVE_ONLY' | 'BLOCKED_MISSING_ELIGIBILITY_MODEL';
  concrete_treatment_allowed: false;
  forbidden_submission_keys: string[];
  activation_requirements_for_future_concrete_content: string[];
  governing_rule_status: 'NOT_ADJUDICATED';
  effect_model_status: 'BLOCKED';
}

export interface FacilityDecisionProfile {
  schema_version: '1.0.0';
  profile_id: string;
  source_scenario_id: 'ASK-D-001';
  care_phase: 'post_cuf_tfc_facility_reception';
  authority: {
    deployment_scope: 'production_training_reference';
    patient_care_use: 'PROHIBITED';
    clinical_rule_source: 'INHERITED_REPOSITORY_TEMPLATE';
    concrete_treatment_activation: false;
    operational_parameters_calibrated: false;
  };
  structural_sources: Array<{
    source_id: string;
    purpose: string;
    url: string;
  }>;
  ui_modes: Record<FacilityDecisionUiMode, FacilityDecisionUiPolicy>;
  operational_model: {
    world_events: FacilityDecisionWorldEventSpec[];
    information_staleness_seconds: number;
    information_staleness_calibration_status: 'NOT_CALIBRATED';
    resources: FacilityDecisionResourceSpec[];
    patient_observation_policy: {
      mode: 'SOURCE_BOUND_OBSERVATIONS_ONLY';
      dynamic_physiology_validated: false;
      latent_state_exposed_to_learner: false;
      note: string;
    };
  };
  diagnostic_catalog: FacilityDecisionDiagnosticSpec[];
  treatment_policies: FacilityTreatmentPolicy[];
  decisions: FacilityDecisionContract[];
  assurance: {
    reference_sequences: Record<'canonical' | 'alternate', string[]>;
    ordered_pair_obligations: string[][];
    ordered_triple_obligations: string[][];
    bounded_exploration: {
      max_decision_depth: number;
      max_repeatable_waits: number;
      required_terminal_witnesses: string[];
    };
  };
  dimension_policy: {
    dimensions: string[];
    learner_live_display: false;
    single_composite_score_is_clinical_validity: false;
    weights_calibration_status: 'NOT_CALIBRATED';
  };
}

export interface FacilityDecisionSubmission {
  submission_id: string;
  decision_id: string;
  expected_revision: number;
  values: Record<string, FacilityDecisionValue>;
}

export interface FacilityDecisionValidationResult {
  decision_id: string;
  valid: boolean;
  errors: string[];
  missing_fields: string[];
  forbidden_fields: string[];
}

export interface FacilityDecisionOrder {
  order_id: string;
  order_code: string;
  decision_id: string;
  placed_at_seconds: number;
  status: 'queued' | 'in_progress' | 'completed_pending_release' | 'result_available';
  resource_id: string;
  queued_at_seconds: number;
  started_at_seconds: number;
  due_at_seconds: number;
  completed_at_seconds: number | null;
  source_pointer: string;
}

export interface FacilityDecisionResult {
  result_id: string;
  order_id: string;
  order_code: string;
  available_at_seconds: number;
  learner_result: string;
  source_pointer: string;
  granularity: FacilityDecisionDiagnosticSpec['result_granularity'];
  limitation: string;
}

export interface FacilityDecisionWorldEvent {
  event_id: string;
  visible_at_seconds: number;
  observed_at_seconds: number;
  calibration_status: 'NOT_CALIBRATED';
  note: string;
}


export interface FacilityDecisionRecord {
  sequence: number;
  record_id: string;
  submission_id: string;
  decision_id: string;
  actor_id: 'receiving_provider';
  payload_sha256: string;
  prior_record_sha256: string;
  before_state_sha256: string;
  after_state_sha256: string;
  started_at_seconds: number;
  completed_at_seconds: number;
  record_sha256: string;
}

export interface FacilityDecisionHandoffState {
  sender_identity: string | null;
  receiver_identity: string | null;
  receiver_acknowledged: boolean;
  questions_offered: boolean;
  sender_confirmed: boolean;
  responsibility_transferred_at_seconds: number | null;
}

export interface FacilityDecisionDimensionRecord {
  dimension_id: string;
  completed_decision_ids: string[];
  safety_events: string[];
  calibration_status: 'NOT_CALIBRATED';
}

export interface FacilityDecisionIntegritySession {
  schema_version: '1.0.0';
  profile_id: string;
  ui_mode: FacilityDecisionUiMode;
  revision: number;
  facility_session: FacilitySession;
  submissions: FacilityDecisionSubmission[];
  decision_records: FacilityDecisionRecord[];
  completed_decision_ids: string[];
  orders: FacilityDecisionOrder[];
  resources: FacilityDecisionResourceState[];
  results: FacilityDecisionResult[];
  visible_world_events: FacilityDecisionWorldEvent[];
  handoff: FacilityDecisionHandoffState;
  information_state: {
    last_structured_reassessment_seconds: number | null;
    reassessment_due: boolean;
    staleness_seconds: number;
  };
  dimensions: FacilityDecisionDimensionRecord[];
  decision_chain_root_sha256: string;
  decision_root_sha256: string;
}

export interface FacilityDecisionContext {
  facility: FacilitySourceContext;
  profile: FacilityDecisionProfile;
}

export type FacilityDecisionFieldPresentation = Pick<
  FacilityDecisionFieldSpec,
  'field_id' | 'label' | 'type' | 'required' | 'allowed_values'
>;

export interface FacilityDecisionActionView {
  decision_id: string;
  label: string;
  category: FacilityDecisionPublicCategory;
  enabled: boolean;
  fields: FacilityDecisionFieldPresentation[];
  disabled_reasons?: string[];
  requires_deliberate_confirmation?: true;
  source_action_id?: string | null;
  source_origin?: FacilityDecisionGoverningSource;
}

export interface FacilityDecisionLearnerView {
  schema_version: '1.0.0';
  ui_mode: FacilityDecisionUiMode;
  terminal_status: FacilitySession['final_state']['terminal_status'];
  elapsed_seconds: number;
  phase: FacilitySession['final_state']['phase'];
  completed_decision_count: number;
  initial_patient_snapshot: Pick<FacilitySession['initial_patient_snapshot'], 'presentation' | 'vitals'>;
  actions: FacilityDecisionActionView[];
  orders: Array<Pick<FacilityDecisionOrder, 'order_code' | 'status' | 'placed_at_seconds' | 'resource_id' | 'started_at_seconds' | 'due_at_seconds'>>;
  resources: Array<{ resource_id: string; active_order_count: number; queued_order_count: number }>;
  results: Array<Pick<FacilityDecisionResult, 'result_id' | 'order_code' | 'available_at_seconds' | 'learner_result' | 'limitation'>>;
  visible_world_events: FacilityDecisionWorldEvent[];
  information_state: FacilityDecisionIntegritySession['information_state'];
  handoff_status: {
    receiver_acknowledged: boolean;
    questions_offered: boolean;
    sender_confirmed: boolean;
    responsibility_transferred: boolean;
  };
  terminal_summary?: {
    completed_decisions: string[];
    dimensions: FacilityDecisionDimensionRecord[];
  };
  instructor?: {
    normalized_source_score_bps: number;
    source_binding: FacilitySession['source_binding'];
    facility_certificate: FacilitySession['certificate'];
    wit_observations: FacilitySession['transitions'][number]['wit_observation'][];
    profile_authority: FacilityDecisionProfile['authority'];
    completed_replay_available: boolean;
    decision_timeline: Array<Pick<FacilityDecisionRecord, 'record_id' | 'sequence' | 'decision_id' | 'started_at_seconds' | 'completed_at_seconds'>>;
  };
  demo?: {
    autoplay_available: true;
    completed_replay_available: true;
    branch_controls: string[];
  };
}
