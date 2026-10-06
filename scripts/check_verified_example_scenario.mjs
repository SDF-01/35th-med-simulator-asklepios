#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { parseCheckerArgs, resolveRepoPath, emitCheckerResult, normalizedFailure } from './node_checker_cli.mjs';

let args;
try {
  args = parseCheckerArgs(process.argv.slice(2), { outputFlags: ['--report', '--json-output'], allowPositionalRepo: true });
} catch (error) {
  process.exit(emitCheckerResult(normalizedFailure(error, 'INDEPENDENT_NODE_VERIFIED_EXAMPLE_V2')));
}
const repo = args.repo;
const manifestPath = resolveRepoPath(repo, 'examples/verified-scenario/manifest.json', { allowMissing: false });
const documentPath = resolveRepoPath(repo, 'examples/verified-scenario/README.md', { allowMissing: false });
const rootReadmePath = resolveRepoPath(repo, 'README.md', { allowMissing: false });
const offlinePolicyPath = resolveRepoPath(repo, 'config/release/OFFLINE_SCENARIO_RELEASE.json', { allowMissing: false });
const genomePath = resolveRepoPath(repo, 'public/data/scenario_core/verified_scenario_genome.json', { allowMissing: false });
const capabilityRatchetPath = resolveRepoPath(repo, 'config/release/SCENARIO_CAPABILITY_RATCHET.json', { allowMissing: false });
const debtRatchetPath = resolveRepoPath(repo, 'config/release/TECHNICAL_DEBT_RATCHET.json', { allowMissing: false });
const releaseGraphPath = resolveRepoPath(repo, 'config/release/RELEASE_GRAPH.json', { allowMissing: false });
const EXPECTED_OFFLINE_RELEASE = 'ASK-OFFLINE-RC3.8A.1';
const EXPECTED_GRAPH_ID = 'asklepios-rc3.8a.1-scenario-science-stakeholder-graph';
const MINIMUM_GRAPH_STAGE_COUNT = 118;
const MINIMUM_GRAPH_TARGET_COUNT = 26;
const EXPECTED_DEBT_RATCHET_ID = 'asklepios-technical-debt-ratchet-v1';
const EXPECTED_DEBT_RATCHET_EPOCH = 8;
const EXPECTED_DEBT_RATCHET_ANCHOR = '84d04484d51e79944b3079889d0eed50841f9588422e0f9928c3840822b5fb91';
const errors = [];
let checks = 0;

function loadJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function normalize(value) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new Error(`non-safe or non-integer number:${value}`);
    return value;
  }
  if (Array.isArray(value)) return value.map(normalize);
  if (typeof value === 'object') {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = normalize(value[key]);
    return out;
  }
  throw new Error(`unsupported canonical type:${typeof value}`);
}

function canonicalBytes(value) {
  return Buffer.from(JSON.stringify(normalize(value)), 'utf8');
}

