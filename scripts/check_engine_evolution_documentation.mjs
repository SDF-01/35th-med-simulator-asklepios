#!/usr/bin/env node
/** Independent Node verification of RC3.8A.1 engine-evolution documentation. */
import crypto from 'node:crypto';
import fs from 'node:fs';
import process from 'node:process';
import { emitCheckerResult, parseCheckerArgs, resolveRepoPath } from './node_checker_cli.mjs';
import { EVOLUTION_START, EVOLUTION_END, graphContractSha256, renderEvolutionBlock, renderRootSection as renderSharedRootSection, renderStandaloneSection as renderSharedStandaloneSection } from './engine_evolution_documentation_common.mjs';

const DOCS = Object.freeze({
  root: 'README.md',
  facility: 'examples/facility-arrival/README.md',
  verified: 'examples/verified-scenario/README.md',
  standalone: 'docs/FACILITY_ARRIVAL_STANDALONE.md',
});
const EXPECTED = Object.freeze({
  "release": "ASK-OFFLINE-RC3.8A.1",
  "display": "RC3.8A.1",
  "evolution": "SCENARIO_SCIENCE_BEHAVIORAL_DIVERSITY_STAKEHOLDER_SCORECARD_TREATMENT_ADMISSION_PLAIN_LANGUAGE_DUAL_RATCHETS_V8",
  "graph": "asklepios-rc3.8a.1-scenario-science-stakeholder-graph",
  "stages": 122,
  "targets": 26,
  "graphBindingMode": "ACYCLIC_SEMANTIC_PROJECTION_V1",
  "capability": "asklepios-scenario-capability-ratchet-v1",
  "capabilityEpoch": 5,
  "capabilityAnchor": "870a94620630dc6fc4a41f3d13120ea45527966676d72e69bd5b460bee45218e",
  "debt": "asklepios-technical-debt-ratchet-v1",
  "debtEpoch": 8,
  "debtAnchor": "84d04484d51e79944b3079889d0eed50841f9588422e0f9928c3840822b5fb91"
});
const POLICY_REQUIRED = Object.freeze({
  "facility": [
    "## Engine evolution binding",
    "- Canonical-writer rule:",
    "- Receipt rule:",
    "- Release-identity rule:",
    "- Route topology:",
    "- Technical-debt ratchet:",
    "- Behavioral quality-diversity:",
    "does not establish clinical certification",
    "direct patient care",
    "- Behavioral policy diversity:",
    "- Operational scenario pack:",
    "- Four playable offline role-model teamwork challenges:",
    "- Source-conformance scorecard:",
    "- Treatment-admission pipeline:",
    "Plain-language release translation"
  ],
  "root": [
    "Canonical repository: https://github.com/SDF-01/ProjectAsklepios",
    "## Static exercise catalog (100 TOON-authored exercises)",
    "- Checker boundary:",
    "- Artifact authority:",
    "- Evidence freshness:",
    "- Release-identity DAG:",
    "- Route topology:",
    "- Technical-debt ratchet:",
    "- Diagnostic model:",
    "- Behavioral quality-diversity:",
    "Clinical authority remains NOT_GRANTED.",
    "Operational timing remains NOT_CALIBRATED.",
    "Direct patient care and clinical decision support remain prohibited.",
    "- Behavioral policy diversity:",
    "- Operational scenario pack:",
    "- Four playable offline role-model teamwork challenges:",
    "- Source-conformance scorecard:",
    "- Treatment-admission pipeline:",
    "- Plain-language release translation:"
  ],
  "standalone": [
    "## Engine evolution and reproducibility boundary",
    "Canonical writer",
    "Independent verifier",
    "Evidence consumers authenticate",
    "acyclic semantic graph projection",
    "monotonic across ratchet epochs",
    "Behavioral quality-diversity",
    "connect-src 'none'",
    "not an empirically calibrated real-clinical workflow clock",
    "does not establish clinical certification",
    "direct patient care",
    "Behavioral policy diversity",
    "Operational scenario pack",
    "Four playable offline role-model teamwork challenges",
    "Source-conformance scorecard",
    "Treatment-admission pipeline",
    "Plain-language release translation"
  ],
  "verified": [
    "## Engine evolution binding",
    "- Canonical-writer rule:",
    "- Receipt rule:",
    "- Release-identity rule:",
    "- Route topology:",
    "- Technical-debt ratchet:",
    "- Behavioral quality-diversity:",
    "does not establish clinical certification",
    "direct patient care",
    "- Behavioral policy diversity:",
    "- Operational scenario pack:",
    "- Four playable offline role-model teamwork challenges:",
    "- Source-conformance scorecard:",
    "- Treatment-admission pipeline:",
    "Plain-language release translation"
  ]
});
const POLICY_FORBIDDEN = Object.freeze({
  root: Object.freeze([
    'deployment is currently healthy',
    'production deployment is healthy',
    'vercel preview is healthy',
    'the live deployment is healthy',
    'generated scenario catalog (107 toon-authored exercises)',
  ]),
});

