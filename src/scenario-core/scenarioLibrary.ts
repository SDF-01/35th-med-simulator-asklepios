import type { ScenarioOperationalBehaviorProfileId } from './behaviorProfiles';

export interface OperationalScenarioCatalogEntry {
  catalog_entry_id: string;
  schema_version: '1.0.0';
  candidate_id: string;
  source_scenario_id: string;
  topic_id: string;
  seed: number;
  operational_behavior_profile_id: ScenarioOperationalBehaviorProfileId;
  profile_label: string;
  title: string;
  plain_language_summary: string;
  context: {
    location: string;
    weather: string;
    visibility: string;
    communications: string;
    resources: string;
    resource_event: string;
  };
  learning_focus: string[];
  reproducibility: {
    package_sha256: string;
    context_signature_sha256: string;
    policy_signature_sha256: string;
    equivalence_class_id: string;
  };
  authority: {
    healthcare_simulation: 'PERMITTED_WITHIN_VALIDATED_SCOPE';
    direct_patient_care: 'PROHIBITED';
    clinical_decision_support: 'PROHIBITED';
    operational_timing: 'NOT_CALIBRATED';
    scoring_state: 'SOURCE_CONFORMANCE_ONLY';
    treatment_state: 'NO_SIMULATION_ADMITTED_CONCRETE_TREATMENT';
  };
  profile_sequence: number;
}

export interface OperationalScenarioCatalog {
  schema_version: '1.0.0';
  classification: 'PASS';
  status: 'PASS';
  catalog_id: string;
  catalog_profile: string;
  selection_profile: string;
  policy_id: string;
  policy_epoch: number;
  policy_sha256: string;
  source_archive_path: string;
  source_archive_root_sha256: string;
  entry_count: number;
  profile_counts: Record<ScenarioOperationalBehaviorProfileId, number>;
  entries: OperationalScenarioCatalogEntry[];
  stakeholder_surfaces: string[];
  truth_boundaries: Record<string, string>;
  catalog_root_sha256: string;
}

const PROFILES: readonly ScenarioOperationalBehaviorProfileId[] = [
  'DIRECT_HANDOFF_BASELINE',
  'COMMUNICATION_RELAY_REQUIRED',
  'RESOURCE_COORDINATION_REQUIRED',
  'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
];

export function validateOperationalScenarioCatalog(value: unknown): asserts value is OperationalScenarioCatalog {
  if (!value || typeof value !== 'object') throw new Error('Scenario catalog is not an object.');
  const catalog = value as Partial<OperationalScenarioCatalog>;
  if (catalog.schema_version !== '1.0.0' || catalog.classification !== 'PASS' || catalog.status !== 'PASS') {
    throw new Error('Scenario catalog status is invalid.');
  }
  if (!Array.isArray(catalog.entries) || catalog.entries.length !== catalog.entry_count || catalog.entry_count !== 12) {
    throw new Error('Scenario catalog must contain the reviewed 12-scenario pack.');
  }
  const ids = new Set<string>();
  const candidates = new Set<string>();
  for (const entry of catalog.entries) {
    if (!entry.catalog_entry_id || ids.has(entry.catalog_entry_id)) throw new Error('Scenario catalog entry ID is missing or duplicated.');
    if (!entry.candidate_id || candidates.has(entry.candidate_id)) throw new Error('Scenario catalog candidate is missing or duplicated.');
    ids.add(entry.catalog_entry_id);
    candidates.add(entry.candidate_id);
    if (!PROFILES.includes(entry.operational_behavior_profile_id)) throw new Error(`Unknown operational behavior profile: ${entry.operational_behavior_profile_id}.`);
    if (!Number.isSafeInteger(entry.seed) || entry.seed < 0) throw new Error(`Scenario seed is invalid: ${entry.catalog_entry_id}.`);
    if (entry.authority.direct_patient_care !== 'PROHIBITED'
      || entry.authority.clinical_decision_support !== 'PROHIBITED'
      || entry.authority.operational_timing !== 'NOT_CALIBRATED'
      || entry.authority.scoring_state !== 'SOURCE_CONFORMANCE_ONLY') {
      throw new Error(`Scenario authority boundary was promoted: ${entry.catalog_entry_id}.`);
    }
  }
  for (const profile of PROFILES) {
    if (catalog.profile_counts?.[profile] !== 3) throw new Error(`Scenario profile must contain exactly three entries: ${profile}.`);
  }
}

export async function loadOperationalScenarioCatalog(): Promise<OperationalScenarioCatalog> {
  // Default cache mode so the service worker can serve this offline after first visit.
  const response = await fetch('/data/scenario_library/operational-pack.json');
  if (!response.ok) throw new Error(`Scenario catalog request failed with status ${response.status}.`);
  const value: unknown = await response.json();
  validateOperationalScenarioCatalog(value);
  return value;
}
