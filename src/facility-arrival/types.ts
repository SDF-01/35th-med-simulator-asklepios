import type { Scenario, Vitals } from '../types';

export type FacilityActorId = 'receiving_provider' | 'clinic_nurse' | 'diagnostics_tech' | 'wit_observer';
export type FacilityPhase = 'pre_arrival' | 'reception' | 'assessment' | 'diagnostics_pending' | 'results_review' | 'disposition' | 'complete';
export type FacilityTerminalStatus = 'active' | 'completed' | 'failed' | 'timeout';
export type FacilityActionOrigin = 'source_template' | 'operational_workflow';
export type FacilityTransitionKind = 'learner_action' | 'system_event';
export type FacilityCalibrationStatus = 'NOT_CALIBRATED' | 'SOURCE_BOUND';

export interface FacilityAuthority {
  deployment_scope: 'production_training_reference';
  patient_care_use: 'PROHIBITED';
  clinical_content_mode: 'INHERITED_REPOSITORY_TEMPLATE';
  operational_content_mode: 'DETERMINISTIC_EXERCISE_ORCHESTRATION';
  evidence_mode: 'IDENTITY_AND_SCOPE_ONLY';
  automatic_clinical_rule_generation: false;
}

export interface FacilityParameter {
  value: number;
  unit: string;
  origin: 'exercise_assumption' | 'exercise_policy' | 'source_template';
  calibration_status: FacilityCalibrationStatus;
  note: string;
}

export interface FacilityActorSpec {
  actor_id: FacilityActorId;
  role: string;
  initial_knowledge: string[];
}

export type FacilityKnowledgeGrants = Partial<Record<FacilityActorId, string[]>>;

export interface FacilityActionSpec {
  action_id: string;
  label: string;
  origin: FacilityActionOrigin;
  source_action_id: string | null;
  duration_mode: 'fixed' | 'until_diagnostics';
  duration_seconds: number;
  repeatable: boolean;
  prerequisites: string[];
  required_event_ids: string[];
  phase_after: FacilityPhase | null;
  knowledge_grants: FacilityKnowledgeGrants;
  wit_category: string;
  terminal_effect: Exclude<FacilityTerminalStatus, 'active'> | null;
  clinical_detail_policy: 'NO_GENERATED_DRUG_DOSE_OR_ROUTE' | null;
}

export type FacilityEventTrigger =
  | { kind: 'initial' }
  | { kind: 'after_action'; action_id: string }
  | { kind: 'elapsed_time_due'; at_elapsed_seconds: number }
  | { kind: 'diagnostics_due' }
  | { kind: 'timeout_due' };

export interface FacilityEventSpec {
  event_id: string;
  label: string;
  trigger: FacilityEventTrigger;
  knowledge_grants: FacilityKnowledgeGrants;
  reveal_source_hidden_findings: boolean;
  terminal_effect: Exclude<FacilityTerminalStatus, 'active'> | null;
  wit_category: string;
}

export interface FacilityArrivalSpec {
  schema_version: '1.1.0';
  profile_id: string;
  example_id: string;
  title: string;
  source_scenario_id: 'ASK-D-001';
  care_continuum_phase: 'post_cuf_tfc_facility_reception';
  authority: FacilityAuthority;
  parameters: {
    diagnostic_delay_seconds: FacilityParameter;
    pass_threshold_bps: FacilityParameter;
    timeout_seconds: FacilityParameter;
  };
  actors: FacilityActorSpec[];
  actions: FacilityActionSpec[];
  events: FacilityEventSpec[];
  completion: {
    required_source_action_priorities: Array<'critical' | 'important'>;
    required_operational_actions: string[];
    required_event_ids: string[];
  };
  canonical_command_sequence: string[];
  sequence_assurance: {
    selected_three_event_sequences: string[][];
  };
}

export interface FacilitySourceContext {
  scenario: Scenario;
  spec: FacilityArrivalSpec;
  template_record_sha256: string;
  content_registry_merkle_root: string;
}

export interface FacilitySourceBinding {
  source_scenario_id: string;
  source_scenario_sha256: string;
  source_action_ids: string[];
  source_file_path: string;
  template_asset_id: string;
  template_record_sha256: string;
  content_registry_merkle_root: string;
}

export interface FacilityState {
  revision: number;
  elapsed_seconds: number;
  phase: FacilityPhase;
  terminal_status: FacilityTerminalStatus;
  outcome: string | null;
  completed_action_ids: string[];
  completed_source_action_ids: string[];
  unsafe_source_action_ids: string[];
  fired_system_events: string[];
  source_action_completed_at: Record<string, number>;
  action_completed_at: Record<string, number>;
  revealed_hidden_findings: string[];
  actor_knowledge: Record<FacilityActorId, string[]>;
  alerts: string[];
  score_points: number;
  max_positive_points: number;
}

