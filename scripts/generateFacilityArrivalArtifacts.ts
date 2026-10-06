import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, relative, resolve } from 'node:path';
import { scenariosById } from '../src/content/scenarios';
import { sha256Canonical, sha256Text } from '../src/scenario-core/hash';
import {
  buildFacilityAar,
  buildFacilityClaimLedger,
  runCanonicalFacilitySession,
  validateFacilitySession,
} from '../src/facility-arrival/engine';
import { facilityArrivalContext } from '../src/facility-arrival/context';
import { graphContractSha256, renderEvolutionBlock } from './engine_evolution_documentation_common.mjs';
import type { ExpectedAction } from '../src/types';

const repo = resolve(process.cwd());
const check = process.argv.includes('--check');
if (!check) {
  throw new Error('TypeScript Facility Arrival generation is verification-only; use npm run generate:facility-arrival.');
}
const outputIndex = process.argv.indexOf('--json-output');
const jsonOutput = outputIndex >= 0 ? process.argv[outputIndex + 1] : undefined;
if (outputIndex >= 0 && (!jsonOutput || jsonOutput.startsWith('--'))) {
  throw new Error('--json-output requires a repository-relative path');
}
const outputPath = jsonOutput ? resolve(repo, jsonOutput) : undefined;
const outputRelative = outputPath ? relative(repo, outputPath).replaceAll('\\', '/') : undefined;
if (outputRelative && (!outputRelative.startsWith('reports/') || outputRelative.includes('/../') || outputRelative === 'reports/')) {
  throw new Error('--json-output must name a file inside reports/.');
}
const base = resolve(repo, 'examples/facility-arrival');
const publicBase = resolve(repo, 'public/data/facility_arrival');

function readJsonObject(relativePath: string): Record<string, unknown> {
  const value = JSON.parse(readFileSync(resolve(repo, relativePath), 'utf8')) as unknown;
  if (value === null || Array.isArray(value) || typeof value !== 'object') {
    throw new Error(`JSON root must be an object:${relativePath}`);
  }
  return value as Record<string, unknown>;
}

const evolutionContext = {
  policy: readJsonObject('config/release/OFFLINE_SCENARIO_RELEASE.json'),
  genome: readJsonObject('public/data/scenario_core/verified_scenario_genome.json'),
  capability: readJsonObject('config/release/SCENARIO_CAPABILITY_RATCHET.json'),
  debt: readJsonObject('config/release/TECHNICAL_DEBT_RATCHET.json'),
  graph: readJsonObject('config/release/RELEASE_GRAPH.json'),
};
const evolutionPolicy = evolutionContext.policy as { release_graph_binding_mode?: unknown };
const evolutionBlock = renderEvolutionBlock(evolutionContext, {
  graphBindingMode: String(evolutionPolicy.release_graph_binding_mode),
  graphContractSha256: graphContractSha256(evolutionContext.graph),
});

function sortDeep(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortDeep);
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value as Record<string, unknown>)
        .sort()
        .map((key) => [key, sortDeep((value as Record<string, unknown>)[key])]),
    );
  }
  return value;
}

function stableJson(value: unknown): string {
  return `${JSON.stringify(sortDeep(value), null, 2)}\n`;
}

function compareGeneratedFile(path: string, content: string, mismatches: string[]): void {
  try {
    if (readFileSync(path, 'utf8') !== content) mismatches.push(path.replace(`${repo}/`, ''));
  } catch {
    mismatches.push(path.replace(`${repo}/`, ''));
  }
}

function flattenSourceActions(): Array<ExpectedAction & { priority: string }> {
  const scenario = scenariosById['ASK-D-001'];
  if (!scenario) throw new Error('ASK-D-001 is missing');
  return (['critical', 'important', 'optional', 'unsafe'] as const)
    .flatMap((priority) => scenario.expected_actions[priority].map((action) => ({ ...action, priority })))
    .sort((left, right) => left.id.localeCompare(right.id));
}

