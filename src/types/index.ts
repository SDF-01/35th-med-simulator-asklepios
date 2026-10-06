import type { BodyInjuryHighlight } from '@/types/bodyInjury';

export type MedicalSection =
  | 'A_field_reaction_triage_incident_response'
  | 'B_transport'
  | 'C_patient_administration'
  | 'D_clinical'
  | 'E_radiology'
  | 'F_lab'
  | 'G_pharmacy'
  | 'H_surgery'
  | 'I_mcc_ucc';

export type SkillLevel = 'beginner' | 'intermediate' | 'advanced' | 'expert';

export type UserRole =
  | 'all_service_member'
  | 'combat_lifesaver'
  | 'medic_or_technician'
  | 'nurse'
  | 'provider'
  | 'admin_staff'
  | 'lab_tech'
  | 'radiology_tech'
  | 'pharmacist'
  | 'mcc_ucc_controller';

export type TrainingMode = 'trainee' | 'coaching' | 'evaluator';

export type CommsStatus = 'normal' | 'degraded' | 'intermittent' | 'unavailable';

export type ResourceStatus = 'normal' | 'constrained' | 'overwhelmed';

export type SessionStatus = 'active' | 'completed' | 'failed' | 'timeout';

export type ActionPriority = 'critical' | 'important' | 'optional' | 'unsafe';

export type MarchStep =
  | 'massive_hemorrhage'
  | 'airway'
  | 'respiration'
  | 'circulation'
  | 'hypothermia_head'
  | 'pain'
  | 'antibiotics'
  | 'wounds'
  | 'splinting';

export interface Vitals {
  hr: number;
  bp_systolic: number;
  bp_diastolic: number;
  rr: number;
  spo2: number;
  temp_c: number;
  gcs: number;
}

export interface ExpectedAction {
  id: string;
  label: string;
  priority: ActionPriority;
  synonyms: string[];
  points: number;
  marchStep?: MarchStep;
}

export interface ScenarioPatient {
  patient_id: string;
  age_band: string;
  sex: string;
  role_context: string;
  mechanism_of_injury: string;
  initial_presentation: string;
  injury_profile_refs: string[];
  initial_vitals: Vitals;
  hidden_findings: string[];
  deterioration_timeline: string[];
  visible_body_zones?: BodyInjuryHighlight[];
}

export interface OperationalContext {
  location_type: string;
  threat_type: string;
  weather: string;
  visibility: string;
  comms_status: CommsStatus;
  resource_status: ResourceStatus;
  narrative: string;
}

export interface Scenario {
  scenario_id: string;
  title: string;
  version: string;
  fictionalization_notice: string;
  operational_context: OperationalContext;
  training_objectives: string[];
  target_section: MedicalSection;
  target_role: UserRole;
  skill_level: SkillLevel;
  difficulty: SkillLevel;
  threat_type: string;
  casualty_count: number;
  patients: ScenarioPatient[];
  expected_actions: {
    critical: ExpectedAction[];
    important: ExpectedAction[];
    optional: ExpectedAction[];
    unsafe: ExpectedAction[];
  };
  end_conditions: {
    success: string[];
    failure: string[];
    timeout_minutes: number;
  };
  aar_teaching_points: string[];
}

export interface RecognizedAction {
  actionId: string;
  label: string;
  priority: ActionPriority;
  confidence: number;
  matchedText: string;
}

export interface ScoringTrace {
  actionId: string;
  label: string;
  points: number;
  reason: string;
  timestamp: number;
}

export type FeedAudience = 'all' | 'provider' | 'wit';

export interface FeedEntry {
  id: string;
  timestamp: number;
  type: 'system' | 'user' | 'patient' | 'alert' | 'evaluation' | 'response';
  content: string;
  /** Optional card title within a feed entry */
  heading?: string;
  /** Optional bullet list below content */
  bullets?: string[];
  /** Who should see this entry — defaults to all */
  audience?: FeedAudience;
  turn?: number;
  patient_id?: string;
  /** Provider prompt that triggered this update (WIT contextual view) */
  trigger_prompt?: string;
}

export interface SupplyItem {
  id: string;
  label: string;
  quantity: number;
  maxQuantity: number;
  category: 'hemorrhage' | 'airway' | 'breathing' | 'circulation' | 'medication' | 'general';
}

export interface MarchState {
  step: MarchStep;
  label: string;
  status: 'pending' | 'in_progress' | 'addressed' | 'critical';
}

export interface PatientState {
  patient_id: string;
  display_label: string;
  triage_category?: 'immediate' | 'delayed' | 'minimal';
  vitals: Vitals;
  symptoms: string[];
  known_injuries: string[];
  revealed_findings: string[];
  revealed_assessments: string[];
  interventions: string[];
  march: MarchState[];
  mental_status: string;
  bleeding_status: string;
  body_zones: BodyInjuryHighlight[];
}

export interface UserActionRecord {
  turn_id: number;
  raw_text: string;
  recognized_actions: RecognizedAction[];
  confidence: number;
  score_delta: number;
  scoring_traces: ScoringTrace[];
  timestamp: number;
}

export interface SimulationSession {
  id: string;
  scenario_id: string;
  role: UserRole;
  training_mode: TrainingMode;
  status: SessionStatus;
  score: number;
  start_time: number;
  elapsed_seconds: number;
  current_turn: number;
  phase_of_care: string;
  active_patient_id: string;
  feed: FeedEntry[];
  actions: UserActionRecord[];
  patients: PatientState[];
  completed_action_ids: string[];
  missed_critical_ids: string[];
  unsafe_action_ids: string[];
  scoring_traces: ScoringTrace[];
  supply_inventory: SupplyItem[];
  supply_status_note: string;
  outcome?: string;
  ended_by_wit?: boolean;
}

export interface AARReport {
  session_id: string;
  bluf: string;
  score: number;
  pass_threshold: number;
  passed: boolean;
  patient_outcome: string;
  score_breakdown: {
    category: string;
    points: number;
    max_points: number;
  }[];
  strengths: string[];
  improvements: string[];
  missed_critical: string[];
  unsafe_actions: string[];
  timeline: { time: string; event: string }[];
  teaching_points: string[];
  recommendations: string[];
}

export interface ScenarioSeed {
  id: string;
  title: string;
  section: MedicalSection;
  threat: string;
  difficulty: SkillLevel;
  patients: number;
  objectives: string[];
}
