import { spawnSync } from 'node:child_process';
import { checkRepositoryVocabulary } from './checkRepositoryVocabulary';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { scenariosById } from '../src/content/scenarios';
import type { ResearchRuntimeBridge } from '../src/research/types';
import { verifyScenarioPackage } from '../src/scenario-checker/verify';
import type { VerifiedScenarioPackage } from '../src/scenario-core/types';
import { validateScenarioPackage } from '../src/scenario-core/validator';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const packagePath = resolve(root, 'public/data/scenario_core/verified_scenario_package.json');
const bridgePath = resolve(root, 'public/data/research_sandbox/runtime_bridge.json');
const assurancePath = resolve(root, 'reports/scenario-contract-assurance.json');
const snapshotPath = resolve(root, 'config/scenario-contracts/ASK-A-001.json');

const generated = JSON.parse(await readFile(packagePath, 'utf8')) as VerifiedScenarioPackage;
const bridge = JSON.parse(await readFile(bridgePath, 'utf8')) as ResearchRuntimeBridge;
const assurance = JSON.parse(await readFile(assurancePath, 'utf8')) as Record<string, unknown>;
const base = scenariosById[generated.build.source_scenario_id];
if (!base) throw new Error(`Missing source scenario ${generated.build.source_scenario_id}.`);

const local = validateScenarioPackage(generated, bridge);
const independent = await verifyScenarioPackage(base, generated, bridge);
type PythonReport = { status: string; errors: string[]; checks: number };
const pythonExecutionErrors: string[] = [];
const pythonExecution = spawnSync('python3', [
  resolve(root, 'scripts/check_scenario_certificate.py'),
  '--package', packagePath,
  '--source-snapshot', snapshotPath,
  '--bridge', bridgePath,
], { cwd: root, encoding: 'utf8' });
let pythonReport: PythonReport = { status: 'FAIL', errors: [], checks: 0 };
if (pythonExecution.error) {
  pythonExecutionErrors.push(`python checker could not start: ${pythonExecution.error.message}`);
} else {
  const stdout = pythonExecution.stdout?.trim() ?? '';
  try {
    pythonReport = JSON.parse(stdout) as PythonReport;
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    pythonExecutionErrors.push(`python checker emitted invalid JSON: ${detail}`);
  }
  if (pythonExecution.status !== 0) {
    const stderr = pythonExecution.stderr?.trim().slice(-2000) ?? '';
    pythonExecutionErrors.push(`python checker exited ${pythonExecution.status ?? 'without status'}${stderr ? `: ${stderr}` : ''}`);
  }
}

const formalFiles = [
  'formal/ScenarioContracts.lean',
  'formal/ScenarioContracts/Basic.lean',
  'formal/ScenarioContracts/Route.lean',
  'formal/ScenarioContracts/Origin.lean',
  'formal/ScenarioContracts/Certificate.lean',
];
const formalSource = (await Promise.all(
  formalFiles.map((path) => readFile(resolve(root, path), 'utf8')),
)).join('\n');
const errors: string[] = [...pythonExecutionErrors];
if (local.status !== 'PASS') errors.push(...local.issues.map((item) => `local:${item.path}:${item.message}`));
if (independent.status !== 'PASS') errors.push(...independent.issues.map((item) => `independent:${item.path}:${item.message}`));
if (pythonReport.status !== 'PASS') errors.push(...pythonReport.errors.map((item) => `python:${item}`));
if (assurance.status !== 'PASS') errors.push('assurance report is not PASS');
if (/\bsorry\b/.test(formalSource)) errors.push('formal source contains an incomplete proof placeholder');
if (generated.evidence.some((item) => !/^[a-f0-9]{64}$/.test(item.chunk_sha256) || !/^[a-f0-9]{64}$/.test(item.source_file_sha256))) {
  errors.push('evidence hash format failure');
}
if (generated.authority.clinical_authority !== 'NOT_GRANTED') errors.push('clinical authority was widened');
if (generated.authority.deployment_scope !== 'research_sandbox_only') errors.push('deployment scope was widened');
if (generated.authority.source_template_status !== 'repository_template_not_clinically_certified') errors.push('source template status was overstated');
if (generated.authority.clinical_rule_source !== 'inherited_template') errors.push('clinical rule source was changed');
if (generated.authority.evidence_authority !== 'supporting_only') errors.push('evidence authority was widened');
if (generated.authority.evidence_effect_scope !== 'citation_support_only') errors.push('evidence scope widened');
if (generated.authority.scoring_behavior !== 'inherited_unchanged') errors.push('scoring behavior changed');

const vocabularyReport = await checkRepositoryVocabulary(root);
if (vocabularyReport.status !== 'PASS') {
  errors.push(`repository vocabulary gate failed: ${JSON.stringify(vocabularyReport.findings)}`);
}

const report = {
  schema_version: '1.0.0',
  status: errors.length === 0 ? 'READY_FOR_MODEL_ASSISTED_BUILD' : 'FAIL',
  scenario_id: generated.scenario.scenario_id,
  source_scenario_id: generated.build.source_scenario_id,
  package_sha256: generated.certificate.package_sha256,
  evidence_references: generated.evidence.length,
  route_nodes: generated.route.nodes.length,
  route_edges: generated.route.edges.length,
  local_checks: local.checks_run,
  independent_typescript_checks: independent.checks_run,
  independent_python_checks: pythonReport.checks,
  generated_cases: assurance.generated_cases,
  relation_checks: assurance.relation_checks,
  pair_schedule_cases: assurance.pair_schedule_cases,
  fault_challenges: assurance.fault_challenges,
  fault_challenges_rejected: assurance.fault_challenges_rejected,
  formal_modules: formalFiles.length,
  deployment_scope: generated.authority.deployment_scope,
  source_template_status: generated.authority.source_template_status,
  clinical_rule_source: generated.authority.clinical_rule_source,
  evidence_authority: generated.authority.evidence_authority,
  evidence_scope: generated.authority.evidence_effect_scope,
  scoring_behavior: generated.authority.scoring_behavior,
  build_time_proposal_gate: 'reviewed_source_bound_allowlist',
  formal_verification: 'github_ci_kernel_build_fresh_replay_and_axiom_audit',
  errors,
  next_gate: 'Connect a server-side model to the proposal schema, then require the same certificate and checker gates before publication.',
};

const output = resolve(root, 'reports/scenario-contracts-rc2-validation.json');
await mkdir(dirname(output), { recursive: true });
await writeFile(output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');

console.log('\n================ SCENARIO CONTRACT RELEASE ================');
console.log(JSON.stringify(report, null, 2));
console.log('===========================================================');
if (errors.length > 0) process.exitCode = 3;
