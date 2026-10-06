import type { Scenario, ScenarioPatient, Vitals } from '../types';
import type {
  ResearchEvidenceRefRecord,
  ResearchPrototypeRecord,
  ResearchRuntimeBridge,
  ResearchSourceRecord,
} from '../research/types';
import { validatePublicResearchBridge } from '../research/validation';
import { contentFingerprint } from './canonical';
import { createSeededRandom } from './prng';
import { TOPIC_PROFILES } from './topicProfiles';
import type {
  GeneratedResearchScenario,
  ScenarioEvidenceCitation,
  ScenarioGenerationRequest,
  ScenarioNarrativeDraft,
} from './types';

function splitPipe(value: string): string[] {
  return value.split('|').map((item) => item.trim()).filter(Boolean);
}

function range(random: ReturnType<typeof createSeededRandom>, bounds: readonly [number, number]): number {
  return random.integer(bounds[0], bounds[1]);
}

function choosePrototype(
  bridge: ResearchRuntimeBridge,
  request: ScenarioGenerationRequest,
): ResearchPrototypeRecord {
  const preferredTrack = request.retriever_track
    ?? bridge.retrieval_release.default_research_sandbox_retriever
    ?? bridge.retrieval_release.candidate_retriever;
  const candidates = bridge.prototypes
    .filter((item) => item.topic_id === request.topic_id)
    .sort((left, right) => left.prototype_id.localeCompare(right.prototype_id));
  const selected = candidates.find((item) => item.retriever_track === preferredTrack)
    ?? candidates[0];
  if (!selected) throw new Error(`No research prototype exists for ${request.topic_id}.`);
  return selected;
}

function buildCitation(
  evidence: ResearchEvidenceRefRecord,
  source: ResearchSourceRecord,
): ScenarioEvidenceCitation {
  return {
    evidence_id: evidence.evidence_id,
    source_id: source.source_id,
    title: source.title,
    journal: source.journal,
    doi: source.doi,
    publication_date: source.publication_date,
    locator: evidence.locator,
    chunk_sha256: evidence.chunk_sha256,
    source_file_sha256: source.source_file_sha256,
  };
}

function collectCitations(
  bridge: ResearchRuntimeBridge,
  prototype: ResearchPrototypeRecord,
): ScenarioEvidenceCitation[] {
  const evidenceById = new Map(bridge.evidence_refs.map((record) => [record.evidence_id, record] as const));
  const sourceByIndex = new Map(bridge.sources.map((record) => [record.source_index, record] as const));
  const unique = new Set<string>();
  const citations: ScenarioEvidenceCitation[] = [];
  for (const evidenceId of splitPipe(prototype.evidence_ids)) {
    if (unique.has(evidenceId)) continue;
    unique.add(evidenceId);
    const evidence = evidenceById.get(evidenceId);
    if (!evidence) throw new Error(`Prototype references missing evidence ${evidenceId}.`);
    const source = sourceByIndex.get(evidence.source_index);
    if (!source) throw new Error(`Evidence ${evidenceId} references missing source ${evidence.source_index}.`);
    citations.push(buildCitation(evidence, source));
    if (citations.length >= 6) break;
  }
  if (citations.length === 0) throw new Error('Scenario generation requires at least one citation.');
  return citations;
}

function buildVitals(
  random: ReturnType<typeof createSeededRandom>,
  ranges: (typeof TOPIC_PROFILES)[keyof typeof TOPIC_PROFILES]['vital_ranges'],
): Vitals {
  return {
    hr: range(random, ranges.hr),
    bp_systolic: range(random, ranges.bp_systolic),
    bp_diastolic: range(random, ranges.bp_diastolic),
    rr: range(random, ranges.rr),
    spo2: range(random, ranges.spo2),
    temp_c: range(random, ranges.temp_c_tenths) / 10,
    gcs: range(random, ranges.gcs),
  };
}

function useDraftText(candidate: string | undefined, fallback: string): string {
  return candidate?.trim() ? candidate.trim() : fallback;
}

