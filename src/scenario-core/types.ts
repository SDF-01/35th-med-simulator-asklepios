import type { Scenario } from '../types';
import type {
  ScenarioEvidenceCitation,
  ScenarioEvidenceTopic,
} from '../scenario-generation/types';

export type ScenarioBuildMode = 'research_only' | 'template_locked';

export type ScenarioStageId =
  | 'source'
  | 'setting'
  | 'pressure'
  | 'route'
  | 'final';

export type ScenarioAtomKind =
  | 'source_template'
  | 'location'
  | 'weather'
  | 'visibility'
  | 'communications'
  | 'resources'
  | 'resource_event'
  | 'research_reference'
  | 'route_template';

export interface ScenarioBlueprint {
  blueprint_id: string;
  blueprint_version: string;
  mode: ScenarioBuildMode;
  source_scenario_id: string;
  allowed_topics: ScenarioEvidenceTopic[];
  mutable_paths: string[];
  location_options: string[];
  weather_options: string[];
  visibility_options: string[];
  communications_options: Array<'normal' | 'degraded' | 'intermittent' | 'unavailable'>;
  resource_options: Array<'normal' | 'constrained' | 'overwhelmed'>;
  resource_event_options: string[];
  route_template_id: string;
}

export interface ScenarioAtom {
  atom_id: string;
  atom_kind: ScenarioAtomKind;
  value: string;
  source_kind: 'repository_template' | 'research_metadata' | 'deterministic_selection';
  evidence_ids: string[];
  authority: 'template_inherited' | 'supporting_only' | 'nonclinical';
  atom_sha256: string;
}

export interface ScenarioRouteNode {
  node_id: string;
  node_kind: 'briefing' | 'movement' | 'observation' | 'pressure' | 'handoff' | 'complete';
  label: string;
  terminal: boolean;
  operational_semantic?:
    | 'orientation'
    | 'movement'
    | 'scene_observation'
    | 'operational_pressure'
    | 'communications_relay'
    | 'resource_coordination'
    | 'closed_loop_handoff'
    | 'completion';
}

export interface ScenarioRouteEdge {
  edge_id: string;
  from: string;
  to: string;
  trigger: 'start' | 'arrive' | 'facilitator_event' | 'handoff_ready' | 'close';
  priority: number;
}

export interface ScenarioRouteGraph {
  route_id: string;
  start_node_id: string;
  nodes: ScenarioRouteNode[];
  edges: ScenarioRouteEdge[];
}

export interface ScenarioBuildStage {
  stage_id: ScenarioStageId;
  formula_version: '1.0.0';
  input_sha256: string;
  payload_sha256: string;
  output_sha256: string;
  selected_atom_ids: string[];
  touched_paths: string[];
}

export interface ScenarioFieldOrigin {
  field_path: string;
  atom_ids: string[];
  evidence_ids: string[];
  origin_kind: 'source_template' | 'generated_context' | 'route_definition';
}

export interface ScenarioCertificateChecks {
  protected_fields_unchanged: boolean;
  route_has_reachable_terminal: boolean;
  route_has_no_dead_end: boolean;
  field_origins_complete: boolean;
  evidence_scope_preserved: boolean;
  stage_chain_contiguous: boolean;
  stage_payloads_verified: boolean;
}

export interface ScenarioCertificate {
  certificate_version: '1.1.0';
  checker_profile: 'scenario-contract-v1';
  base_scenario_sha256: string;
  base_protected_sha256: string;
  output_protected_sha256: string;
  source_bridge_sha256: string;
  source_prototype_sha256: string;
  source_prototype_record_sha256: string;
  blueprint_sha256: string;
  atom_root_sha256: string;
  stage_chain_sha256: string;
  route_sha256: string;
  field_origin_sha256: string;
  evidence_sha256: string;
  package_sha256: string;
  checks: ScenarioCertificateChecks;
}

export interface VerifiedScenarioPackage {
  schema_version: '2.1.0';
  build: {
    build_id: string;
    build_version: '2.1.0';
    mode: ScenarioBuildMode;
    seed: number;
    topic_id: ScenarioEvidenceTopic;
    retriever_track: string;
    blueprint_id: string;
    source_scenario_id: string;
    source_bridge_schema: string;
    source_database_sha256: string;
    source_bridge_sha256: string;
    source_prototype_id: string;
    source_prototype_sha256: string;
    source_prototype_record_sha256: string;
  };
  blueprint: ScenarioBlueprint;
  authority: {
    clinical_authority: 'NOT_GRANTED';
    deployment_scope: 'research_sandbox_only';
    source_template_status: 'repository_template_not_clinically_certified';
    clinical_rule_source: 'inherited_template';
    evidence_authority: 'supporting_only';
    evidence_effect_scope: 'citation_support_only';
    scoring_behavior: 'inherited_unchanged';
  };
  scenario: Scenario;
  route: ScenarioRouteGraph;
  evidence: ScenarioEvidenceCitation[];
  atoms: ScenarioAtom[];
  stages: ScenarioBuildStage[];
  field_origins: ScenarioFieldOrigin[];
  certificate: ScenarioCertificate;
}

export interface ScenarioPackageCheckIssue {
  code: string;
  path: string;
  message: string;
}

export interface ScenarioPackageCheckReport {
  status: 'PASS' | 'FAIL';
  issues: ScenarioPackageCheckIssue[];
  checks_run: number;
}