function sha256Bytes(bytes) {
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function sha256Json(value) {
  return sha256Bytes(canonicalBytes(value));
}

function sha256File(file) {
  return sha256Bytes(fs.readFileSync(file));
}

function stablePublicValue(value) {
  if (typeof value === 'number' && !Number.isInteger(value)) return String(value);
  if (Array.isArray(value)) return value.map(stablePublicValue);
  if (value && typeof value === 'object') {
    const out = {};
    for (const [key, child] of Object.entries(value)) out[key] = stablePublicValue(child);
    return out;
  }
  return value;
}

function fail(message) {
  errors.push(message);
}

function checkTextHygiene(file, label) {
  if (!fs.existsSync(file)) {
    fail(`missing:${label}`);
    return;
  }
  const bytes = fs.readFileSync(file);
  if (bytes.includes(13)) fail(`carriage return forbidden:${label}`);
  const text = bytes.toString('utf8');
  text.split(/\n/).forEach((line, index) => {
    if (/[ \t]$/.test(line)) fail(`trailing whitespace:${label}:${index + 1}`);
  });
  if (text.length > 0 && !text.endsWith('\n')) fail(`final newline missing:${label}`);
  checks += 1;
}

try {
  checkTextHygiene(documentPath, 'examples/verified-scenario/README.md');
  checkTextHygiene(rootReadmePath, 'README.md');
  if (!fs.existsSync(manifestPath)) throw new Error('example manifest missing');
  const manifest = loadJson(manifestPath);
  const hashCandidate = structuredClone(manifest);
  const observedHash = hashCandidate.example_manifest_sha256;
  delete hashCandidate.example_manifest_sha256;
  if (observedHash !== sha256Json(hashCandidate)) fail('manifest hash mismatch');
  checks += 1;

  const source = manifest.source_bindings ?? {};
  for (const [field, label] of [
    ['scenario_package_path', 'scenario package'],
    ['content_registry_path', 'content registry'],
  ]) {
    const rel = source[field];
    if (typeof rel !== 'string' || rel.startsWith('/') || rel.split('/').includes('..')) fail(`unsafe ${label} path`);
  }
  const scenarioPath = path.join(repo, source.scenario_package_path ?? '');
  const registryPath = path.join(repo, source.content_registry_path ?? '');
  if (!fs.existsSync(scenarioPath)) throw new Error('source scenario package missing');
  if (!fs.existsSync(registryPath)) throw new Error('source registry missing');
  const scenarioPackage = loadJson(scenarioPath);
  const registry = loadJson(registryPath);
  if (source.scenario_package_file_sha256 !== sha256File(scenarioPath)) fail('scenario file hash mismatch');
  if (source.content_registry_file_sha256 !== sha256File(registryPath)) fail('registry file hash mismatch');
  if (source.content_registry_merkle_root !== registry.roots?.registry_merkle_root) fail('registry root mismatch');
  if (source.scenario_package_sha256 !== scenarioPackage.certificate?.package_sha256) fail('certificate package hash mismatch');
  checks += 4;

  const requiredAuthority = {
    clinical_authority: 'NOT_GRANTED',
    deployment_scope: 'research_sandbox_only',
    source_template_status: 'repository_template_not_clinically_certified',
    clinical_rule_source: 'inherited_template',
    evidence_authority: 'supporting_only',
    evidence_effect_scope: 'citation_support_only',
    scoring_behavior: 'inherited_unchanged',
  };
  for (const [field, expected] of Object.entries(requiredAuthority)) {
    if (manifest.authority?.[field] !== expected) fail(`manifest authority mismatch:${field}`);
    if (scenarioPackage.authority?.[field] !== expected) fail(`source authority mismatch:${field}`);
  }
  checks += 2;

  const assets = new Map((registry.assets ?? []).map((item) => [item.asset_id, item]));
  const attestations = new Map((registry.evidence_attestations ?? []).map((item) => [item.evidence_asset_id.replace(/^evidence:/, ''), item]));
  const templateId = `template:${scenarioPackage.build?.source_scenario_id}`;
  const template = assets.get(templateId);
  if (!template) fail('template asset missing');
  else {
    if (manifest.protected_template?.asset_id !== templateId) fail('template ID mismatch');
    if (manifest.protected_template?.record_sha256 !== template.record_sha256) fail('template hash mismatch');
    if (manifest.protected_template?.clinical_certification !== 'NOT_GRANTED') fail('template authority escalation');
  }
  checks += 3;

  const sourceEvidence = scenarioPackage.evidence ?? [];
  const citations = manifest.citations ?? [];
  if (citations.length !== sourceEvidence.length) fail('citation count mismatch');
  const seen = new Set();
  sourceEvidence.forEach((evidence, index) => {
    const citation = citations[index] ?? {};
    const evidenceId = evidence.evidence_id;
    if (seen.has(evidenceId)) fail(`duplicate citation:${evidenceId}`);
    seen.add(evidenceId);
    if (citation.evidence_id !== evidenceId || citation.order !== index + 1) fail(`citation order/ID mismatch:${index}`);
    for (const field of ['title', 'journal', 'doi', 'locator', 'chunk_sha256', 'source_file_sha256']) {
      if (citation[field] !== evidence[field]) fail(`citation mismatch:${evidenceId}:${field}`);
    }
    const evidenceAsset = assets.get(`evidence:${evidenceId}`);
    const attestation = attestations.get(evidenceId);
    if (!evidenceAsset || !attestation) {
      fail(`registry evidence chain missing:${evidenceId}`);
      return;
    }
    const sourceAsset = assets.get(evidenceAsset.metadata?.source_asset_id);
    if (!sourceAsset) {
      fail(`source asset missing:${evidenceId}`);
      return;
    }
    for (const field of ['doi', 'locator', 'chunk_sha256', 'source_file_sha256']) {
      if (evidenceAsset.metadata?.[field] !== evidence[field]) fail(`evidence asset mismatch:${evidenceId}:${field}`);
    }
    for (const field of ['title', 'journal', 'doi', 'source_file_sha256']) {
      if (sourceAsset.metadata?.[field] !== evidence[field]) fail(`source asset mismatch:${evidenceId}:${field}`);
    }
    const exact = {
      relation: 'REFERENCE_ONLY',
      identity_verification: 'PASS',
      entailment_status: 'NOT_ADJUDICATED',
      contradiction_status: 'NOT_SEARCHED',
      human_review_status: 'NOT_REVIEWED',
      clinical_authority: 'NOT_GRANTED',
      authority_tier: 3,
    };
    for (const [field, expected] of Object.entries(exact)) {
      if (attestation[field] !== expected || citation[field] !== expected) fail(`attestation mismatch:${evidenceId}:${field}`);
    }
    if (JSON.stringify(attestation.independent_verifiers) !== '[]') fail(`unexpected independent verifier:${evidenceId}`);
    if (citation.attestation_sha256 !== attestation.attestation_sha256) fail(`attestation hash mismatch:${evidenceId}`);
    if (citation.evidence_asset_record_sha256 !== evidenceAsset.record_sha256) fail(`evidence record hash mismatch:${evidenceId}`);
    if (citation.source_asset_record_sha256 !== sourceAsset.record_sha256) fail(`source record hash mismatch:${evidenceId}`);
    checks += 24;
  });

  const openIds = new Set((manifest.validity_ledger ?? []).filter((x) => x.status === 'OPEN').map((x) => x.gate_id));
  for (const gate of [
    'clinical_template_certification',
    'claim_level_evidence_entailment',
    'contradiction_search',
    'real_world_operational_calibration',
    'human_policy_calibration',
    'executable_to_formal_refinement',
    'independent_proof_kernel',
    'multi_template_clinical_breadth',
    'training_effectiveness_validation',
  ]) {
    if (!openIds.has(gate)) fail(`required open gate missing:${gate}`);
  }
  checks += 9;

  const policy = loadJson(offlinePolicyPath);
  const genome = loadJson(genomePath);
  const capability = loadJson(capabilityRatchetPath);
  const debt = loadJson(debtRatchetPath);
  const graph = loadJson(releaseGraphPath);
  if (policy.release_id !== EXPECTED_OFFLINE_RELEASE || policy.display_version !== 'RC3.8A.1') fail('offline engine-evolution policy identity differs');
  if (policy.engine_evolution !== 'SCENARIO_SCIENCE_BEHAVIORAL_DIVERSITY_STAKEHOLDER_SCORECARD_TREATMENT_ADMISSION_PLAIN_LANGUAGE_DUAL_RATCHETS_V8') fail('offline engine-evolution profile differs');
  if (graph.graph_id !== EXPECTED_GRAPH_ID) fail('engine-evolution release graph identity differs');
  const expectedStageCount = policy.expected_graph_stage_count;
  const expectedTargetCount = policy.expected_graph_target_count;
  const observedStageCount = (graph.stages ?? []).length;
  const observedTargetCount = Object.keys(graph.targets ?? {}).length;
  if (!Number.isSafeInteger(expectedStageCount) || expectedStageCount < MINIMUM_GRAPH_STAGE_COUNT) fail('engine-evolution release graph stage floor regressed');
  if (observedStageCount !== expectedStageCount) fail('engine-evolution release graph stage count differs');
  if (!Number.isSafeInteger(expectedTargetCount) || expectedTargetCount < MINIMUM_GRAPH_TARGET_COUNT) fail('engine-evolution release graph target floor regressed');
  if (observedTargetCount !== expectedTargetCount) fail('engine-evolution release graph target count differs');
  if (capability.ratchet_id !== 'asklepios-scenario-capability-ratchet-v1' || capability.ratchet_epoch !== 5) fail('scenario capability ratchet identity differs');
  if (capability.authority_boundary?.quality_vector_use !== 'SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING') fail('scenario capability quality-vector boundary differs');
  if (debt.ratchet_id !== EXPECTED_DEBT_RATCHET_ID || debt.ratchet_epoch !== EXPECTED_DEBT_RATCHET_EPOCH || debt.ratchet_anchor_sha256 !== EXPECTED_DEBT_RATCHET_ANCHOR) fail('technical-debt ratchet identity differs');
  const identityCandidate = structuredClone(genome);
  delete identityCandidate.genome_id;
  delete identityCandidate.genome_sha256;
  const expectedIdentityDigest = sha256Json(identityCandidate);
  if (genome.genome_id !== `ASK-GENOME-${expectedIdentityDigest.slice(0, 16).toUpperCase()}`) fail('scenario genome identity mismatch');

  const genomeCandidate = structuredClone(genome);
  const observedGenomeSha = genomeCandidate.genome_sha256;
  delete genomeCandidate.genome_sha256;
  const expectedGenomeSha = sha256Json(genomeCandidate);
  if (observedGenomeSha !== expectedGenomeSha) fail('scenario genome hash mismatch');
  if (genome.behavior_descriptor?.cycle_free !== true) fail('scenario genome route is not cycle-free');
  if (![0, undefined].includes(genome.behavior_descriptor?.reachable_nonterminal_dead_ends)) fail('scenario genome contains reachable nonterminal dead ends');
  checks += 8;

  const doc = fs.readFileSync(documentPath, 'utf8');
  const rootReadme = fs.readFileSync(rootReadmePath, 'utf8');
  if (!doc.includes(`\`${observedHash}\``)) fail('documentation manifest hash missing');
  if (!doc.includes('Clinical authority is NOT GRANTED')) fail('documentation authority warning missing');
  for (const fragment of ['## Engine evolution binding', 'Behavioral quality-diversity', EXPECTED_OFFLINE_RELEASE, genome.genome_id, EXPECTED_GRAPH_ID, 'NOT_CALIBRATED', 'PROHIBITED']) {
    if (!doc.includes(fragment)) fail(`documentation engine-evolution fragment missing:${fragment}`);
  }
  if (!rootReadme.includes('[Open the canonical verified example](examples/verified-scenario/README.md)')) fail('root README example link missing');
  if (!rootReadme.includes('Clinical authority remains NOT_GRANTED')) fail('root README authority warning missing');
  if (!rootReadme.includes(EXPECTED_OFFLINE_RELEASE) || !rootReadme.includes(EXPECTED_GRAPH_ID)) fail('root README engine-evolution binding missing');
  if (rootReadme.includes('Psychometric validity:   ESTABLISHED')) fail('unsupported psychometric validity claim');
  checks += 12;
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
}

const result = {
  schema_version: '1.0.0',
  status: errors.length === 0 ? 'PASS' : 'FAIL',
  checks,
  errors: [...new Set(errors)].sort(),
};
result.classification = result.status;
process.exit(emitCheckerResult(result, { repo, report: args.report }));
