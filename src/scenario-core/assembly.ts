import { scenariosById } from '../content/scenarios';
import type { Scenario } from '../types';
import type {
  ResearchEvidenceRefRecord,
  ResearchPrototypeRecord,
  ResearchRuntimeBridge,
  ResearchSourceRecord,
} from '../research/types';
import { validatePublicResearchBridge } from '../research/validation';
import type {
  ScenarioEvidenceCitation,
  ScenarioEvidenceTopic,
} from '../scenario-generation/types';
import {
  FIELD_VARIANT_BLUEPRINT,
  FIELD_VARIANT_OPERATIONAL_CONSTRAINTS,
  FIELD_VARIANT_OPERATIONAL_FACTORS,
} from './blueprints';
import { selectDeterministicFeasibleAssignment } from './coverage';
import { buildCertificate, createScenarioAtom } from './certificate';
import { canonicalJson, sha256Canonical } from './hash';
import { protectedScenarioProjection } from './projection';
import { resolveScenarioOperationalBehaviorProfile } from './behaviorProfiles';
import { buildFieldRoute, validateRouteGraph } from './route';
import { makeStage, stagePayload, type PackageWithoutCertificate } from './stages';
import type {
  ScenarioFieldOrigin,
  VerifiedScenarioPackage,
} from './types';

export interface TemplateLockedScenarioRequest {
  topic_id: ScenarioEvidenceTopic;
  seed: number;
  retriever_track?: string;
}

function cloneScenario(value: Scenario): Scenario {
  return JSON.parse(JSON.stringify(value)) as Scenario;
}

function splitPipe(value: string): string[] {
  return value.split('|').map((item) => item.trim()).filter(Boolean);
}

function choosePrototype(
  bridge: ResearchRuntimeBridge,
  request: TemplateLockedScenarioRequest,
): ResearchPrototypeRecord {
  const track = request.retriever_track
    ?? bridge.retrieval_release.default_research_sandbox_retriever
    ?? bridge.retrieval_release.candidate_retriever;
  const candidates = bridge.prototypes
    .filter((item) => item.topic_id === request.topic_id)
    .sort((left, right) => left.prototype_id.localeCompare(right.prototype_id));
  const prototype = candidates.find((item) => item.retriever_track === track);
  if (!prototype) {
    throw new Error(`No citation prototype exists for ${request.topic_id} on retriever track ${track}.`);
  }
  return prototype;
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
  const evidenceById = new Map(
    bridge.evidence_refs.map((record) => [record.evidence_id, record] as const),
  );
  const sourceByIndex = new Map(
    bridge.sources.map((record) => [record.source_index, record] as const),
  );
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
  if (citations.length === 0) throw new Error('At least one evidence reference is required.');
  return citations;
}


function normalizedBridgeView(bridge: ResearchRuntimeBridge): ResearchRuntimeBridge {
  return {
    ...bridge,
    sources: [...bridge.sources].sort((left, right) => left.source_index - right.source_index),
    evidence_refs: [...bridge.evidence_refs].sort((left, right) => left.evidence_id.localeCompare(right.evidence_id)),
    prototypes: [...bridge.prototypes].sort((left, right) => left.prototype_id.localeCompare(right.prototype_id)),
  };
}