function hashedRecord<T extends Record<string, unknown>>(record: T): T & { source_record_sha256: string } {
  return { ...record, source_record_sha256: sha256Canonical(record) };
}

function buildSourceTruth() {
  const records = [
    hashedRecord({
      source_id: 'JTS-CPG-INDEX-2026-07-28',
      title: 'Joint Trauma System Clinical Practice Guidelines',
      url: 'https://jts.health.mil/index.cfm/CPGs/cpgs',
      locator: 'Primary goals; Blood; Documentation; Radiology; Tactical Combat Casualty Care Guidelines; Transport',
      relation: 'SCOPE_AND_PROCESS_REFERENCE',
      clinical_rule_entailment: 'NOT_USED',
      supported_scope_claim: 'JTS publishes current casualty-care standards and lists relevant resuscitation, documentation, imaging, TCCC, and transport resources.',
      retrieved_at_utc: '2026-07-29T00:00:00Z',
    }),
    hashedRecord({
      source_id: 'JTS-PI-2026-04-02',
      title: 'Joint Trauma System Performance Improvement',
      url: 'https://jts.health.mil/index.cfm/pi',
      locator: 'Performance Improvement overview',
      relation: 'SCOPE_AND_PROCESS_REFERENCE',
      clinical_rule_entailment: 'NOT_USED',
      supported_scope_claim: 'JTS performance improvement spans the continuum of care and evaluates transitions between phases of care.',
      retrieved_at_utc: '2026-07-29T00:00:00Z',
    }),
    hashedRecord({
      source_id: 'JTS-DCOT-2026-04-03',
      title: 'Defense Committees on Trauma',
      url: 'https://jts.health.mil/index.cfm/committees/dcot',
      locator: 'Mission and component committees',
      relation: 'SCOPE_AND_PROCESS_REFERENCE',
      clinical_rule_entailment: 'NOT_USED',
      supported_scope_claim: 'DoD combat-casualty governance spans tactical, en route, and surgical care through separate expert committees.',
      retrieved_at_utc: '2026-07-29T00:00:00Z',
    }),
    hashedRecord({
      source_id: 'USAF-WIT-CRE-2026',
      title: 'Wing Inspection Team supports readiness during Combat Readiness Exercise 2026',
      url: 'https://www.18af.amc.af.mil/News/Article-Display/Article/4388635/wing-inspection-team-supports-readiness-during-combat-readiness-exercise-2026-a/',
      locator: 'WIT roles in observation, evaluation, trend identification, and corrective-action validation',
      relation: 'SCOPE_AND_PROCESS_REFERENCE',
      clinical_rule_entailment: 'NOT_USED',
      supported_scope_claim: 'Wing Inspection Team members observe operations, evaluate processes, and identify strengths and gaps during readiness exercises.',
      retrieved_at_utc: '2026-07-29T00:00:00Z',
    }),
  ];
  const payload = {
    schema_version: '1.1.0',
    purpose: 'Identity-only scope and process references for post-field-care facility reception and Wing Inspection Team framing.',
    clinical_rule_source: 'ASK-D-001 inherited repository template only',
    records,
  };
  return { ...payload, source_truth_root_sha256: sha256Canonical(payload) };
}

