import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { scenariosById } from '../src/content/scenarios';
import type { ResearchRuntimeBridge } from '../src/research/types';
import { verifyScenarioPackage } from '../src/scenario-checker/verify';
import {
  FIELD_VARIANT_BLUEPRINT,
  FIELD_VARIANT_OPERATIONAL_CONSTRAINTS,
  FIELD_VARIANT_OPERATIONAL_COVERAGE_STRENGTH,
  FIELD_VARIANT_OPERATIONAL_FACTORS,
  buildConstraintAwareCoveringArray,
  buildDeterministicAssignmentCycle,
  buildTemplateLockedScenario,
  buildFieldRoute,
  buildScenarioBehaviorArchive,
  buildScenarioBehaviorDescriptor,
  canonicalJson,
  enumerateSuccessfulRouteWitnesses,
  protectedScenarioProjection,
  replayRouteWitness,
  SCENARIO_OPERATIONAL_BEHAVIOR_PROFILES,
  scenarioBehaviorSignature,
  validateRouteGraph,
  validateScenarioExperience,
} from '../src/scenario-core/index';
import type {
  FactorAssignment,
  FactorValues,
  ScenarioBehaviorCandidateInput,
  ScenarioRouteGraph,
  ScenarioRouteWitness,
  VerifiedScenarioPackage,
} from '../src/scenario-core/index';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const bridge = JSON.parse(
  await readFile(resolve(root, 'public/data/research_sandbox/runtime_bridge.json'), 'utf8'),
) as ResearchRuntimeBridge;
const sourceScenario = scenariosById[FIELD_VARIANT_BLUEPRINT.source_scenario_id];
if (!sourceScenario) throw new Error(`Missing reviewed source scenario ${FIELD_VARIANT_BLUEPRINT.source_scenario_id}.`);

