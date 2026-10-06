import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { scenariosById } from '../src/content/scenarios';
import type { ResearchRuntimeBridge } from '../src/research/types';
import { verifyScenarioPackage } from '../src/scenario-checker/verify';
import { buildTemplateLockedScenario } from '../src/scenario-core/assembly';
import { validateScenarioExperience } from '../src/scenario-core/experience';
import { validateScenarioPackage } from '../src/scenario-core/validator';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const bridgePath = resolve(root, 'public/data/research_sandbox/runtime_bridge.json');
const bridge = JSON.parse(await readFile(bridgePath, 'utf8')) as ResearchRuntimeBridge;
const generated = buildTemplateLockedScenario(bridge, {
  topic_id: 'massive_hemorrhage',
  seed: 41027,
  retriever_track: bridge.retrieval_release.default_research_sandbox_retriever,
});
const base = scenariosById[generated.build.source_scenario_id];
if (!base) throw new Error(`Missing source scenario ${generated.build.source_scenario_id}.`);

const local = validateScenarioPackage(generated, bridge);
const independent = await verifyScenarioPackage(base, generated, bridge);
const experience = validateScenarioExperience(generated);
if (local.status !== 'PASS' || independent.status !== 'PASS' || experience.status !== 'PASS') {
  throw new Error(JSON.stringify({ local, independent, experience }, null, 2));
}

async function writeJson(relative: string, value: unknown): Promise<void> {
  const path = resolve(root, relative);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

await writeJson('public/data/scenario_core/verified_scenario_package.json', generated);
await writeJson('public/data/scenario_core/verified_scenario.json', generated.scenario);
await writeJson('reports/scenario-package-generation.json', {
  status: 'PASS',
  scenario_id: generated.scenario.scenario_id,
  source_scenario_id: generated.build.source_scenario_id,
  topic_id: generated.build.topic_id,
  evidence_references: generated.evidence.length,
  route_nodes: generated.route.nodes.length,
  route_edges: generated.route.edges.length,
  local_checks: local.checks_run,
  independent_checks: independent.checks_run,
  experience_checks: experience.checks_run,
  route_maximum_steps: experience.metrics.maximum_route_steps,
  package_sha256: generated.certificate.package_sha256,
});

console.log('\n================ VERIFIED SCENARIO PACKAGE ================');
console.log(JSON.stringify({
  status: 'PASS',
  scenario_id: generated.scenario.scenario_id,
  source_scenario_id: generated.build.source_scenario_id,
  topic_id: generated.build.topic_id,
  evidence_references: generated.evidence.length,
  route_nodes: generated.route.nodes.length,
  local_checks: local.checks_run,
  independent_checks: independent.checks_run,
  experience_checks: experience.checks_run,
  route_maximum_steps: experience.metrics.maximum_route_steps,
  package_sha256: generated.certificate.package_sha256,
}, null, 2));
console.log('===========================================================');
