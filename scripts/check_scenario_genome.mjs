#!/usr/bin/env node
/** Independently reconstruct and verify the Asklepios Scenario Genome v1. */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { parseCheckerArgs, emitCheckerResult, normalizedFailure } from './node_checker_cli.mjs';

const COMPILED_AUTHORITY_BOUNDARY = Object.freeze({
  clinical_authority: 'NOT_GRANTED',
  deployment_scope: 'research_sandbox_only',
  evidence_authority: 'supporting_only',
  human_team_behavior: 'STRUCTURAL_ONLY_NOT_CALIBRATED',
  operational_calibration: 'NOT_CALIBRATED',
  patient_care_use: 'PROHIBITED',
  patient_dynamics: 'SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY',
  scoring_behavior: 'inherited_unchanged',
});
const COMPILED_POLICY_ID = 'asklepios-scenario-genome-policy-v1';
const COMPILED_GENOME_SCHEMA = '1.0.0';
const COMPILED_DESCRIPTOR_PROFILE = 'INTERPRETABLE_STRUCTURAL_BEHAVIOR_DESCRIPTOR_V1';
const COMPILED_ROUTE_TOPOLOGY_PROFILE = 'REACHABLE_TERMINATING_DAG_V1';
const COMPILED_REQUIRED_DIMENSIONS = new Set([
  'atom_count',
  'branching_nodes',
  'cycle_free',
  'evidence_references',
  'expected_action_counts',
  'field_origin_records',
  'maximum_out_degree',
  'node_kind_counts',
  'nonterminal_dead_ends',
  'operational_factor_count',
  'reachable_nodes',
  'route_edges',
  'route_maximum_steps',
  'route_nodes',
  'stage_count',
  'terminal_nodes',
  'unreachable_nodes',
  'unsafe_action_count',
]);
const COMPILED_FORBIDDEN_FIELDS = new Set([
  'action_probability',
  'clinical_effect_probability',
  'compliance_probability',
  'empirical_distribution',
  'patient_outcome_probability',
  'physiology_transition_probability',
  'real_world_frequency',
  'treatment_effect',
  'treatment_recommendation',
]);
const SHA256 = /^[0-9a-f]{64}$/;

function normalize(value, location = '$') {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new Error(`non-integer or unsafe number:${location}`);
    return value;
  }
  if (Array.isArray(value)) return value.map((item, index) => normalize(item, `${location}[${index}]`));
  if (typeof value === 'object') {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = normalize(value[key], `${location}.${key}`);
    return out;
  }
  throw new Error(`unsupported canonical type:${location}:${typeof value}`);
}

function canonicalBytes(value) {
  return Buffer.from(JSON.stringify(normalize(value)), 'utf8');
}

function canonicalSha256(value) {
  return crypto.createHash('sha256').update(canonicalBytes(value)).digest('hex');
}

function fileSha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function hashWithout(record, ...keys) {
  const omitted = new Set(keys);
  return canonicalSha256(Object.fromEntries(Object.entries(record).filter(([key]) => !omitted.has(key))));
}

function loadObject(file, label) {
  const stats = fs.lstatSync(file);
  if (!stats.isFile() || stats.isSymbolicLink()) throw new Error(`required regular ${label} missing`);
  const value = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (value === null || Array.isArray(value) || typeof value !== 'object') throw new Error(`${label} is not an object`);
  return value;
}

function repoPath(repo, relative) {
  if (typeof relative !== 'string' || !relative || relative.includes('\0') || relative.includes('\\') || path.isAbsolute(relative)) throw new Error(`unsafe repository path:${String(relative)}`);
  const normalized = path.posix.normalize(relative);
  const parts = normalized.split('/');
  if (normalized === '..' || normalized.startsWith('../') || normalized.includes('/../') || normalized === '.' || parts.some((part) => !part || part === '.' || part === '..')) throw new Error(`unsafe repository path:${relative}`);
  if (parts.some((part) => part.includes(':') || part.endsWith(' ') || part.endsWith('.'))) throw new Error(`non-portable repository path:${relative}`);
  const candidate = path.resolve(repo, normalized);
  const root = path.resolve(repo);
  if (candidate !== root && !candidate.startsWith(`${root}${path.sep}`)) throw new Error(`repository path escape:${relative}`);
  let current = root;
  for (const part of parts.slice(0, -1)) {
    current = path.join(current, part);
    if (fs.existsSync(current) && fs.lstatSync(current).isSymbolicLink()) throw new Error(`symlinked repository path ancestor:${relative}`);
  }
  return candidate;
}

