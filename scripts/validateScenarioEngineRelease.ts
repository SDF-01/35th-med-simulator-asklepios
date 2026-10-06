import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { ResearchRuntimeBridge } from '../src/research/types';
import { validatePublicResearchBridge } from '../src/research/validation';
import type { GeneratedResearchScenario, ScenarioValidationReport } from '../src/scenario-generation/types';
import { validateGeneratedResearchScenario } from '../src/scenario-generation/validator';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const errors: string[] = [];
const bridgePath = resolve(root, 'public/data/research_sandbox/runtime_bridge.json');
const generatedPath = resolve(root, 'public/data/research_sandbox/generated_scenario.json');

let bridge: ResearchRuntimeBridge | null = null;
try {
  bridge = validatePublicResearchBridge(JSON.parse(readFileSync(bridgePath, 'utf8')) as ResearchRuntimeBridge);
} catch (error) {
  errors.push(`bridge:${error instanceof Error ? error.message : String(error)}`);
}

let validation: ScenarioValidationReport | null = null;
let generated: GeneratedResearchScenario | null = null;
try {
  const payload = JSON.parse(readFileSync(generatedPath, 'utf8')) as {
    generated: GeneratedResearchScenario;
    validation?: ScenarioValidationReport;
  };
  generated = payload.generated;
  validation = validateGeneratedResearchScenario(generated);
  if (validation.status !== 'PASS') errors.push('generated scenario failed validation');
} catch (error) {
  errors.push(`generated:${error instanceof Error ? error.message : String(error)}`);
}

for (const stalePath of [
  'docs/jem-evidence-registry.md',
  'scripts/validate-jem-evidence-registry.mjs',
  'src/content/evidence/jemEvidenceRegistry.ts',
]) {
  if (existsSync(resolve(root, stalePath))) errors.push(`stale registry remains:${stalePath}`);
}

const appText = readFileSync(resolve(root, 'src/App.tsx'), 'utf8');
if (!appText.includes('/research-sandbox')) errors.push('research sandbox route is missing');

const report = {
  schema_version: '1.0.0',
  status: errors.length === 0 ? 'PASS' : 'FAIL',
  errors,
  bridge: bridge
    ? { sources: bridge.sources.length, evidence_refs: bridge.evidence_refs.length, prototypes: bridge.prototypes.length }
    : null,
  generated_scenario: generated
    ? {
        scenario_id: generated.scenario.scenario_id,
        topic_id: generated.generator.topic_id,
        seed: generated.generator.seed,
        citations: generated.evidence.length,
        fingerprint: generated.content_fingerprint,
        clinical_authority: generated.authority.clinical_authority,
        scoring_enabled: generated.authority.scoring_enabled,
      }
    : null,
  checked_invariants: validation?.checked_invariants ?? 0,
  production_scored_path_modified: false,
};

const output = resolve(root, 'reports/scenario-engine-rc1-validation.json');
mkdirSync(dirname(output), { recursive: true });
writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(report, null, 2));
if (errors.length > 0) process.exit(3);