function normalize(value, location = '$') {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new Error(`non-safe integer:${location}`);
    return value;
  }
  if (Array.isArray(value)) return value.map((item, index) => normalize(item, `${location}[${index}]`));
  if (typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, normalize(value[key], `${location}.${key}`)]));
  }
  throw new Error(`unsupported canonical type:${location}`);
}
function same(left, right) { return JSON.stringify(normalize(left)) === JSON.stringify(normalize(right)); }
function canonicalSha(value) { return crypto.createHash('sha256').update(Buffer.from(JSON.stringify(normalize(value)), 'utf8')).digest('hex'); }
function load(repo, relative) {
  const value = JSON.parse(fs.readFileSync(resolveRepoPath(repo, relative, { allowMissing: false }), 'utf8'));
  if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error(`JSON root malformed:${relative}`);
  return value;
}
function digest(file) { return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'); }
function readCanonicalDocument(repo, relative, errors) {
  const file = resolveRepoPath(repo, relative, { allowMissing: false });
  const raw = fs.readFileSync(file);
  const text = raw.toString('utf8');
  if (!Buffer.from(text, 'utf8').equals(raw)) errors.push(`engine-evolution document is not UTF-8:${relative}`);
  if (raw.includes(13)) errors.push(`engine-evolution document contains carriage return:${relative}`);
  if (raw.length === 0 || raw.at(-1) !== 10) errors.push(`engine-evolution document missing terminal LF:${relative}`);
  if (raw.length >= 2 && raw.at(-1) === 10 && raw.at(-2) === 10) errors.push(`engine-evolution document has blank line at EOF:${relative}`);
  text.split('\n').forEach((line, index) => {
    if (/[ \t]$/.test(line)) errors.push(`engine-evolution document has trailing whitespace:${relative}:${index + 1}`);
  });
  return text;
}
function count(text, token) { return text.split(token).length - 1; }
function markedSection(text, start, end, label, errors) {
  if (count(text, start) !== 1 || count(text, end) !== 1) {
    errors.push(`documentation marker inventory differs:${label}`);
    return null;
  }
  const first = text.indexOf(start);
  const last = text.indexOf(end, first);
  if (last < first) {
    errors.push(`documentation marker order differs:${label}`);
    return null;
  }
  return text.slice(first, last + end.length);
}
function asPolicyLiteralObject(value) {
  return Object.fromEntries(Object.entries(value).map(([key, items]) => [key, [...items]]));
}




function documentationRenderOptions(ctx) {
  return {
    graphBindingMode: EXPECTED.graphBindingMode,
    graphContractSha256: graphContractSha256(ctx.graph),
  };
}

function canonicalEvolutionBlock(ctx) {
  return renderEvolutionBlock(ctx, documentationRenderOptions(ctx));
}



function verify(repo) {
  const errors = [];
  const policy = load(repo, 'config/release/OFFLINE_SCENARIO_RELEASE.json');
  const descriptor = load(repo, 'public/data/scenario_core/offline_scenario_release.json');
  const genome = load(repo, 'public/data/scenario_core/verified_scenario_genome.json');
  const capability = load(repo, 'config/release/SCENARIO_CAPABILITY_RATCHET.json');
  const debt = load(repo, 'config/release/TECHNICAL_DEBT_RATCHET.json');
  const graph = load(repo, 'config/release/RELEASE_GRAPH.json');
  const ctx = { policy, descriptor, genome, capability, debt, graph };

  if (policy.release_id !== EXPECTED.release || policy.display_version !== EXPECTED.display || policy.engine_evolution !== EXPECTED.evolution) errors.push('engine-evolution policy identity differs');
  if (policy.expected_graph_id !== EXPECTED.graph || policy.expected_graph_stage_count !== EXPECTED.stages || policy.expected_graph_target_count !== EXPECTED.targets) errors.push('engine-evolution policy graph floor differs');
  if (policy.release_graph_binding_mode !== EXPECTED.graphBindingMode) errors.push('engine-evolution graph binding mode differs');
  if (policy.expected_capability_ratchet_id !== EXPECTED.capability || policy.expected_capability_ratchet_epoch !== EXPECTED.capabilityEpoch) errors.push('engine-evolution policy capability-ratchet floor differs');
  if (policy.expected_technical_debt_ratchet_id !== EXPECTED.debt || policy.expected_technical_debt_ratchet_epoch !== EXPECTED.debtEpoch) errors.push('engine-evolution policy technical-debt-ratchet floor differs');
  if (!same(policy.documentation_contract?.required_literals, asPolicyLiteralObject(POLICY_REQUIRED))) errors.push('engine-evolution documentation required-literal contract differs');
  if (!same(policy.documentation_contract?.forbidden_casefold_phrases, asPolicyLiteralObject(POLICY_FORBIDDEN))) errors.push('engine-evolution documentation forbidden-phrase contract differs');
  if (graph.graph_id !== EXPECTED.graph || graph.stages?.length !== EXPECTED.stages || Object.keys(graph.targets ?? {}).length !== EXPECTED.targets) errors.push('engine-evolution graph identity differs');
  if (capability.ratchet_id !== EXPECTED.capability || capability.ratchet_epoch !== EXPECTED.capabilityEpoch || capability.ratchet_anchor_sha256 !== EXPECTED.capabilityAnchor) errors.push('engine-evolution capability ratchet differs');
  if (debt.ratchet_id !== EXPECTED.debt || debt.ratchet_epoch !== EXPECTED.debtEpoch || debt.ratchet_anchor_sha256 !== EXPECTED.debtAnchor) errors.push('engine-evolution technical-debt ratchet differs');

  const documents = {};
  for (const [name, relative] of Object.entries(DOCS)) {
    documents[name] = readCanonicalDocument(repo, relative, errors);
  }
  const contract = policy.documentation_contract;
  const sections = {
    root: markedSection(documents.root, contract.root_start_marker, contract.root_end_marker, 'root', errors),
    facility: markedSection(documents.facility, EVOLUTION_START, EVOLUTION_END, 'facility', errors),
    verified: markedSection(documents.verified, EVOLUTION_START, EVOLUTION_END, 'verified', errors),
    standalone: markedSection(documents.standalone, contract.standalone_start_marker, contract.standalone_end_marker, 'standalone', errors),
  };
  markedSection(documents.root, '<!-- asklepios-repository-operation:start -->', '<!-- asklepios-repository-operation:end -->', 'root-repository', errors);
  if (sections.root !== null && sections.root !== renderSharedRootSection(ctx, documentationRenderOptions(ctx))) errors.push('canonical engine-evolution document differs:README.md');
  if (sections.standalone !== null && sections.standalone !== renderSharedStandaloneSection(ctx, documentationRenderOptions(ctx))) errors.push('canonical engine-evolution document differs:docs/FACILITY_ARRIVAL_STANDALONE.md');
  const expectedEvolution = canonicalEvolutionBlock(ctx);
  if (sections.facility !== null && sections.facility !== expectedEvolution) errors.push('canonical engine-evolution block differs:facility');
  if (sections.verified !== null && sections.verified !== expectedEvolution) errors.push('canonical engine-evolution block differs:verified');

  const tokens = [
    EXPECTED.release, EXPECTED.display, EXPECTED.evolution,
    genome.genome_id, genome.genome_sha256,
    capability.ratchet_id, String(capability.ratchet_epoch), capability.ratchet_anchor_sha256,
    debt.ratchet_id, String(debt.ratchet_epoch), debt.ratchet_anchor_sha256,
    graph.graph_id, String(graph.stages.length), String(Object.keys(graph.targets).length),
    EXPECTED.graphBindingMode, graphContractSha256(graph),
  ];
  for (const [name, content] of Object.entries(sections)) {
    if (content === null) continue;
    for (const token of tokens) if (!content.includes(token)) errors.push(`engine-evolution identity missing:${name}:${token}`);
    if (/RC3\.7A\.[012](?!\d)/.test(content)) errors.push(`stale active engine-evolution version:${name}`);
  }
  for (const [name, content] of Object.entries(documents)) {
    const folded = content.toLocaleLowerCase('en-US');
    const fullFolded = documents[name].toLocaleLowerCase('en-US');
    for (const literal of POLICY_REQUIRED[name] ?? []) if (!fullFolded.includes(literal.toLocaleLowerCase('en-US'))) errors.push(`offline documentation required literal missing:${name}:${literal}`);
  }

  const repositoryLines = documents.root.split(/\r?\n/).map((line) => line.trim()).filter((line) => line.toLowerCase().startsWith('canonical repository:'));
  if (!same(repositoryLines, [`Canonical repository: ${policy.canonical_repository_url}`])) errors.push('canonical repository declaration differs');
  for (const [surface, phrases] of Object.entries(POLICY_FORBIDDEN)) {
    const folded = documents[surface].toLocaleLowerCase('en-US');
    for (const phrase of phrases) if (folded.includes(phrase)) errors.push(`offline documentation forbidden claim:${surface}:${phrase}`);
  }

  const inventory = new Map((descriptor.artifacts ?? []).map((item) => [item.path, item]));
  for (const relative of Object.values(DOCS)) {
    const record = inventory.get(relative);
    if (!record) {
      errors.push(`engine-evolution document absent from offline artifact inventory:${relative}`);
      continue;
    }
    const file = resolveRepoPath(repo, relative, { allowMissing: false });
    const info = fs.lstatSync(file);
    if (!info.isFile() || info.isSymbolicLink()) errors.push(`engine-evolution document missing or unsafe:${relative}`);
    if (record.bytes !== info.size) errors.push(`engine-evolution document byte count differs:${relative}`);
    if (record.sha256 !== digest(file)) errors.push(`engine-evolution document hash differs:${relative}`);
  }

  const classification = errors.length ? 'FAIL' : 'PASS';
  return {
    schema_version: '1.1.0',
    classification,
    status: classification,
    checker_profile: 'INDEPENDENT_NODE_ENGINE_EVOLUTION_DOCUMENTATION_V5',
    documents: Object.keys(documents).length,
    release_id: policy.release_id,
    genome_id: genome.genome_id,
    capability_ratchet_epoch: capability.ratchet_epoch,
    technical_debt_ratchet_epoch: debt.ratchet_epoch,
    graph_id: graph.graph_id,
    errors: [...new Set(errors)].sort(),
  };
}

let parsed;
let result;
try {
  parsed = parseCheckerArgs(process.argv.slice(2), { allowPositionalRepo: true, outputFlags: ['--report', '--json-output'] });
  result = verify(parsed.repo);
} catch (error) {
  result = {
    schema_version: '1.1.0',
    classification: 'FAIL',
    status: 'FAIL',
    checker_profile: 'INDEPENDENT_NODE_ENGINE_EVOLUTION_DOCUMENTATION_V5',
    errors: [`${error?.name ?? 'Error'}:${error?.message ?? String(error)}`],
  };
}
process.exitCode = emitCheckerResult(result, { repo: parsed?.repo ?? '.', report: parsed?.report ?? null });
