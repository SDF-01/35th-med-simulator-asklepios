import type { MedicalSection, Scenario, SkillLevel, UserRole } from '../types';

export type ScenarioEvidenceTopic =
  | 'massive_hemorrhage'
  | 'airway'
  | 'respiration_chest'
  | 'shock_resuscitation'
  | 'tbi_neurologic'
  | 'burns_hypothermia'
  | 'analgesia_sedation'
  | 'toxicology'
  | 'evacuation_transport'
  | 'mass_casualty_systems'
  | 'documentation_aar';

export interface ScenarioGenerationRequest {
  topic_id: ScenarioEvidenceTopic;
  seed: number;
  retriever_track?: string;
  target_section?: MedicalSection;
  target_role?: UserRole;
  difficulty?: SkillLevel;
}

export interface ScenarioEvidenceCitation {
  evidence_id: string;
  source_id: string;
  title: string;
  journal: string;
  doi: string;
  publication_date: string;
  locator: string;
  chunk_sha256: string;
  source_file_sha256: string;
}

export interface GeneratedFieldTrace {
  field_path: string;
  derivation: 'procedural_constraint' | 'retrieved_research_support' | 'validated_narrative_draft';
  evidence_ids: string[];
  note: string;
}

export interface ScenarioNarrativeDraft {
  title?: string;
  operational_narrative?: string;
  initial_presentation?: string;
  cue_labels?: string[];
  complication_labels?: string[];
}

export interface ScenarioNarrativeRequest {
  topic_id: ScenarioEvidenceTopic;
  seed: number;
  constraints: {
    clinical_authority: 'NOT_GRANTED';
    scoring_enabled: false;
    maximum_citations: number;
    expected_actions_must_remain_empty: true;
  };
  citations: ScenarioEvidenceCitation[];
}

export interface ScenarioNarrativeProvider {
  provider_id: string;
  draft(request: ScenarioNarrativeRequest): Promise<ScenarioNarrativeDraft>;
}

export interface GeneratedResearchScenario {
  schema_version: '1.0.0';
  generator: {
    generator_id: 'asklepios-hybrid-scenario-engine';
    generator_version: '1.0.0';
    seed: number;
    topic_id: ScenarioEvidenceTopic;
    retriever_track: string;
    source_bridge_schema: string;
  };
  authority: {
    source_tier: 3;
    clinical_authority: 'NOT_GRANTED';
    scoring_enabled: false;
    deployment_mode: 'research_sandbox_only';
  };
  scenario: Scenario;
  evidence: ScenarioEvidenceCitation[];
  field_provenance: GeneratedFieldTrace[];
  cue_categories: string[];
  complication_categories: string[];
  resource_events: string[];
  content_fingerprint: string;
}

export interface ScenarioValidationIssue {
  code: string;
  path: string;
  message: string;
}

export interface ScenarioValidationReport {
  status: 'PASS' | 'FAIL';
  issues: ScenarioValidationIssue[];
  checked_invariants: number;
}