function buildReadme(session: ReturnType<typeof runCanonicalFacilitySession>, aar: ReturnType<typeof buildFacilityAar>): string {
  const transitionRows = session.transitions.map((transition) => (
    `| ${transition.sequence} | ${transition.completed_at_seconds}s | ${transition.kind} | ${transition.label.replaceAll('|', '\\|')} |`
  )).join('\n');
  return `# Facility-arrival canonical interactive scenario\n\n` +
    `[Open the self-contained offline Facility Arrival scenario](playable.html). It runs locally in a modern browser with no server or network request.\n\n` +
    `## Four playable offline role-model teamwork challenges\n\n` +
    `The single offline file includes four selectable, fully playable role-model examples. Each profile keeps the same source-bound clinical template and changes only the operational teamwork route:\n\n` +
    `- **Direct handoff baseline** — complete the normal closed-loop receiving workflow.\n` +
    `- **Communications relay** — establish an intermediate relay and confirm receipt before the final handoff.\n` +
    `- **Resource coordination** — coordinate a constrained resource and confirm ownership before the final handoff.\n` +
    `- **Relay and resource coordination** — establish the relay first, then coordinate the constrained resource, then close the handoff.\n\n` +
    `Open \`playable.html\`, choose a challenge at the top, and use manual actions, **Watch autoplay**, or **Complete canonical replay**. Relay and resource actions carry zero clinical points. They are structural training behaviors, not clinically calibrated timing or treatment authority.\n\n` +
    `This is the current start-to-finish Project Asklepios example for the **post-CUF/TFC receiving phase**. It begins when a field-stabilized casualty arrives at a constrained base clinic and ends with a closed-loop transfer to the next level of care.\n\n` +
    `- Browser route: [\`/examples/facility-arrival\`](/examples/facility-arrival)\n` +
    `- Source template: \`${session.source_binding.source_scenario_id}\`\n` +
    `- Facility profile: \`${session.facility_profile}\`\n` +
    `- Terminal status: \`${session.final_state.terminal_status}\`\n` +
    `- Score: \`${(session.normalized_score_bps / 100).toFixed(2)}%\`\n` +
    `- Session SHA-256: \`${session.certificate.session_sha256}\`\n` +
    `- Content-registry root: \`${session.source_binding.content_registry_merkle_root}\`\n\n` +
    `${evolutionBlock}\n\n` +
    `## Complete simulated learner interaction\n\n` +
    `| Seq | Time | Type | Interaction |\n|---:|---:|---|---|\n${transitionRows}\n\n` +
    `## Alternate branches\n\nThe interactive page can also produce an explicit source-bound timeout, unsafe discharge failure, and unsafe tourniquet-action failure. Each branch is event-sourced and independently replayable.\n\n` +
    `## WIT and learner separation\n\nWIT observations remain process-only and carry no clinical directive or clinical points. Hidden source findings remain unavailable to the learner until the authenticated diagnostics-ready event occurs.\n\n` +
    `## Evidence and calibration boundary\n\nClinical actions and points come only from the inherited ASK-D-001 repository template. The JTS and USAF records in \`source-truth.json\` frame continuum-of-care and inspection-process scope; they are not used as a hidden clinical-rule generator. Diagnostic timing and the pass threshold are explicitly marked \`NOT_CALIBRATED\` exercise-design values.\n\n` +
    `## Rebuild and verify\n\n\`\`\`bash\nnpm run generate:facility-arrival\nnpm run verify:facility-arrival\npython3 scripts/check_facility_arrival_example.py --repo .\nnode scripts/check_facility_arrival_example.mjs --repo .\n\`\`\`\n\n` +
    `## Open validity obligations\n\n${aar.validity_ledger.open.map((item) => `- ${item}`).join('\n')}\n`;
}

const session = runCanonicalFacilitySession(facilityArrivalContext);
const errors = validateFacilitySession(session, facilityArrivalContext);
if (errors.length > 0) throw new Error(`canonical facility session invalid: ${errors.join(',')}`);
const aar = buildFacilityAar(session, facilityArrivalContext);
const ledger = buildFacilityClaimLedger(facilityArrivalContext);
const scenario = facilityArrivalContext.scenario;
const patient = scenario.patients[0];
if (!patient) throw new Error('ASK-D-001 has no patient');
const snapshotBase = {
  schema_version: '1.0.0',
  ...session.source_binding,
  patient: {
    initial_presentation: patient.initial_presentation,
    initial_vitals: patient.initial_vitals,
    hidden_findings: patient.hidden_findings,
  },
  source_actions: flattenSourceActions().map((action) => ({
    id: action.id,
    label: action.label,
    priority: action.priority,
    points: action.points,
  })),
  end_conditions: scenario.end_conditions,
};
const sourceSnapshot = { ...snapshotBase, snapshot_sha256: sha256Canonical(snapshotBase) };
const sourceTruth = buildSourceTruth();
const readme = buildReadme(session, aar);