export function buildTemplateLockedScenario(
  rawBridge: ResearchRuntimeBridge,
  request: TemplateLockedScenarioRequest,
): VerifiedScenarioPackage {
  const bridge = validatePublicResearchBridge(rawBridge);
  const blueprint = FIELD_VARIANT_BLUEPRINT;
  if (!blueprint.allowed_topics.includes(request.topic_id)) {
    throw new Error(`Blueprint ${blueprint.blueprint_id} does not admit topic ${request.topic_id}.`);
  }
  const sourceScenario = scenariosById[blueprint.source_scenario_id];
  if (!sourceScenario) throw new Error(`Source scenario ${blueprint.source_scenario_id} is missing.`);

  if (!Number.isSafeInteger(request.seed) || request.seed < 0) {
    throw new Error('Scenario seed must be a nonnegative safe integer.');
  }
  const prototype = choosePrototype(bridge, request);
  const citations = collectCitations(bridge, prototype);

  // Every seed is mapped through a deterministic permutation of the complete
  // reviewed and feasible operational space. The first cycle therefore has no
  // duplicate contexts and covers every admitted t-way interaction by design.
  const selected = selectDeterministicFeasibleAssignment(
    FIELD_VARIANT_OPERATIONAL_FACTORS,
    request.seed,
    `${blueprint.blueprint_id}:${blueprint.blueprint_version}:${request.topic_id}`,
    { constraints: FIELD_VARIANT_OPERATIONAL_CONSTRAINTS },
  );
  const selectedLocation = selected.assignment.location!;
  const selectedWeather = selected.assignment.weather!;
  const selectedVisibility = selected.assignment.visibility!;
  const selectedComms = selected.assignment.communications as (typeof blueprint.communications_options)[number];
  const selectedResources = selected.assignment.resources as (typeof blueprint.resource_options)[number];
  const selectedResourceEvent = selected.assignment.resource_event!;

  const sourceAtom = createScenarioAtom({
    atom_id: 'atom-source-template',
    atom_kind: 'source_template',
    value: blueprint.source_scenario_id,
    source_kind: 'repository_template',
    evidence_ids: [],
    authority: 'template_inherited',
  });
  const contextAtoms = [
    createScenarioAtom({ atom_id: 'atom-location', atom_kind: 'location', value: selectedLocation, source_kind: 'deterministic_selection', evidence_ids: [], authority: 'nonclinical' }),
    createScenarioAtom({ atom_id: 'atom-weather', atom_kind: 'weather', value: selectedWeather, source_kind: 'deterministic_selection', evidence_ids: [], authority: 'nonclinical' }),
    createScenarioAtom({ atom_id: 'atom-visibility', atom_kind: 'visibility', value: selectedVisibility, source_kind: 'deterministic_selection', evidence_ids: [], authority: 'nonclinical' }),
    createScenarioAtom({ atom_id: 'atom-communications', atom_kind: 'communications', value: selectedComms, source_kind: 'deterministic_selection', evidence_ids: [], authority: 'nonclinical' }),
    createScenarioAtom({ atom_id: 'atom-resources', atom_kind: 'resources', value: selectedResources, source_kind: 'deterministic_selection', evidence_ids: [], authority: 'nonclinical' }),
    createScenarioAtom({ atom_id: 'atom-resource-event', atom_kind: 'resource_event', value: selectedResourceEvent, source_kind: 'deterministic_selection', evidence_ids: [], authority: 'nonclinical' }),
  ];
  const evidenceAtoms = citations.map((citation, index) => createScenarioAtom({
    atom_id: `atom-reference-${String(index + 1).padStart(2, '0')}`,
    atom_kind: 'research_reference',
    value: citation.evidence_id,
    source_kind: 'research_metadata',
    evidence_ids: [citation.evidence_id],
    authority: 'supporting_only',
  }));
  const behaviorProfile = resolveScenarioOperationalBehaviorProfile(selectedComms, selectedResources);
  const routeAtom = createScenarioAtom({
    atom_id: 'atom-route-template',
    atom_kind: 'route_template',
    value: `${blueprint.route_template_id}:${behaviorProfile.profile_id}`,
    source_kind: 'repository_template',
    evidence_ids: [],
    authority: 'nonclinical',
  });
  const atoms = [sourceAtom, ...contextAtoms, ...evidenceAtoms, routeAtom];

  const sourceBridgeHash = sha256Canonical(normalizedBridgeView(bridge));
  const sourcePrototypeHash = prototype.prototype_sha256;
  const sourcePrototypeRecordHash = sha256Canonical(prototype);

  const scenario = cloneScenario(sourceScenario);
  const shortHash = sha256Canonical({
    blueprint: blueprint.blueprint_id,
    seed: request.seed,
    topic: request.topic_id,
    context: contextAtoms.map((atom) => atom.atom_sha256),
  }).slice(0, 10);
  const buildHash = sha256Canonical({
    scenario_id: `ASK-V-${shortHash.toUpperCase()}`,
    retriever_track: prototype.retriever_track,
    prototype_record_sha256: sourcePrototypeRecordHash,
  }).slice(0, 10);
  scenario.scenario_id = `ASK-V-${shortHash.toUpperCase()}`;
  scenario.title = `${sourceScenario.title} — Operational Variant`;
  scenario.version = `${sourceScenario.version}+variant.2.2`;
  scenario.fictionalization_notice = [
    sourceScenario.fictionalization_notice,
    'Operational details were varied for training; the inherited clinical scaffold was not changed.',
  ].join(' ');
  scenario.operational_context = {
    ...sourceScenario.operational_context,
    location_type: selectedLocation,
    weather: selectedWeather,
    visibility: selectedVisibility,
    comms_status: selectedComms,
    resource_status: selectedResources,
    narrative: [
      `Fictional operational variant at ${selectedLocation}.`,
      `Weather: ${selectedWeather}. Visibility: ${selectedVisibility}.`,
      `Communications: ${selectedComms}. Resources: ${selectedResources}.`,
      `Facilitator event: ${selectedResourceEvent}.`,
      `The clinical scaffold, action catalog, scoring, and end conditions are inherited unchanged from ${sourceScenario.scenario_id}.`,
    ].join(' '),
  };

  const route = buildFieldRoute(`${blueprint.route_template_id}-${shortHash}`, behaviorProfile.profile_id);
  const routeValidation = validateRouteGraph(route);
  if (!routeValidation.valid) throw new Error(routeValidation.issues.join('\n'));

  const packageWithoutStages: Omit<PackageWithoutCertificate, 'stages' | 'field_origins'> = {
    schema_version: '2.1.0',
    build: {
      build_id: `ASK-B-${buildHash.toUpperCase()}`,
      build_version: '2.1.0',
      mode: 'template_locked',
      seed: request.seed,
      topic_id: request.topic_id,
      retriever_track: prototype.retriever_track,
      blueprint_id: blueprint.blueprint_id,
      source_scenario_id: sourceScenario.scenario_id,
      source_bridge_schema: bridge.schema_version,
      source_database_sha256: bridge.retrieval_release.database_sha256,
      source_bridge_sha256: sourceBridgeHash,
      source_prototype_id: prototype.prototype_id,
      source_prototype_sha256: sourcePrototypeHash,
      source_prototype_record_sha256: sourcePrototypeRecordHash,
    },
    blueprint,
    authority: {
      clinical_authority: 'NOT_GRANTED',
      deployment_scope: 'research_sandbox_only',
      source_template_status: 'repository_template_not_clinically_certified',
      clinical_rule_source: 'inherited_template',
      evidence_authority: 'supporting_only',
      evidence_effect_scope: 'citation_support_only',
      scoring_behavior: 'inherited_unchanged',
    },
    scenario,
    route,
    evidence: citations,
    atoms,
  };

  const settingOriginMap: Record<string, string[]> = {
    'scenario.scenario_id': contextAtoms.map((atom) => atom.atom_id),
    'scenario.title': [sourceAtom.atom_id],
    'scenario.version': [sourceAtom.atom_id],
    'scenario.fictionalization_notice': [sourceAtom.atom_id],
    'scenario.operational_context.location_type': ['atom-location'],
    'scenario.operational_context.weather': ['atom-weather'],
    'scenario.operational_context.visibility': ['atom-visibility'],
    'scenario.operational_context.comms_status': ['atom-communications'],
    'scenario.operational_context.resource_status': ['atom-resources'],
    'scenario.operational_context.narrative': [
      'atom-location',
      'atom-weather',
      'atom-visibility',
      'atom-communications',
      'atom-resources',
      'atom-resource-event',
    ],
  };
  const atomsById = new Map(atoms.map((atom) => [atom.atom_id, atom] as const));
  const fieldOrigins: ScenarioFieldOrigin[] = [
    {
      field_path: 'scenario.protected_projection',
      atom_ids: [sourceAtom.atom_id],
      evidence_ids: [],
      origin_kind: 'source_template',
    },
    ...Object.entries(settingOriginMap).map(([fieldPath, atomIds]) => ({
      field_path: fieldPath,
      atom_ids: atomIds,
      evidence_ids: [...new Set(atomIds.flatMap((id) => atomsById.get(id)?.evidence_ids ?? []))],
      origin_kind: 'generated_context' as const,
    })),
    {
      field_path: 'route',
      atom_ids: [routeAtom.atom_id],
      evidence_ids: [],
      origin_kind: 'route_definition',
    },
  ];

  const temporary: PackageWithoutCertificate = {
    ...packageWithoutStages,
    stages: [],
    field_origins: fieldOrigins,
  };
  const stageInputs = [
    { id: 'source' as const, atomIds: [sourceAtom.atom_id, ...evidenceAtoms.map((atom) => atom.atom_id)], paths: ['scenario.protected_projection'] },
    { id: 'setting' as const, atomIds: contextAtoms.slice(0, 5).map((atom) => atom.atom_id), paths: [
      'scenario.scenario_id', 'scenario.title', 'scenario.version', 'scenario.fictionalization_notice',
      'scenario.operational_context.location_type', 'scenario.operational_context.weather',
      'scenario.operational_context.visibility', 'scenario.operational_context.comms_status',
      'scenario.operational_context.resource_status',
    ] },
    { id: 'pressure' as const, atomIds: ['atom-resource-event'], paths: ['scenario.operational_context.narrative'] },
    { id: 'route' as const, atomIds: [routeAtom.atom_id], paths: ['route'] },
    { id: 'final' as const, atomIds: atoms.map((atom) => atom.atom_id), paths: [] },
  ];
  const stages = [] as PackageWithoutCertificate['stages'];
  let previous = sha256Canonical({
    build: temporary.build,
    source_database_sha256: bridge.retrieval_release.database_sha256,
  });
  for (const entry of stageInputs) {
    const partial = { ...temporary, stages };
    const stage = makeStage({
      stage_id: entry.id,
      input_sha256: previous,
      payload: stagePayload(entry.id, partial, sourceScenario),
      selected_atom_ids: entry.atomIds,
      touched_paths: entry.paths,
    });
    stages.push(stage);
    previous = stage.output_sha256;
  }

  const packageWithoutCertificate: PackageWithoutCertificate = {
    ...packageWithoutStages,
    stages,
    field_origins: fieldOrigins,
  };
  const certificate = buildCertificate(sourceScenario, packageWithoutCertificate);
  if (canonicalJson(protectedScenarioProjection(sourceScenario)) !== canonicalJson(protectedScenarioProjection(scenario))) {
    throw new Error('Protected scenario fields changed during assembly.');
  }
  return { ...packageWithoutCertificate, certificate };
}