export interface FacilityWitObservation {
  category: string;
  statement: string;
  process_only: true;
  clinical_directive: null;
}

export interface FacilityTransition {
  sequence: number;
  transition_id: string;
  kind: FacilityTransitionKind;
  actor_id: FacilityActorId | 'system';
  command_id: string | null;
  action_id: string | null;
  event_id: string | null;
  label: string;
  source_action_id: string | null;
  origin: FacilityActionOrigin | 'system_event';
  started_at_seconds: number;
  completed_at_seconds: number;
  score_delta: number;
  state_after: FacilityState;
  wit_observation: FacilityWitObservation;
  before_state_sha256: string;
  after_state_sha256: string;
}

export interface FacilityCommand {
  command_id: string;
  action_id: string;
  expected_revision: number;
}

export interface FacilityCommandReceipt {
  command_id: string;
  action_id: string;
  command_sha256: string;
  first_transition_sequence: number | null;
  final_transition_sequence: number | null;
}

export interface FacilityActionDecisionTrace {
  action_id: string;
  enabled: boolean;
  conditions: Record<string, boolean>;
  rejection_reasons: string[];
}

export interface FacilityCertificateChecks {
  source_binding_matches: boolean;
  source_action_subset_preserved: boolean;
  required_source_actions_complete: boolean;
  unsafe_source_actions_fail_closed: boolean;
  diagnostics_precede_hidden_findings: boolean;
  terminal_handoff_reached: boolean;
  patient_care_use_prohibited: boolean;
  wit_observations_process_only: boolean;
  replay_chain_complete: boolean;
  timeout_is_event_sourced: boolean;
  transition_states_bound: boolean;
  score_within_bounds: boolean;
  actor_knowledge_authorized: boolean;
  uncalibrated_parameters_disclosed: boolean;
}

export interface FacilityCertificate {
  certificate_version: '1.0.0';
  source_binding_sha256: string;
  spec_sha256: string;
  initial_state_sha256: string;
  final_state_sha256: string;
  transition_root_sha256: string;
  replay_root_sha256: string;
  claim_ledger_sha256: string;
  checks: FacilityCertificateChecks;
  session_sha256: string;
}

export interface FacilitySession {
  schema_version: '1.1.0';
  example_id: string;
  title: string;
  facility_profile: string;
  care_continuum_phase: string;
  authority: FacilityAuthority;
  source_binding: FacilitySourceBinding;
  spec_sha256: string;
  initial_patient_snapshot: {
    presentation: string;
    vitals: Vitals;
    hidden_findings_count: number;
  };
  initial_state: FacilityState;
  transitions: FacilityTransition[];
  command_receipts: FacilityCommandReceipt[];
  final_state: FacilityState;
  normalized_score_bps: number;
  certificate: FacilityCertificate;
}

export interface FacilityCommandResult {
  session: FacilitySession;
  idempotent: boolean;
}

export type FacilityClaimOrigin = 'inherited_source_template' | 'exercise_assumption' | 'scope_reference';
export interface FacilityClaimRecord {
  claim_id: string;
  field_path: string;
  atomic_claim: string;
  origin_class: FacilityClaimOrigin;
  relation: 'INHERITED' | 'ASSUMPTION' | 'SCOPE_AND_PROCESS_REFERENCE';
  evidence_entailment: 'NOT_APPLICABLE' | 'NOT_ADJUDICATED';
  contradiction_status: 'NOT_APPLICABLE' | 'NOT_SEARCHED';
  clinical_authority: 'INHERITED_ONLY' | 'NOT_GRANTED';
  source_pointer: string;
  record_sha256: string;
}

export interface FacilityClaimLedger {
  schema_version: '1.0.0';
  example_id: string;
  records: FacilityClaimRecord[];
  ledger_sha256: string;
}

export interface FacilityAar {
  schema_version: '1.1.0';
  example_id: string;
  session_sha256: string;
  terminal_status: FacilityTerminalStatus;
  normalized_score_bps: number;
  passed: boolean;
  pass_threshold_bps: number;
  source_action_coverage: {
    required_completed: string[];
    required_missing: string[];
    optional_completed: string[];
    optional_not_exercised: string[];
  };
  strengths: string[];
  improvement_opportunities: string[];
  wit_observation_summary: FacilityWitObservation[];
  counterfactual_boundaries: {
    available_branches: string[];
    causal_claims_allowed: false;
    note: string;
  };
  validity_ledger: {
    demonstrated: string[];
    open: string[];
  };
  aar_sha256: string;
}