function deepEqual(left, right) {
  return JSON.stringify(normalize(left)) === JSON.stringify(normalize(right));
}

function scanForbidden(value, forbidden, location = '$', findings = []) {
  if (Array.isArray(value)) {
    value.forEach((item, index) => scanForbidden(item, forbidden, `${location}[${index}]`, findings));
  } else if (value && typeof value === 'object') {
    for (const [key, child] of Object.entries(value)) {
      if (forbidden.has(key.toLowerCase())) findings.push(`${location}.${key}`);
      scanForbidden(child, forbidden, `${location}.${key}`, findings);
    }
  }
  return findings;
}

function routeMetrics(route) {
  if (!Array.isArray(route?.nodes) || route.nodes.length === 0) throw new Error('scenario genome route nodes missing');
  if (!Array.isArray(route?.edges) || route.edges.length === 0) throw new Error('scenario genome route edges missing');
  if (typeof route.start_node_id !== 'string' || !route.start_node_id) throw new Error('scenario genome route start missing');

  const nodes = new Map();
  const kindCounts = new Map();
  const terminalIds = new Set();
  for (const node of route.nodes) {
    if (!node || typeof node !== 'object' || Array.isArray(node)) throw new Error('scenario genome route node malformed');
    if (typeof node.node_id !== 'string' || !node.node_id) throw new Error('scenario genome route node ID missing');
    if (nodes.has(node.node_id)) throw new Error(`scenario genome route node duplicated:${node.node_id}`);
    if (typeof node.node_kind !== 'string' || !node.node_kind) throw new Error(`scenario genome route node kind missing:${node.node_id}`);
    if (typeof node.terminal !== 'boolean') throw new Error(`scenario genome route terminal flag malformed:${node.node_id}`);
    nodes.set(node.node_id, node);
    kindCounts.set(node.node_kind, (kindCounts.get(node.node_kind) ?? 0) + 1);
    if (node.terminal) terminalIds.add(node.node_id);
  }
  if (!nodes.has(route.start_node_id)) throw new Error('scenario genome route start is unknown');
  if (terminalIds.size === 0) throw new Error('scenario genome route has no terminal');

  const adjacency = new Map([...nodes.keys()].map((nodeId) => [nodeId, []]));
  const edgeIds = new Set();
  for (const edge of route.edges) {
    if (!edge || typeof edge !== 'object' || Array.isArray(edge)) throw new Error('scenario genome route edge malformed');
    if (typeof edge.edge_id !== 'string' || !edge.edge_id) throw new Error('scenario genome route edge ID missing');
    if (edgeIds.has(edge.edge_id)) throw new Error(`scenario genome route edge duplicated:${edge.edge_id}`);
    edgeIds.add(edge.edge_id);
    if (!nodes.has(edge.from) || !nodes.has(edge.to)) throw new Error(`scenario genome route edge endpoint unknown:${edge.edge_id}`);
    adjacency.get(edge.from).push(edge.to);
  }
  for (const targets of adjacency.values()) targets.sort();

  const degreesByNode = new Map([...adjacency.entries()].map(([nodeId, targets]) => [nodeId, targets.length]));
  const terminalWithOutgoing = [...terminalIds].filter((nodeId) => degreesByNode.get(nodeId) !== 0).sort();
  if (terminalWithOutgoing.length) throw new Error(`scenario genome terminal has outgoing edge:${terminalWithOutgoing.join(',')}`);
  const nonterminalDeadEnds = [...nodes.keys()].filter((nodeId) => !terminalIds.has(nodeId) && degreesByNode.get(nodeId) === 0).sort();
  if (nonterminalDeadEnds.length) throw new Error(`scenario genome route has nonterminal dead end:${nonterminalDeadEnds.join(',')}`);

  const reachable = new Set();
  const pending = [route.start_node_id];
  while (pending.length) {
    const nodeId = pending.pop();
    if (reachable.has(nodeId)) continue;
    reachable.add(nodeId);
    for (const target of [...(adjacency.get(nodeId) ?? [])].reverse()) pending.push(target);
  }
  const unreachable = [...nodes.keys()].filter((nodeId) => !reachable.has(nodeId)).sort();
  if (unreachable.length) throw new Error(`scenario genome route has unreachable nodes:${unreachable.join(',')}`);

  const indegree = new Map([...nodes.keys()].map((nodeId) => [nodeId, 0]));
  for (const targets of adjacency.values()) for (const target of targets) indegree.set(target, indegree.get(target) + 1);
  const queue = [...nodes.keys()].filter((nodeId) => indegree.get(nodeId) === 0).sort();
  const topologicalOrder = [];
  while (queue.length) {
    const nodeId = queue.shift();
    topologicalOrder.push(nodeId);
    for (const target of adjacency.get(nodeId) ?? []) {
      indegree.set(target, indegree.get(target) - 1);
      if (indegree.get(target) === 0) {
        queue.push(target);
        queue.sort();
      }
    }
  }
  if (topologicalOrder.length !== nodes.size) throw new Error('scenario genome route contains cycle');
  const longest = new Map([...nodes.keys()].map((nodeId) => [nodeId, -1]));
  longest.set(route.start_node_id, 0);
  for (const nodeId of topologicalOrder) {
    if (longest.get(nodeId) < 0) continue;
    for (const target of adjacency.get(nodeId) ?? []) longest.set(target, Math.max(longest.get(target), longest.get(nodeId) + 1));
  }
  const maximumSteps = Math.max(...[...terminalIds].map((nodeId) => longest.get(nodeId)), -1);
  if (maximumSteps < 0) throw new Error('scenario genome route has no reachable terminal');
  const degrees = [...degreesByNode.values()];
  return {
    route_topology_profile: COMPILED_ROUTE_TOPOLOGY_PROFILE,
    route_nodes: route.nodes.length,
    route_edges: route.edges.length,
    reachable_nodes: reachable.size,
    unreachable_nodes: unreachable.length,
    terminal_nodes: terminalIds.size,
    nonterminal_dead_ends: nonterminalDeadEnds.length,
    cycle_free: true,
    branching_nodes: degrees.filter((value) => value > 1).length,
    maximum_out_degree: Math.max(...degrees, 0),
    route_maximum_steps: maximumSteps,
    node_kind_counts: Object.fromEntries([...kindCounts.entries()].sort(([a], [b]) => a.localeCompare(b))),
  };
}

