import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { ResearchRuntimeBridge } from '../src/research/types';
import { generateResearchScenario } from '../src/scenario-generation/generator';
import { validateGeneratedResearchScenario } from '../src/scenario-generation/validator';
import type { ScenarioEvidenceTopic } from '../src/scenario-generation/types';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const bridgePath = resolve(root, 'public/data/research_sandbox/runtime_bridge.json');
const bridge = JSON.parse(readFileSync(bridgePath, 'utf8')) as ResearchRuntimeBridge;
const requestedTopic = (process.argv.find((value) => value.startsWith('--topic='))?.split('=', 2)[1] ?? 'airway') as ScenarioEvidenceTopic;
const seed = Number(process.argv.find((value) => value.startsWith('--seed='))?.split('=', 2)[1] ?? '20260727');
const generated = generateResearchScenario(bridge, {
  topic_id: requestedTopic,
  seed,
  retriever_track: bridge.retrieval_release.default_research_sandbox_retriever,
});
const validation = validateGeneratedResearchScenario(generated);
if (validation.status !== 'PASS') {
  throw new Error(validation.issues.map((item) => `${item.path}: ${item.message}`).join('\n'));
}
const outputPath = resolve(root, 'public/data/research_sandbox/generated_scenario.json');
mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, `${JSON.stringify({ generated, validation }, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({
  status: 'PASS',
  scenario_id: generated.scenario.scenario_id,
  topic_id: generated.generator.topic_id,
  citations: generated.evidence.length,
  checked_invariants: validation.checked_invariants,
  output: outputPath,
}, null, 2));