function require(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

async function atomicWriteJson(path: string, value: unknown): Promise<void> {
  const temporary = `${path}.tmp-${process.pid}`;
  await mkdir(dirname(path), { recursive: true });
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  await rename(temporary, path);
}

function contextRow(topic: string, generated: VerifiedScenarioPackage): FactorAssignment {
  const event = generated.atoms.find((atom) => atom.atom_kind === 'resource_event')?.value ?? '';
  return {
    topic,
    location: generated.scenario.operational_context.location_type,
    weather: generated.scenario.operational_context.weather,
    visibility: generated.scenario.operational_context.visibility,
    communications: generated.scenario.operational_context.comms_status,
    resources: generated.scenario.operational_context.resource_status,
    resource_event: event,
  };
}

function operationalRow(row: FactorAssignment): FactorAssignment {
  return Object.fromEntries(Object.entries(row).filter(([name]) => name !== 'topic'));
}

interface ProfileRouteWitnessAudit {
  pass: boolean;
  detail: string;
  witnesses: ScenarioRouteWitness[];
  pressure_witness: ScenarioRouteWitness | null;
  direct_witness: ScenarioRouteWitness | null;
  required_teamwork_node_ids: string[];
}

function auditProfileRouteWitnesses(route: ScenarioRouteGraph): ProfileRouteWitnessAudit {
  const validation = validateRouteGraph(route);
  const witnesses = enumerateSuccessfulRouteWitnesses(route);
  const reversedEdgeRoute = { ...route, edges: [...route.edges].reverse() };
  const reorderedWitnesses = enumerateSuccessfulRouteWitnesses(reversedEdgeRoute);
  const pressureNodeIds = route.nodes
    .filter((node) => node.operational_semantic === 'operational_pressure')
    .map((node) => node.node_id);
  const terminalNodeIds = route.nodes.filter((node) => node.terminal).map((node) => node.node_id);
  const requiredTeamworkNodeIds = route.nodes
    .filter((node) => (
      node.operational_semantic === 'communications_relay'
      || node.operational_semantic === 'resource_coordination'
    ))
    .map((node) => node.node_id);
  const pressureNodeId = pressureNodeIds.length === 1 ? pressureNodeIds[0]! : null;
  const terminalNodeId = terminalNodeIds.length === 1 ? terminalNodeIds[0]! : null;
  const pressureWitnesses = pressureNodeId
    ? witnesses.filter((witness) => witness.node_ids.includes(pressureNodeId))
    : [];
  const directWitnesses = pressureNodeId
    ? witnesses.filter((witness) => !witness.node_ids.includes(pressureNodeId))
    : [];
  const pressureWitness = pressureWitnesses.length === 1 ? pressureWitnesses[0]! : null;
  const directWitness = directWitnesses.length === 1 ? directWitnesses[0]! : null;

  const preservesRequiredTeamworkOrder = (witness: ScenarioRouteWitness): boolean => {
    let priorIndex = -1;
    for (const requiredNodeId of requiredTeamworkNodeIds) {
      const occurrences = witness.node_ids.filter((nodeId) => nodeId === requiredNodeId).length;
      const currentIndex = witness.node_ids.indexOf(requiredNodeId);
      if (occurrences !== 1 || currentIndex <= priorIndex) return false;
      priorIndex = currentIndex;
    }
    return true;
  };

  const witnessInventoryStable = canonicalJson(witnesses) === canonicalJson(reorderedWitnesses);
  const witnessReplayStable = witnesses.every((witness) => (
    replayRouteWitness(route, witness)
    && replayRouteWitness(reversedEdgeRoute, witness)
  ));
  const pressureConvergesBeforeRequiredTeamwork = Boolean(
    pressureNodeId
    && pressureWitness
    && directWitness
    && canonicalJson(pressureWitness.node_ids.filter((nodeId) => nodeId !== pressureNodeId))
      === canonicalJson(directWitness.node_ids),
  );
  const everyWitnessTerminates = Boolean(
    terminalNodeId
    && witnesses.every((witness) => (
      witness.node_ids[0] === route.start_node_id
      && witness.node_ids.at(-1) === terminalNodeId
      && witness.terminal_node_id === terminalNodeId
      && witness.edge_ids.length === witness.triggers.length
      && witness.node_ids.length === witness.edge_ids.length + 1
    )),
  );
  const everyWitnessPreservesRequirements = witnesses.every(preservesRequiredTeamworkOrder);

  const pass = validation.valid
    && witnesses.length === 2
    && pressureWitnesses.length === 1
    && directWitnesses.length === 1
    && witnessInventoryStable
    && witnessReplayStable
    && pressureConvergesBeforeRequiredTeamwork
    && everyWitnessTerminates
    && everyWitnessPreservesRequirements;

  return {
    pass,
    detail: [
      `route=${route.route_id}`,
      `valid=${validation.valid}`,
      `witnesses=${witnesses.map((witness) => witness.node_ids.join('>')).join(' | ')}`,
      `required=${requiredTeamworkNodeIds.join('>') || 'none'}`,
      `inventory_stable=${witnessInventoryStable}`,
      `replay_stable=${witnessReplayStable}`,
      `converges=${pressureConvergesBeforeRequiredTeamwork}`,
    ].join(';'),
    witnesses,
    pressure_witness: pressureWitness,
    direct_witness: directWitness,
    required_teamwork_node_ids: requiredTeamworkNodeIds,
  };
}

const combinedFactors: FactorValues = {
  topic: FIELD_VARIANT_BLUEPRINT.allowed_topics,
  ...FIELD_VARIANT_OPERATIONAL_FACTORS,
};
const coveringArray = buildConstraintAwareCoveringArray(combinedFactors, {
  strength: FIELD_VARIANT_OPERATIONAL_COVERAGE_STRENGTH,
  constraints: FIELD_VARIANT_OPERATIONAL_CONSTRAINTS,
  max_cartesian_assignments: 10_000,
  max_constraint_evaluations: 1_000_000,
  max_schedule_rows: 1_000,
});
require(
  coveringArray.certificate.covered_interactions === coveringArray.certificate.required_feasible_interactions,
  'Constraint-aware covering array is incomplete.',
);

const cycles = new Map(FIELD_VARIANT_BLUEPRINT.allowed_topics.map((topicId) => {
  const cycle = buildDeterministicAssignmentCycle(
    FIELD_VARIANT_OPERATIONAL_FACTORS,
    `${FIELD_VARIANT_BLUEPRINT.blueprint_id}:${FIELD_VARIANT_BLUEPRINT.blueprint_version}:${topicId}`,
    {
      constraints: FIELD_VARIANT_OPERATIONAL_CONSTRAINTS,
      max_cartesian_assignments: 10_000,
      max_constraint_evaluations: 1_000_000,
    },
  );
  return [topicId, cycle] as const;
}));
const contextSpace = cycles.values().next().value?.assignments.length ?? 0;
require(contextSpace > 0, 'Operational assignment cycle is empty.');
for (const [topicId, cycle] of cycles) {
  require(cycle.assignments.length === contextSpace, `${topicId} has a different assignment-space size.`);
  require(new Set(cycle.assignments.map(canonicalJson)).size === contextSpace, `${topicId} assignment cycle is not bijective.`);
  const repeated = buildDeterministicAssignmentCycle(
    FIELD_VARIANT_OPERATIONAL_FACTORS,
    `${FIELD_VARIANT_BLUEPRINT.blueprint_id}:${FIELD_VARIANT_BLUEPRINT.blueprint_version}:${topicId}`,
    { constraints: FIELD_VARIANT_OPERATIONAL_CONSTRAINTS },
  );
  require(canonicalJson(cycle) === canonicalJson(repeated), `${topicId} assignment cycle is not deterministic.`);
}

const seedByTopicAndAssignment = new Map<string, number>();
for (const [topicId, cycle] of cycles) {
  cycle.assignments.forEach((assignment, seed) => {
    seedByTopicAndAssignment.set(`${topicId}|${canonicalJson(assignment)}`, seed);
  });
}

const observedValues = new Map(Object.keys(combinedFactors).map((name) => [name, new Set<string>()] as const));
const operationalContexts = new Set<string>();
const packageHashes = new Set<string>();
const realizedRows: Array<{ topic: string; seed: number; row_sha256: string; package_sha256: string }> = [];
const behaviorCandidateInputs: ScenarioBehaviorCandidateInput[] = [];
let experienceChecks = 0;
let independentChecks = 0;
let deterministicRepeats = 0;
let evidenceNonAuthoringCases = 0;

for (const expectedRow of coveringArray.rows) {
  const topicId = expectedRow.topic;
  require(
    FIELD_VARIANT_BLUEPRINT.allowed_topics.includes(topicId as (typeof FIELD_VARIANT_BLUEPRINT.allowed_topics)[number]),
    `Covering array emitted unknown topic ${topicId}.`,
  );
  const expectedOperational = operationalRow(expectedRow);
  const seed = seedByTopicAndAssignment.get(`${topicId}|${canonicalJson(expectedOperational)}`);
  require(seed !== undefined, `No deterministic seed realizes covering row ${canonicalJson(expectedRow)}.`);
  const request = {
    topic_id: topicId as (typeof FIELD_VARIANT_BLUEPRINT.allowed_topics)[number],
    seed,
    retriever_track: bridge.retrieval_release.default_research_sandbox_retriever,
  } as const;
  const generated = buildTemplateLockedScenario(bridge, request);
  const actualRow = contextRow(topicId, generated);
  require(canonicalJson(actualRow) === canonicalJson(expectedRow), `Seed ${topicId}/${seed} did not realize its certified covering row.`);

  const report = validateScenarioExperience(generated);
  require(report.status === 'PASS', `${topicId}/${seed} failed experience assurance: ${JSON.stringify(report.issues)}`);
  experienceChecks += report.checks_run;

  const repeated = buildTemplateLockedScenario(bridge, request);
  require(canonicalJson(generated) === canonicalJson(repeated), `${topicId}/${seed} is not deterministic.`);
  deterministicRepeats += 1;

  const independent = await verifyScenarioPackage(sourceScenario, generated, bridge);
  require(independent.status === 'PASS', `${topicId}/${seed} failed the independent package checker.`);
  independentChecks += independent.checks_run;
  behaviorCandidateInputs.push({
    generated,
    experience_checks: report.checks_run,
    independent_checks: independent.checks_run,
  });

  const scenarioText = canonicalJson({
    title: generated.scenario.title,
    notice: generated.scenario.fictionalization_notice,
    narrative: generated.scenario.operational_context.narrative,
  }).toLowerCase();
  require(
    generated.evidence.every((item) => (
      !scenarioText.includes(item.evidence_id.toLowerCase())
      && !scenarioText.includes(item.doi.toLowerCase())
    )),
    `${topicId}/${seed} copied citation metadata into scenario prose.`,
  );
  evidenceNonAuthoringCases += 1;

  for (const [name, value] of Object.entries(actualRow)) observedValues.get(name)?.add(value);
  operationalContexts.add(canonicalJson(generated.scenario.operational_context));
  packageHashes.add(generated.certificate.package_sha256);
  realizedRows.push({
    topic: topicId,
    seed,
    row_sha256: generated.certificate.atom_root_sha256,
    package_sha256: generated.certificate.package_sha256,
  });
}

const missingValues = Object.entries(combinedFactors).flatMap(([name, values]) => (
  values.filter((value) => !observedValues.get(name)?.has(value)).map((value) => `${name}=${value}`)
));
require(missingValues.length === 0, `Generator did not emit reviewed factor values: ${missingValues.join(', ')}`);
require(packageHashes.size === coveringArray.rows.length, 'Distinct covering rows produced duplicate certified packages.');
require(realizedRows.length === coveringArray.certificate.schedule_rows, 'Not every covering row was realized by the generator.');

const relationChecks: Array<{ id: string; pass: boolean; detail?: string }> = [];
const request = {
  topic_id: FIELD_VARIANT_BLUEPRINT.allowed_topics[0]!,
  seed: 41027,
  retriever_track: bridge.retrieval_release.default_research_sandbox_retriever,
} as const;
const baseline = buildTemplateLockedScenario(bridge, request);
const reordered = {
  ...bridge,
  sources: [...bridge.sources].reverse(),
  evidence_refs: [...bridge.evidence_refs].reverse(),
  prototypes: [...bridge.prototypes].reverse(),
};
relationChecks.push({
  id: 'bridge_record_order_independence',
  pass: canonicalJson(baseline) === canonicalJson(buildTemplateLockedScenario(reordered, request)),
});

const unrelated = clone(bridge);
unrelated.sources.push({
  source_index: 999_999,
  source_id: 'unrelated-source',
  title: 'Unrelated administrative record',
  journal: 'Fixture',
  doi: '10.0000/unrelated',
  publication_date: '2026-01-01',
  source_file_sha256: 'a'.repeat(64),
});
const unrelatedPackage = buildTemplateLockedScenario(unrelated, request);
relationChecks.push({
  id: 'unrelated_source_changes_provenance_not_scenario_behavior',
  pass: canonicalJson(baseline.scenario) === canonicalJson(unrelatedPackage.scenario)
    && canonicalJson(baseline.route) === canonicalJson(unrelatedPackage.route)
    && canonicalJson(protectedScenarioProjection(baseline.scenario)) === canonicalJson(protectedScenarioProjection(unrelatedPackage.scenario))
    && baseline.build.source_bridge_sha256 !== unrelatedPackage.build.source_bridge_sha256
    && baseline.certificate.package_sha256 !== unrelatedPackage.certificate.package_sha256,
});

const alternateTrack = bridge.prototypes.find((item) => (
  item.topic_id === request.topic_id && item.retriever_track !== request.retriever_track
))?.retriever_track;
require(Boolean(alternateTrack), 'No alternate retriever track is available for metamorphic assurance.');
const alternateRetriever = buildTemplateLockedScenario(bridge, { ...request, retriever_track: alternateTrack! });
relationChecks.push({
  id: 'retriever_changes_evidence_not_operational_behavior',
  pass: canonicalJson(baseline.scenario) === canonicalJson(alternateRetriever.scenario)
    && canonicalJson(baseline.route) === canonicalJson(alternateRetriever.route)
    && canonicalJson(protectedScenarioProjection(baseline.scenario)) === canonicalJson(protectedScenarioProjection(alternateRetriever.scenario))
    && baseline.build.source_prototype_record_sha256 !== alternateRetriever.build.source_prototype_record_sha256
    && baseline.certificate.package_sha256 !== alternateRetriever.certificate.package_sha256,
});

const baselineBehaviorSignature = scenarioBehaviorSignature(buildScenarioBehaviorDescriptor(baseline));
const provenanceOnlyBehaviorSignature = scenarioBehaviorSignature(buildScenarioBehaviorDescriptor(unrelatedPackage));
const retrieverOnlyBehaviorSignature = scenarioBehaviorSignature(buildScenarioBehaviorDescriptor(alternateRetriever));
const narrativeOnlyVariant = clone(baseline);
narrativeOnlyVariant.scenario.title = `${narrativeOnlyVariant.scenario.title} — alternate learner-facing wording`;
narrativeOnlyVariant.scenario.operational_context.narrative = `${narrativeOnlyVariant.scenario.operational_context.narrative} Facilitator wording may vary.`;
const narrativeOnlyBehaviorSignature = scenarioBehaviorSignature(buildScenarioBehaviorDescriptor(narrativeOnlyVariant));
const changedOperationalVariant = buildTemplateLockedScenario(bridge, { ...request, seed: request.seed + 1 });
const changedOperationalBehaviorSignature = scenarioBehaviorSignature(buildScenarioBehaviorDescriptor(changedOperationalVariant));
relationChecks.push({
  id: 'provenance_only_change_does_not_create_new_behavior',
  pass: baselineBehaviorSignature === provenanceOnlyBehaviorSignature,
});
relationChecks.push({
  id: 'retriever_only_change_does_not_create_new_behavior',
  pass: baselineBehaviorSignature === retrieverOnlyBehaviorSignature,
});
relationChecks.push({
  id: 'narrative_only_change_does_not_create_new_behavior',
  pass: baselineBehaviorSignature === narrativeOnlyBehaviorSignature,
});
relationChecks.push({
  id: 'operational_factor_change_creates_new_behavior',
  pass: baselineBehaviorSignature !== changedOperationalBehaviorSignature,
});

const baselineRouteWitnessAudit = auditProfileRouteWitnesses(baseline.route);
relationChecks.push({
  id: 'successful_route_witness_inventory_is_complete',
  pass: baselineRouteWitnessAudit.witnesses.length === 2
    && Boolean(baselineRouteWitnessAudit.pressure_witness)
    && Boolean(baselineRouteWitnessAudit.direct_witness),
  detail: baselineRouteWitnessAudit.detail,
});
relationChecks.push({
  id: 'pressure_branch_reaches_completion',
  pass: Boolean(baselineRouteWitnessAudit.pressure_witness),
  detail: baselineRouteWitnessAudit.pressure_witness?.node_ids.join('>') ?? 'missing',
});
relationChecks.push({
  id: 'direct_handoff_branch_reaches_completion',
  pass: Boolean(baselineRouteWitnessAudit.direct_witness),
  detail: baselineRouteWitnessAudit.direct_witness?.node_ids.join('>') ?? 'missing',
});
relationChecks.push({
  id: 'route_witness_replay_is_edge_order_independent',
  pass: baselineRouteWitnessAudit.pass,
  detail: baselineRouteWitnessAudit.detail,
});
relationChecks.push({
  id: 'every_successful_route_preserves_teamwork_requirements',
  pass: baselineRouteWitnessAudit.pass,
  detail: `required=${baselineRouteWitnessAudit.required_teamwork_node_ids.join('>') || 'none'}`,
});
relationChecks.push({
  id: 'optional_pressure_branch_converges_before_required_teamwork',
  pass: baselineRouteWitnessAudit.pass,
  detail: baselineRouteWitnessAudit.detail,
});

for (const profile of SCENARIO_OPERATIONAL_BEHAVIOR_PROFILES) {
  const route = buildFieldRoute(`ASK-EXPERIENCE-PROFILE-${profile.profile_id}`, profile.profile_id);
  const audit = auditProfileRouteWitnesses(route);
  relationChecks.push({
    id: `profile_${profile.profile_id.toLowerCase()}_graph_derived_witnesses_preserve_requirements`,
    pass: audit.pass,
    detail: audit.detail,
  });
}

const firstCycle = cycles.get(request.topic_id)!;
const cycleStart = buildTemplateLockedScenario(bridge, { ...request, seed: 0 });
const cycleRepeat = buildTemplateLockedScenario(bridge, { ...request, seed: firstCycle.assignments.length });
relationChecks.push({
  id: 'operational_assignment_cycle_is_complete_and_periodic',
  pass: canonicalJson(cycleStart.scenario.operational_context) === canonicalJson(cycleRepeat.scenario.operational_context)
    && cycleStart.certificate.package_sha256 !== cycleRepeat.certificate.package_sha256,
  detail: `cycle_length=${firstCycle.assignments.length}`,
});

require(relationChecks.every((item) => item.pass), `Metamorphic relationship failed: ${JSON.stringify(relationChecks)}`);

const behaviorArchive = buildScenarioBehaviorArchive(behaviorCandidateInputs);
require(behaviorArchive.summary.candidate_count === realizedRows.length, 'Behavior archive candidate inventory differs from the realized covering schedule.');
require(behaviorArchive.summary.total_strength_three_interactions_observed === coveringArray.certificate.required_feasible_interactions, 'Behavior archive interaction inventory differs from the covering-array certificate.');
require(behaviorArchive.summary.occupied_cells === behaviorArchive.summary.possible_cells_in_observed_domain, 'Behavior archive does not occupy every topic/feasible-operational-policy-shape cell in the observed domain.');

const report = {
  schema_version: '1.2.0',
  classification: 'PASS',
  status: 'PASS',
  assurance_profile: 'CONSTRAINT_AWARE_THREE_WAY_COVERING_ARRAY_AND_BIJECTIVE_CONTEXT_CYCLE_V1',
  generated_cases: realizedRows.length,
  topics_checked: FIELD_VARIANT_BLUEPRINT.allowed_topics.length,
  deterministic_repeats: deterministicRepeats,
  unique_certified_packages: packageHashes.size,
  unique_operational_contexts: operationalContexts.size,
  total_operational_context_space_per_topic: contextSpace,
  complete_assignment_cycle_verified_for_each_topic: true,
  missing_reviewed_factor_values: missingValues,
  experience_checks: experienceChecks,
  independent_checks: independentChecks,
  evidence_non_authoring_cases: evidenceNonAuthoringCases,
  covering_array: coveringArray.certificate,
  assignment_cycles: Object.fromEntries([...cycles].map(([topic, cycle]) => [topic, cycle.certificate])),
  realized_rows: realizedRows,
  relation_checks: relationChecks,
  behavior_archive: {
    path: 'reports/scenario-behavior-archive.json',
    archive_root_sha256: behaviorArchive.archive_root_sha256,
    archive_profile: behaviorArchive.archive_profile,
    behavior_descriptor_profile: behaviorArchive.behavior_descriptor_profile,
    cell_profile: behaviorArchive.cell_profile,
    quality_profile: behaviorArchive.quality_profile,
    selection_boundary: behaviorArchive.selection_boundary,
    ...behaviorArchive.summary,
  },
  truth_boundaries: {
    clinical_authority: 'NOT_GRANTED',
    patient_care_use: 'PROHIBITED',
    operational_timing: 'NOT_CALIBRATED',
    human_team_behavior: 'STRUCTURAL_ONLY_NOT_CALIBRATED',
    patient_dynamics: 'SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY',
    quality_vector_use: 'SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING',
    source_templates_clinically_certified: 0,
  },
};

const archiveOutput = resolve(root, 'reports/scenario-behavior-archive.json');
const output = resolve(root, 'reports/scenario-experience-assurance.json');
await atomicWriteJson(archiveOutput, behaviorArchive);
await atomicWriteJson(output, report);
console.log(JSON.stringify(report, null, 2));