const generatedFiles: Record<string, string> = {
  'interaction.json': stableJson(session),
  'aar.json': stableJson(aar),
  'claim-ledger.json': stableJson(ledger),
  'source-snapshot.json': stableJson(sourceSnapshot),
  'source-truth.json': stableJson(sourceTruth),
  'README.md': `${readme.trimEnd()}\n`,
};
const fileHashes = Object.fromEntries(Object.entries(generatedFiles).map(([name, content]) => [name, sha256Text(content)]));
const manifestBase = {
  schema_version: '1.1.0',
  example_id: session.example_id,
  title: session.title,
  browser_route: '/examples/facility-arrival',
  care_continuum_phase: session.care_continuum_phase,
  authority: session.authority,
  source_binding: session.source_binding,
  certificate: session.certificate,
  counts: {
    transitions: session.transitions.length,
    learner_actions: session.transitions.filter((item) => item.kind === 'learner_action').length,
    system_events: session.transitions.filter((item) => item.kind === 'system_event').length,
    wit_observations: session.transitions.length,
    claim_records: ledger.records.length,
    demonstrated_gates: aar.validity_ledger.demonstrated.length,
    open_gates: aar.validity_ledger.open.length,
  },
  files: {
    interaction: 'interaction.json',
    aar: 'aar.json',
    claim_ledger: 'claim-ledger.json',
    source_snapshot: 'source-snapshot.json',
    source_truth: 'source-truth.json',
    documentation: 'README.md',
  },
  hashes: {
    interaction_sha256: fileHashes['interaction.json'],
    aar_sha256: fileHashes['aar.json'],
    claim_ledger_sha256: fileHashes['claim-ledger.json'],
    source_snapshot_sha256: fileHashes['source-snapshot.json'],
    source_truth_sha256: fileHashes['source-truth.json'],
    documentation_sha256: fileHashes['README.md'],
  },
  generated_from: {
    spec_path: 'config/facility-arrival/ASK-D-001.json',
    spec_sha256: session.spec_sha256,
    source_path: 'src/content/scenarios.ts',
    source_snapshot_sha256: sourceSnapshot.snapshot_sha256,
    content_registry_root: session.source_binding.content_registry_merkle_root,
  },
};
const manifest = { ...manifestBase, manifest_sha256: sha256Canonical(manifestBase) };
generatedFiles['manifest.json'] = stableJson(manifest);

const mismatches: string[] = [];
for (const [name, content] of Object.entries(generatedFiles)) {
  compareGeneratedFile(resolve(base, name), content, mismatches);
}
compareGeneratedFile(resolve(publicBase, 'reference-session.json'), stableJson(session), mismatches);
compareGeneratedFile(resolve(publicBase, 'reference-aar.json'), stableJson(aar), mismatches);
compareGeneratedFile(resolve(publicBase, 'reference-manifest.json'), stableJson(manifest), mismatches);

const report = {
  schema_version: '1.1.0',
  classification: mismatches.length === 0 ? 'PASS' : 'FAIL',
  status: mismatches.length === 0 ? 'PASS' : 'FAIL',
  mode: 'check',
  generator_role: 'INDEPENDENT_TYPESCRIPT_CHECKER',
  canonical_writer: 'PYTHON_BUILD_FACILITY_ARRIVAL_EXAMPLE',
  files_compared: Object.keys(generatedFiles).length + 3,
  example_id: session.example_id,
  terminal_status: session.final_state.terminal_status,
  normalized_score_bps: session.normalized_score_bps,
  transitions: session.transitions.length,
  session_sha256: session.certificate.session_sha256,
  manifest_sha256: manifest.manifest_sha256,
  mismatches,
};
if (outputPath) {
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
}
console.log(JSON.stringify(report, null, 2));
if (mismatches.length > 0) process.exitCode = 1;
