import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { scenariosById } from '../src/content/scenarios';
import type { ResearchRuntimeBridge } from '../src/research/types';
import { verifyScenarioPackage } from '../src/scenario-checker/verify';
import { buildTemplateLockedScenario } from '../src/scenario-core/assembly';
import { FIELD_VARIANT_BLUEPRINT } from '../src/scenario-core/blueprints';
import { buildPairCoverageSchedule, countUncoveredPairs } from '../src/scenario-core/coverage';
import { canonicalJson } from '../src/scenario-core/hash';
import { protectedScenarioProjection } from '../src/scenario-core/projection';
import { selectNextNode } from '../src/scenario-core/route';
import type { VerifiedScenarioPackage } from '../src/scenario-core/types';
import { validateScenarioPackage } from '../src/scenario-core/validator';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const bridge = JSON.parse(
  await readFile(resolve(root, 'public/data/research_sandbox/runtime_bridge.json'), 'utf8'),
) as ResearchRuntimeBridge;
const base = scenariosById[FIELD_VARIANT_BLUEPRINT.source_scenario_id];
if (!base) throw new Error('Source scenario is missing.');

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const contexts = new Set<string>();
const packageHashes = new Set<string>();
let generatedCases = 0;
let localChecks = 0;
let independentChecks = 0;

for (const topicId of FIELD_VARIANT_BLUEPRINT.allowed_topics) {
  for (let seed = 0; seed < 128; seed += 1) {
    const generated = buildTemplateLockedScenario(bridge, {
      topic_id: topicId,
      seed,
      retriever_track: bridge.retrieval_release.default_research_sandbox_retriever,
    });
    const local = validateScenarioPackage(generated, bridge);
    if (local.status !== 'PASS') throw new Error(`Local validation failed for ${topicId}/${seed}.`);
    localChecks += local.checks_run;
    if (seed % 8 === 0) {
      const independent = await verifyScenarioPackage(base, generated, bridge);
      if (independent.status !== 'PASS') throw new Error(`Independent validation failed for ${topicId}/${seed}.`);
      independentChecks += independent.checks_run;
    }
    if (canonicalJson(protectedScenarioProjection(generated.scenario)) !== canonicalJson(protectedScenarioProjection(base))) {
      throw new Error(`Protected projection changed for ${topicId}/${seed}.`);
    }
    generatedCases += 1;
    packageHashes.add(generated.certificate.package_sha256);
    contexts.add(canonicalJson(generated.scenario.operational_context));
  }
}

const relationChecks: Array<{ id: string; pass: boolean }> = [];
const request = { topic_id: 'massive_hemorrhage' as const, seed: 41027, retriever_track: 'hybrid_cc_loto' };
const baseline = buildTemplateLockedScenario(bridge, request);
const repeated = buildTemplateLockedScenario(bridge, request);
relationChecks.push({ id: 'repeatability', pass: canonicalJson(baseline) === canonicalJson(repeated) });

const reordered = {
  ...bridge,
  sources: [...bridge.sources].reverse(),
  evidence_refs: [...bridge.evidence_refs].reverse(),
  prototypes: [...bridge.prototypes].reverse(),
};
relationChecks.push({
  id: 'record_order_independence',
  pass: canonicalJson(baseline) === canonicalJson(buildTemplateLockedScenario(reordered, request)),
});

const changedSeed = buildTemplateLockedScenario(bridge, { ...request, seed: request.seed + 1 });
relationChecks.push({
  id: 'seed_changes_admitted_fields_only',
  pass: baseline.certificate.package_sha256 !== changedSeed.certificate.package_sha256
    && canonicalJson(protectedScenarioProjection(baseline.scenario))
      === canonicalJson(protectedScenarioProjection(changedSeed.scenario)),
});
const firstRequiredOperationalNode = baseline.route.nodes.find((node) => node.operational_semantic === 'communications_relay')
  ?? baseline.route.nodes.find((node) => node.operational_semantic === 'resource_coordination')
  ?? baseline.route.nodes.find((node) => node.node_id === 'handoff');
if (!firstRequiredOperationalNode) throw new Error('Route is missing the first required operational node.');
const reversedEdgeRoute = { ...baseline.route, edges: [...baseline.route.edges].reverse() };
relationChecks.push({
  id: 'route_priority_is_deterministic',
  pass: selectNextNode(baseline.route, 'contact', 'facilitator_event') === 'pressure'
    && selectNextNode(reversedEdgeRoute, 'contact', 'facilitator_event') === 'pressure'
    && selectNextNode(baseline.route, 'contact', 'handoff_ready') === firstRequiredOperationalNode.node_id
    && selectNextNode(reversedEdgeRoute, 'contact', 'handoff_ready') === firstRequiredOperationalNode.node_id
    && selectNextNode(baseline.route, 'pressure', 'handoff_ready') === firstRequiredOperationalNode.node_id
    && selectNextNode(reversedEdgeRoute, 'pressure', 'handoff_ready') === firstRequiredOperationalNode.node_id,
});

