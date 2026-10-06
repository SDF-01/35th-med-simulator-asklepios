export interface ResearchSourceRecord {
  source_index: number;
  source_id: string;
  title: string;
  journal: string;
  doi: string;
  publication_date: string;
  source_file_sha256: string;
}

export interface ResearchEvidenceRefRecord {
  evidence_id: string;
  source_index: number;
  record_type: 'chunk' | 'snippet' | string;
  locator: string;
  topic_ids: string;
  word_count: number;
  chunk_sha256: string;
}

export interface ResearchPrototypeRecord {
  prototype_id: string;
  pair_id: string;
  retriever_track: string;
  topic_id: string;
  title: string;
  seed: number;
  location: string;
  weather: string;
  communications: string;
  resource_events: string;
  cue_categories: string;
  complication_categories: string;
  evidence_ids: string;
  prototype_sha256: string;
}

export interface ResearchRuntimeBridge {
  schema_version: string;
  generated_at_utc: string;
  scope: string;
  contains_licensed_source_text: false;
  authority: {
    tier: 3;
    clinical_authority: 'NOT_GRANTED';
    scoring_enabled: false;
    unscored_research_sandbox_only: true;
  };
  retrieval_release: {
    status: string;
    database_sha256: string;
    production_active_retriever: string;
    baseline_retriever: string;
    candidate_retriever: string;
    default_research_sandbox_retriever: string;
    feature_flag: string;
  };
  sources: ResearchSourceRecord[];
  evidence_refs: ResearchEvidenceRefRecord[];
  prototypes: ResearchPrototypeRecord[];
}

export type ResearchSandboxEventType =
  | 'sandbox_started'
  | 'time_advanced'
  | 'cue_revealed'
  | 'resource_event_triggered'
  | 'learner_note_recorded'
  | 'sandbox_reset';

export interface ResearchSandboxEvent {
  event_id: string;
  event_type: ResearchSandboxEventType;
  sequence: number;
  elapsed_seconds: number;
  payload: Record<string, string | number | boolean>;
}

export interface ResearchSandboxState {
  prototype_id: string;
  deterministic_seed: number;
  retriever_track: string;
  elapsed_seconds: number;
  revealed_cues: string[];
  triggered_resource_events: string[];
  learner_notes: string[];
  events: ResearchSandboxEvent[];
  mode: 'research_sandbox';
  scoring_enabled: false;
  clinical_authority: 'NOT_GRANTED';
}