function expectedActionCounts(packageValue) {
  const actions = packageValue?.scenario?.expected_actions;
  const categories = ['critical', 'important', 'optional', 'unsafe'];
  if (!actions || typeof actions !== 'object' || Array.isArray(actions)) throw new Error('scenario genome expected-action catalog missing');
  if (!deepEqual(Object.keys(actions).sort(), categories.slice().sort())) throw new Error('scenario genome expected-action category inventory differs');
  const result = {};
  for (const category of categories.sort()) {
    if (!Array.isArray(actions[category])) throw new Error(`scenario genome expected-action category malformed:${category}`);
    result[category] = actions[category].length;
  }
  return result;
}

function validatePolicy(policy, repo) {
  if (policy.schema_version !== '1.0.0') throw new Error('scenario genome policy schema differs');
  if (policy.policy_id !== COMPILED_POLICY_ID) throw new Error('scenario genome policy ID differs');
  if (policy.genome_schema_version !== COMPILED_GENOME_SCHEMA) throw new Error('scenario genome schema differs');
  if (policy.behavior_descriptor_profile !== COMPILED_DESCRIPTOR_PROFILE) throw new Error('scenario genome descriptor profile differs');
  if (policy.route_topology_profile !== COMPILED_ROUTE_TOPOLOGY_PROFILE) throw new Error('scenario genome route topology profile differs');
  if (!deepEqual(policy.authority_boundary, COMPILED_AUTHORITY_BOUNDARY)) throw new Error('scenario genome authority boundary differs');
  if (!deepEqual(new Set(policy.required_behavior_dimensions ?? []), COMPILED_REQUIRED_DIMENSIONS)) {
    // JSON cannot compare Sets; normalize them explicitly.
    const observed = [...new Set(policy.required_behavior_dimensions ?? [])].sort();
    const expected = [...COMPILED_REQUIRED_DIMENSIONS].sort();
    if (JSON.stringify(observed) !== JSON.stringify(expected)) throw new Error('scenario genome behavior dimension inventory differs');
  }
  const observedForbidden = [...new Set(policy.forbidden_genome_fields ?? [])].sort();
  const expectedForbidden = [...COMPILED_FORBIDDEN_FIELDS].sort();
  if (JSON.stringify(observedForbidden) !== JSON.stringify(expectedForbidden)) throw new Error('scenario genome forbidden-field inventory differs');
  if (!policy.provenance_requirements || !Object.values(policy.provenance_requirements).every((value) => value === true)) throw new Error('scenario genome provenance requirements differ');
  const sourceKeys = Object.keys(policy.source_paths ?? {}).sort();
  if (JSON.stringify(sourceKeys) !== JSON.stringify(['content_registry', 'independent_checker', 'scenario_package', 'writer'])) throw new Error('scenario genome source path inventory differs');
  for (const relative of [...Object.values(policy.source_paths), policy.output_path, policy.report_path]) repoPath(repo, relative);
}