/** Backwards-compatible research-only generator. New runtime packages use scenario-core/assembly. */
export function generateResearchScenario(
  rawBridge: ResearchRuntimeBridge,
  request: ScenarioGenerationRequest,
  draft: ScenarioNarrativeDraft = {},
): GeneratedResearchScenario {
  const bridge = validatePublicResearchBridge(rawBridge);
  const profile = TOPIC_PROFILES[request.topic_id];
  if (!profile) throw new Error(`Unsupported scenario topic ${request.topic_id}.`);
  const random = createSeededRandom(request.seed);
  const prototype = choosePrototype(bridge, request);
  const citations = collectCitations(bridge, prototype);
  const evidenceIds = citations.map((item) => item.evidence_id);

  const location = prototype.location || random.pick(profile.locations);
  const weather = prototype.weather || random.pick(['clear', 'rain', 'cold wind', 'low visibility']);
  const communications = prototype.communications || random.pick(profile.comms);
  const resourceEvents = splitPipe(prototype.resource_events).length > 0
    ? splitPipe(prototype.resource_events)
    : [random.pick(profile.resource_events)];
  const cues = draft.cue_labels?.length
    ? [...new Set(draft.cue_labels)]
    : (splitPipe(prototype.cue_categories).length > 0 ? splitPipe(prototype.cue_categories) : [...profile.cues]);
  const complications = draft.complication_labels?.length
    ? [...new Set(draft.complication_labels)]
    : (splitPipe(prototype.complication_categories).length > 0
      ? splitPipe(prototype.complication_categories)
      : [...profile.complications]);

  const patient: ScenarioPatient = {
    patient_id: 'P1',
    age_band: random.pick(profile.age_bands),
    sex: random.pick(profile.sex_values),
    role_context: random.pick(profile.role_contexts),
    mechanism_of_injury: random.pick(profile.mechanisms),
    initial_presentation: useDraftText(draft.initial_presentation, random.pick(profile.presentations)),
    injury_profile_refs: [...profile.injury_profile_refs],
    initial_vitals: buildVitals(random, profile.vital_ranges),
    hidden_findings: [...profile.hidden_findings],
    deterioration_timeline: [...profile.deterioration],
    visible_body_zones: profile.visible_body_zones.map((item) => ({ ...item })),
  };

  const targetSection = request.target_section ?? profile.target_section;
  const targetRole = request.target_role ?? profile.target_role;
  const difficulty = request.difficulty ?? profile.difficulty;
  const baseNarrative = [
    `Fictional training evolution at ${location}.`,
    `Weather: ${weather}. Communications: ${communications}.`,
    `Research-supported cue categories: ${cues.join(', ')}.`,
    `Resource event: ${resourceEvents[0]}.`,
    'The facilitator controls progression. No automated clinical score or treatment rule is active.',
  ].join(' ');

  const scenarioBase: Omit<Scenario, 'scenario_id'> = {
    title: useDraftText(draft.title, profile.title_stem),
    version: 'research-1.0.0',
    fictionalization_notice:
      'Fictional, unscored research scenario. It does not establish medical advice, provider scope, treatment rules, or clinical scoring.',
    operational_context: {
      location_type: location,
      threat_type: profile.threat_type,
      weather,
      visibility: weather.includes('low') ? 'Reduced' : 'Variable',
      comms_status: (['normal', 'degraded', 'intermittent', 'unavailable'] as const).includes(
        communications as Scenario['operational_context']['comms_status'],
      )
        ? (communications as Scenario['operational_context']['comms_status'])
        : random.pick(profile.comms),
      resource_status: random.pick(profile.resources),
      narrative: useDraftText(draft.operational_narrative, baseNarrative),
    },
    training_objectives: [...profile.objectives],
    target_section: targetSection,
    target_role: targetRole,
    skill_level: difficulty,
    difficulty,
    threat_type: profile.threat_type,
    casualty_count: 1,
    patients: [patient],
    expected_actions: { critical: [], important: [], optional: [], unsafe: [] },
    end_conditions: {
      success: ['Facilitator confirms that all selected cues and resource events were explored.'],
      failure: ['No automated clinical failure state is assigned in research-sandbox mode.'],
      timeout_minutes: 20,
    },
    aar_teaching_points: [
      'Compare observations with the cited research record and its stated limitations.',
      'Preserve uncertainty when the evidence does not establish a clinical rule.',
      'Any scored action or state-transition rule requires a separate approved authority layer.',
    ],
  };

  const identityMaterial = {
    seed: request.seed,
    topic_id: request.topic_id,
    retriever_track: prototype.retriever_track,
    scenario: scenarioBase,
    evidence_ids: evidenceIds,
    cues,
    complications,
    resource_events: resourceEvents,
  };
  const fingerprint = contentFingerprint(identityMaterial);
  const scenario: Scenario = {
    scenario_id: `ASK-RS-${request.topic_id.toUpperCase().replaceAll('_', '-')}-${fingerprint.slice(0, 8)}`,
    ...scenarioBase,
  };

  const resultWithoutFingerprint = {
    schema_version: '1.0.0' as const,
    generator: {
      generator_id: 'asklepios-hybrid-scenario-engine' as const,
      generator_version: '1.0.0' as const,
      seed: request.seed,
      topic_id: request.topic_id,
      retriever_track: prototype.retriever_track,
      source_bridge_schema: bridge.schema_version,
    },
    authority: {
      source_tier: 3 as const,
      clinical_authority: 'NOT_GRANTED' as const,
      scoring_enabled: false as const,
      deployment_mode: 'research_sandbox_only' as const,
    },
    scenario,
    evidence: citations,
    field_provenance: [
      {
        field_path: 'scenario.operational_context',
        derivation: 'procedural_constraint' as const,
        evidence_ids: evidenceIds,
        note: 'Context is fictionalized from a deterministic profile and citation-only prototype metadata.',
      },
      {
        field_path: 'scenario.patients[0].initial_presentation',
        derivation: draft.initial_presentation ? 'validated_narrative_draft' as const : 'procedural_constraint' as const,
        evidence_ids: evidenceIds,
        note: 'Presentation remains observational and cannot create a treatment rule.',
      },
      {
        field_path: 'cue_categories',
        derivation: 'retrieved_research_support' as const,
        evidence_ids: evidenceIds,
        note: 'Cue categories are scenario prompts, not authoritative physiology.',
      },
      {
        field_path: 'complication_categories',
        derivation: 'retrieved_research_support' as const,
        evidence_ids: evidenceIds,
        note: 'Complications are facilitator candidates and remain unscored.',
      },
    ],
    cue_categories: cues,
    complication_categories: complications,
    resource_events: resourceEvents,
  };

  return {
    ...resultWithoutFingerprint,
    content_fingerprint: contentFingerprint(resultWithoutFingerprint),
  };
}