if (relationChecks.some((item) => !item.pass)) {
  throw new Error(`Relationship check failed: ${JSON.stringify(relationChecks)}`);
}

const factors = {
  topic: FIELD_VARIANT_BLUEPRINT.allowed_topics,
  location: FIELD_VARIANT_BLUEPRINT.location_options,
  weather: FIELD_VARIANT_BLUEPRINT.weather_options,
  visibility: FIELD_VARIANT_BLUEPRINT.visibility_options,
  communications: FIELD_VARIANT_BLUEPRINT.communications_options,
  resources: FIELD_VARIANT_BLUEPRINT.resource_options,
} as const;
const pairSchedule = buildPairCoverageSchedule(factors);
const uncoveredPairs = countUncoveredPairs(pairSchedule, factors);
if (uncoveredPairs !== 0) throw new Error(`Coverage schedule missed ${uncoveredPairs} pairs.`);

const challenges: Array<[string, (value: VerifiedScenarioPackage) => void]> = [
  ['protected_action', (value) => { value.scenario.expected_actions.critical[0]!.points += 1; }],
  ['patient_vital', (value) => { value.scenario.patients[0]!.initial_vitals.hr += 1; }],
  ['end_condition', (value) => { value.scenario.end_conditions.success.push('unexpected'); }],
  ['teaching_point', (value) => { value.scenario.aar_teaching_points[0] = 'changed'; }],
  ['scenario_id', (value) => { value.scenario.scenario_id = 'ASK-V-TAMPERED'; }],
  ['narrative', (value) => { value.scenario.operational_context.narrative += ' changed'; }],
  ['blueprint_scope', (value) => { value.blueprint.mutable_paths.push('scenario.patients'); }],
  ['route_destination', (value) => { value.route.edges[0]!.to = 'missing'; }],
  ['route_terminal', (value) => { value.route.nodes.at(-1)!.terminal = false; }],
  ['route_ambiguity', (value) => { value.route.edges.push({ ...value.route.edges[0]!, edge_id: 'duplicate' }); }],
  ['chunk_hash', (value) => { value.evidence[0]!.chunk_sha256 = '1'.repeat(64); }],
  ['source_hash', (value) => { value.evidence[0]!.source_file_sha256 = '2'.repeat(64); }],
  ['duplicate_evidence', (value) => { value.evidence[1]!.evidence_id = value.evidence[0]!.evidence_id; }],
  ['atom_hash', (value) => { value.atoms[0]!.atom_sha256 = '3'.repeat(64); }],
  ['atom_scope', (value) => { value.atoms.find((atom) => atom.authority === 'nonclinical')!.evidence_ids = [value.evidence[0]!.evidence_id]; }],
  ['origin_removed', (value) => { value.field_origins = value.field_origins.filter((origin) => origin.field_path !== 'scenario.operational_context.weather'); }],
  ['origin_atom', (value) => { value.field_origins[1]!.atom_ids = ['missing']; }],
  ['stage_input', (value) => { value.stages[2]!.input_sha256 = '4'.repeat(64); }],
  ['stage_payload', (value) => { value.stages[2]!.payload_sha256 = '5'.repeat(64); }],
  ['stage_output', (value) => { value.stages[2]!.output_sha256 = '6'.repeat(64); }],
  ['authority', (value) => { (value.authority as { evidence_authority: string }).evidence_authority = 'other'; }],
  ['bridge_binding', (value) => { value.build.source_bridge_sha256 = '7'.repeat(64); }],
  ['prototype_binding', (value) => { value.build.source_prototype_record_sha256 = '8'.repeat(64); }],
  ['package_hash', (value) => { value.certificate.package_sha256 = '9'.repeat(64); }],
];

let rejectedChallenges = 0;
for (const [label, mutate] of challenges) {
  const candidate = clone(baseline);
  mutate(candidate);
  const result = await verifyScenarioPackage(base, candidate, bridge);
  if (result.status !== 'FAIL') throw new Error(`Challenge ${label} was not rejected.`);
  rejectedChallenges += 1;
}

const report = {
  schema_version: '1.0.0',
  status: 'PASS',
  generated_cases: generatedCases,
  topics: FIELD_VARIANT_BLUEPRINT.allowed_topics.length,
  unique_packages: packageHashes.size,
  unique_operational_contexts: contexts.size,
  local_checks: localChecks,
  independent_checks: independentChecks,
  relation_checks: relationChecks,
  pair_schedule_cases: pairSchedule.length,
  uncovered_pairs: uncoveredPairs,
  fault_challenges: challenges.length,
  fault_challenges_rejected: rejectedChallenges,
  protected_source_scenario: base.scenario_id,
};

const output = resolve(root, 'reports/scenario-contract-assurance.json');
await mkdir(dirname(output), { recursive: true });
await writeFile(output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');

console.log('\n================ SCENARIO CONTRACT ASSURANCE ================');
console.log(JSON.stringify(report, null, 2));
console.log('=============================================================');