function reconstruct(repo) {
  const policyPath = repoPath(repo, 'config/scenario-genome/SCENARIO_GENOME_POLICY.json');
  const policy = loadObject(policyPath, 'scenario genome policy');
  validatePolicy(policy, repo);
  const packagePath = repoPath(repo, policy.source_paths.scenario_package);
  const registryPath = repoPath(repo, policy.source_paths.content_registry);
  const writerPath = repoPath(repo, policy.source_paths.writer);
  const checkerPath = repoPath(repo, policy.source_paths.independent_checker);
  const packageValue = loadObject(packagePath, 'scenario package');
  const registry = loadObject(registryPath, 'content registry');
  loadObject(policyPath, 'scenario genome policy');
  for (const [file, label] of [[writerPath, 'scenario genome writer'], [checkerPath, 'scenario genome checker']]) {
    const stats = fs.lstatSync(file);
    if (!stats.isFile() || stats.isSymbolicLink()) throw new Error(`required regular ${label} missing`);
  }

  const authority = packageValue.authority;
  if (authority?.clinical_authority !== 'NOT_GRANTED') throw new Error('scenario package clinical authority escalated');
  if (authority?.deployment_scope !== 'research_sandbox_only') throw new Error('scenario package deployment scope differs');
  if (authority?.evidence_authority !== 'supporting_only') throw new Error('scenario package evidence authority escalated');
  if (authority?.scoring_behavior !== 'inherited_unchanged') throw new Error('scenario package scoring behavior changed');
  const certificate = packageValue.certificate;
  if (!certificate || !SHA256.test(certificate.package_sha256 ?? '')) throw new Error('scenario package certificate hash malformed');
  if (!certificate.checks || !Object.values(certificate.checks).every((value) => value === true)) throw new Error('scenario package certificate contains failed check');
  if (certificate.base_protected_sha256 !== certificate.output_protected_sha256) throw new Error('scenario protected projection changed');
  const registryRoot = registry?.roots?.registry_merkle_root;
  if (!SHA256.test(registryRoot ?? '')) throw new Error('content registry Merkle root malformed');

  const { build, scenario, blueprint, route } = packageValue;
  for (const [value, label] of [[build, 'build'], [scenario, 'scenario'], [blueprint, 'blueprint'], [route, 'route']]) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`scenario package ${label} missing`);
  }
  for (const [value, label] of [[packageValue.evidence, 'evidence'], [packageValue.atoms, 'atoms'], [packageValue.stages, 'stages'], [packageValue.field_origins, 'field origins']]) {
    if (!Array.isArray(value)) throw new Error(`scenario package ${label} missing`);
  }

  const operationalContext = scenario.operational_context;
  if (!operationalContext || typeof operationalContext !== 'object' || Array.isArray(operationalContext)) throw new Error('scenario operational context missing');
  const factors = Object.fromEntries(Object.entries(operationalContext).filter(([key]) => key !== 'narrative').sort(([a], [b]) => a.localeCompare(b)));
  if (!Object.values(factors).every((value) => typeof value === 'string' && value.length > 0)) throw new Error('scenario operational factors malformed');

  const routeDescriptor = routeMetrics(route);
  const actionCounts = expectedActionCounts(packageValue);
  const behaviorDescriptor = {
    descriptor_profile: COMPILED_DESCRIPTOR_PROFILE,
    ...routeDescriptor,
    expected_action_counts: actionCounts,
    unsafe_action_count: actionCounts.unsafe,
    evidence_references: packageValue.evidence.length,
    atom_count: packageValue.atoms.length,
    stage_count: packageValue.stages.length,
    field_origin_records: packageValue.field_origins.length,
    operational_factor_count: Object.keys(factors).length,
    operational_context_sha256: canonicalSha256(factors),
    route_sha256: canonicalSha256(route),
    protected_projection_sha256: certificate.output_protected_sha256,
  };
  const missing = [...COMPILED_REQUIRED_DIMENSIONS].filter((key) => !(key in behaviorDescriptor));
  if (missing.length) throw new Error(`scenario genome behavior dimensions missing:${missing.sort().join(',')}`);

  const seenEvidence = new Set();
  const evidenceRecords = packageValue.evidence.map((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw new Error('scenario genome evidence record malformed');
    if (typeof item.evidence_id !== 'string' || !item.evidence_id) throw new Error('scenario genome evidence ID missing');
    if (seenEvidence.has(item.evidence_id)) throw new Error(`scenario genome evidence ID duplicated:${item.evidence_id}`);
    seenEvidence.add(item.evidence_id);
    const record = {
      evidence_id: item.evidence_id,
      source_id: item.source_id,
      doi: item.doi,
      locator: item.locator,
      chunk_sha256: item.chunk_sha256,
      source_file_sha256: item.source_file_sha256,
      evidence_record_sha256: canonicalSha256(item),
    };
    if (!SHA256.test(record.chunk_sha256 ?? '')) throw new Error(`scenario genome evidence chunk hash malformed:${item.evidence_id}`);
    if (!SHA256.test(record.source_file_sha256 ?? '')) throw new Error(`scenario genome evidence source hash malformed:${item.evidence_id}`);
    return record;
  }).sort((left, right) => left.evidence_id.localeCompare(right.evidence_id));

  const identity = {
    identity_domain: policy.genome_identity_domain,
    source_scenario_id: build.source_scenario_id,
    scenario_id: scenario.scenario_id,
    blueprint_id: build.blueprint_id,
    topic_id: build.topic_id,
    seed: build.seed,
    retriever_track: build.retriever_track,
    scenario_package_path: policy.source_paths.scenario_package,
    scenario_package_file_sha256: fileSha256(packagePath),
    scenario_package_certificate_sha256: certificate.package_sha256,
    content_registry_path: policy.source_paths.content_registry,
    content_registry_file_sha256: fileSha256(registryPath),
    content_registry_merkle_root: registryRoot,
    policy_path: 'config/scenario-genome/SCENARIO_GENOME_POLICY.json',
    policy_file_sha256: fileSha256(policyPath),
    writer_path: policy.source_paths.writer,
    writer_file_sha256: fileSha256(writerPath),
    independent_checker_path: policy.source_paths.independent_checker,
    independent_checker_file_sha256: fileSha256(checkerPath),
  };
  for (const field of ['source_scenario_id', 'scenario_id', 'blueprint_id', 'topic_id', 'retriever_track']) {
    if (typeof identity[field] !== 'string' || !identity[field]) throw new Error(`scenario genome identity field missing:${field}`);
  }
  if (!Number.isSafeInteger(identity.seed)) throw new Error('scenario genome seed malformed');

  const genome = {
    schema_version: COMPILED_GENOME_SCHEMA,
    genome_id: 'PENDING',
    genome_sha256: 'PENDING',
    identity,
    authority_boundary: COMPILED_AUTHORITY_BOUNDARY,
    operational_factors: factors,
    behavior_descriptor: behaviorDescriptor,
    evidence_records: evidenceRecords,
    provenance_root_sha256: canonicalSha256({ identity, evidence_records: evidenceRecords }),
    limitations: [
      'No clinical authority is granted.',
      'Human and team behavior remains structural only and is not empirically calibrated.',
      'Operational timing remains not calibrated.',
      'Patient dynamics remain source-bound static observations only.',
      'Scoring behavior is inherited unchanged and is not a validated psychometric proficiency model.',
    ],
    truth_boundary: policy.truth_boundary,
  };
  const forbidden = scanForbidden(genome, COMPILED_FORBIDDEN_FIELDS);
  if (forbidden.length) throw new Error(`forbidden scenario genome fields:${forbidden.join(',')}`);
  const identityDigest = hashWithout(genome, 'genome_id', 'genome_sha256');
  genome.genome_id = `ASK-GENOME-${identityDigest.slice(0, 16).toUpperCase()}`;
  genome.genome_sha256 = hashWithout(genome, 'genome_sha256');
  normalize(genome);
  return { policy, genome };
}

let args;
try {
  args = parseCheckerArgs(process.argv.slice(2), { outputFlags: ['--report', '--json-output'], allowPositionalRepo: true });
} catch (error) {
  process.exit(emitCheckerResult(normalizedFailure(error, 'INDEPENDENT_NODE_SCENARIO_GENOME_RECONSTRUCTION_V1')));
}
const repo = args.repo;
let result;
try {
  const { policy, genome: expected } = reconstruct(repo);
  const genomePath = repoPath(repo, policy.output_path);
  const observed = loadObject(genomePath, 'scenario genome');
  const errors = [];
  if (!deepEqual(observed, expected)) errors.push('scenario genome differs from independent reconstruction');
  if (observed.genome_sha256 !== hashWithout(observed, 'genome_sha256')) errors.push('scenario genome self-hash mismatch');
  const identityDigest = hashWithout(observed, 'genome_id', 'genome_sha256');
  if (observed.genome_id !== `ASK-GENOME-${identityDigest.slice(0, 16).toUpperCase()}`) errors.push('scenario genome ID mismatch');
  const forbidden = scanForbidden(observed, COMPILED_FORBIDDEN_FIELDS);
  if (forbidden.length) errors.push(`forbidden scenario genome fields:${forbidden.join(',')}`);
  const bytes = fs.readFileSync(genomePath);
  if (bytes.includes(13)) errors.push('scenario genome contains carriage return');
  if (!bytes.toString('utf8').endsWith('\n')) errors.push('scenario genome final newline missing');
  result = {
    schema_version: '1.0.0',
    classification: errors.length === 0 ? 'PASS' : 'FAIL',
    status: errors.length === 0 ? 'PASS' : 'FAIL',
    checker_profile: 'INDEPENDENT_NODE_SCENARIO_GENOME_RECONSTRUCTION_V1',
    genome_id: observed.genome_id,
    genome_sha256: observed.genome_sha256,
    behavior_dimensions: Object.keys(observed.behavior_descriptor ?? {}).length,
    required_behavior_dimensions: COMPILED_REQUIRED_DIMENSIONS.size,
    evidence_records: Array.isArray(observed.evidence_records) ? observed.evidence_records.length : 0,
    errors: [...new Set(errors)].sort(),
  };
} catch (error) {
  result = {
    schema_version: '1.0.0',
    classification: 'FAIL',
    status: 'FAIL',
    checker_profile: 'INDEPENDENT_NODE_SCENARIO_GENOME_RECONSTRUCTION_V1',
    errors: [error instanceof Error ? `${error.name}:${error.message}` : String(error)],
  };
}
process.exit(emitCheckerResult(result, { repo, report: args.report }));
