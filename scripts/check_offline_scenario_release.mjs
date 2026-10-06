#!/usr/bin/env node
/** Independent Node reconstruction of the RC3.8A.1 offline-scenario release. */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { parseCheckerArgs, resolveRepoPath, emitCheckerResult } from './node_checker_cli.mjs';
import { EVOLUTION_START, EVOLUTION_END, graphContractSha256, renderEvolutionBlock, renderRootSection as renderSharedRootSection, renderStandaloneSection as renderSharedStandaloneSection } from './engine_evolution_documentation_common.mjs';

const COMPILED = Object.freeze({
  "releaseId": "ASK-OFFLINE-RC3.8A.1",
  "displayVersion": "RC3.8A.1",
  "evolution": "SCENARIO_SCIENCE_BEHAVIORAL_DIVERSITY_STAKEHOLDER_SCORECARD_TREATMENT_ADMISSION_PLAIN_LANGUAGE_DUAL_RATCHETS_V8",
  "graphId": "asklepios-rc3.8a.1-scenario-science-stakeholder-graph",
  "graphStages": 122,
  "graphTargets": 26,
  "graphBindingMode": "ACYCLIC_SEMANTIC_PROJECTION_V1",
  "capabilityId": "asklepios-scenario-capability-ratchet-v1",
  "capabilityEpoch": 5,
  "debtId": "asklepios-technical-debt-ratchet-v1",
  "debtEpoch": 8
});
const TRUTH = Object.freeze({
  "clinical_authority": "NOT_GRANTED",
  "human_team_behavior": "STRUCTURAL_ONLY_NOT_CALIBRATED",
  "operational_calibration": "NOT_CALIBRATED",
  "patient_care_use": "PROHIBITED",
  "patient_dynamics": "SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY",
  "quality_vector_use": "SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING",
  "scoring_behavior": "inherited_unchanged"
});
const GUARANTEES = Object.freeze({
  "content_security_policy_connect_none": true,
  "deterministic_replay": true,
  "external_runtime_assets": false,
  "installation_required": false,
  "network_requests": false,
  "server_required": false,
  "single_file": true
});
const WRITER_OWNED_SURFACES = Object.freeze([
  "root",
  "standalone"
]);
const VERIFICATION_ONLY_SURFACES = Object.freeze([
  "facility",
  "verified"
]);
const REQUIRED_CAPABILITIES = Object.freeze([
  "acyclic_release_identity_graph",
  "after_action_review",
  "behavioral_policy_equivalence_archive",
  "behavioral_quality_diversity_archive",
  "canonical_writer_independent_verifier",
  "capability_ratchet",
  "clock_driven_world_events",
  "complete_release_dag_diagnostics",
  "cross_platform_checker_cli_and_atomic_reports",
  "differential_engine_documentation_verification",
  "event_sourced_replay",
  "hidden_information_release",
  "integer_only_nonclinical_selection_vector",
  "learner_wit_separation",
  "monotonic_technical_debt_ratchet",
  "narrative_and_provenance_invariance_guard",
  "operational_scenario_pack",
  "plain_language_change_summary",
  "plain_language_release_contract",
  "playable_offline_role_model_profiles",
  "privacy_bounded_telemetry",
  "reachable_terminating_route_topology",
  "receipt_bound_evidence",
  "scenario_genome_identity",
  "scoped_technical_debt_receipt_gate",
  "source_bound_scoring",
  "source_conformance_scorecard",
  "stakeholder_capability_dashboard",
  "timeout_branch",
  "treatment_admission_pipeline",
  "unsafe_action_fail_closed_branches"
]);
const REQUIRED_DOC_LITERALS = Object.freeze({
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
const DOC_PHRASES = REQUIRED_DOC_LITERALS;
const PROHIBITED_LIVE_DEPLOYMENT_CLAIMS = Object.freeze([
  'deployment is currently healthy',
  'production deployment is healthy',
  'vercel preview is healthy',
  'the live deployment is healthy',
]);
const FORBIDDEN_DOC_CASEFOLD = Object.freeze({
  "root": [
    "deployment is currently healthy",
    "production deployment is healthy",
    "vercel preview is healthy",
    "the live deployment is healthy",
    "generated scenario catalog (107 toon-authored exercises)"
  ]
});
const ARTIFACTS = Object.freeze({
  "behavioral_diversity_policy": "config/scenario-science/BEHAVIORAL_DIVERSITY_POLICY.json",
  "capability_ratchet": "config/release/SCENARIO_CAPABILITY_RATCHET.json",
  "facility_manifest": "examples/facility-arrival/manifest.json",
  "facility_readme": "examples/facility-arrival/README.md",
  "operational_pack_policy": "config/scenario-science/OPERATIONAL_SCENARIO_PACK_POLICY.json",
  "operational_scenario_pack": "public/data/scenario_library/operational-pack.json",
  "plain_language_change_summary": "docs/RC3_8D_PLAIN_LANGUAGE_CHANGE_SUMMARY.md",
  "plain_language_release_contract": "config/product/PLAIN_LANGUAGE_RELEASE_CONTRACT.json",
  "playable_html": "examples/facility-arrival/playable.html",
  "root_readme": "README.md",
  "scenario_genome": "public/data/scenario_core/verified_scenario_genome.json",
  "scenario_science_policy": "config/scenario-science/SCENARIO_SCIENCE_POLICY.json",
  "stakeholder_capability_map": "config/product/STAKEHOLDER_CAPABILITY_MAP.json",
  "stakeholder_dashboard": "public/data/scenario_library/stakeholder-dashboard.json",
  "stakeholder_release_summary": "docs/RC3_8_STAKEHOLDER_RELEASE_SUMMARY.md",
  "standalone_documentation": "docs/FACILITY_ARRIVAL_STANDALONE.md",
  "technical_debt_ratchet": "config/release/TECHNICAL_DEBT_RATCHET.json",
  "treatment_admission_projection": "public/data/scenario_library/treatment-admission.json",
  "treatment_admission_registry": "config/scenario-science/TREATMENT_ADMISSION_REGISTRY.json",
  "verified_manifest": "examples/verified-scenario/manifest.json",
  "verified_readme": "examples/verified-scenario/README.md"
});

function sha256(buffer) { return crypto.createHash('sha256').update(buffer).digest('hex'); }
function readBytes(repo, relative) { return fs.readFileSync(resolveRepoPath(repo, relative, { allowMissing: false })); }
function readText(repo, relative) { return readBytes(repo, relative).toString('utf8'); }
function readObject(repo, relative) {
  const value = JSON.parse(readText(repo, relative));
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`JSON root is not an object:${relative}`);
  return value;
}
function normalize(value, location = '$') {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new Error(`non-safe or non-integer number:${location}`);
    return value;
  }
  if (Array.isArray(value)) return value.map((item, index) => normalize(item, `${location}[${index}]`));
  if (typeof value === 'object') {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = normalize(value[key], `${location}.${key}`);
    return out;
  }
  throw new Error(`unsupported canonical type:${location}`);
}
function canonicalSha(value) { return sha256(Buffer.from(JSON.stringify(normalize(value)), 'utf8')); }
function same(left, right) { return JSON.stringify(normalize(left)) === JSON.stringify(normalize(right)); }
function requireCheck(condition, errors, message) { if (!condition) errors.push(message); }


function context(repo, errors) {
  const policy = readObject(repo, 'config/release/OFFLINE_SCENARIO_RELEASE.json');
  const graph = readObject(repo, 'config/release/RELEASE_GRAPH.json');
  const genome = readObject(repo, 'public/data/scenario_core/verified_scenario_genome.json');
  const capability = readObject(repo, 'config/release/SCENARIO_CAPABILITY_RATCHET.json');
  const debt = readObject(repo, 'config/release/TECHNICAL_DEBT_RATCHET.json');
  requireCheck(policy.release_id === COMPILED.releaseId, errors, 'offline release policy ID differs');
  requireCheck(policy.display_version === COMPILED.displayVersion, errors, 'offline release display version differs');
  requireCheck(policy.engine_evolution === COMPILED.evolution, errors, 'offline engine-evolution profile differs');
  requireCheck(policy.expected_graph_id === COMPILED.graphId, errors, 'offline policy graph ID differs');
  requireCheck(policy.expected_graph_stage_count === COMPILED.graphStages, errors, 'offline policy graph stage count differs');
  requireCheck(policy.expected_graph_target_count === COMPILED.graphTargets, errors, 'offline policy graph target count differs');
  requireCheck(policy.release_graph_binding_mode === COMPILED.graphBindingMode, errors, 'offline graph binding mode differs');
  requireCheck(policy.expected_capability_ratchet_id === COMPILED.capabilityId && policy.expected_capability_ratchet_epoch === COMPILED.capabilityEpoch, errors, 'offline policy capability-ratchet floor differs');
  requireCheck(policy.expected_technical_debt_ratchet_id === COMPILED.debtId && policy.expected_technical_debt_ratchet_epoch === COMPILED.debtEpoch, errors, 'offline policy technical-debt-ratchet floor differs');
  requireCheck(same(policy.truth_boundary, TRUTH), errors, 'offline truth boundary differs');
  requireCheck(same(policy.offline_guarantees, GUARANTEES), errors, 'offline guarantee contract differs');
  requireCheck(same([...(policy.required_capabilities ?? [])].sort(), [...REQUIRED_CAPABILITIES].sort()), errors, 'offline capability inventory differs');
  requireCheck(same(policy.documentation_contract?.required_literals, REQUIRED_DOC_LITERALS), errors, 'offline documentation required-literal contract differs');
  requireCheck(same(policy.documentation_contract?.forbidden_casefold_phrases, FORBIDDEN_DOC_CASEFOLD), errors, 'offline documentation forbidden-phrase contract differs');
  requireCheck(same(policy.documentation_contract?.writer_owned_surfaces, WRITER_OWNED_SURFACES), errors, 'offline documentation writer-owned surface contract differs');
  requireCheck(same(policy.documentation_contract?.verification_only_surfaces, VERIFICATION_ONLY_SURFACES), errors, 'offline documentation verification-only surface contract differs');
  const owned = [...(policy.documentation_contract?.writer_owned_surfaces ?? []), ...(policy.documentation_contract?.verification_only_surfaces ?? [])];
  requireCheck(new Set(owned).size === 4 && same([...new Set(owned)].sort(), ['facility', 'root', 'standalone', 'verified']), errors, 'offline documentation ownership partition differs');
  const observedArtifacts = Object.fromEntries((policy.artifact_inventory ?? []).map((record) => [record.name, record.path]));
  requireCheck(same(observedArtifacts, ARTIFACTS), errors, 'offline artifact inventory differs');
  requireCheck(graph.graph_id === COMPILED.graphId, errors, 'offline release graph identity differs');
  requireCheck((graph.stages ?? []).length === COMPILED.graphStages, errors, 'offline release graph stage count differs');
  requireCheck(Object.keys(graph.targets ?? {}).length === COMPILED.graphTargets, errors, 'offline release graph target count differs');
  requireCheck(capability.ratchet_id === COMPILED.capabilityId && capability.ratchet_epoch === COMPILED.capabilityEpoch, errors, 'offline capability ratchet binding differs');
  requireCheck(debt.ratchet_id === COMPILED.debtId && debt.ratchet_epoch === COMPILED.debtEpoch, errors, 'offline technical-debt ratchet binding differs');
  requireCheck(same(capability.authority_boundary, TRUTH), errors, 'capability-ratchet truth boundary differs');
  return { policy, graph, genome, capability, debt };
}

function evolutionBinding(ctx) {
  return {
    release_id: ctx.policy.release_id,
    display_version: ctx.policy.display_version,
    engine_evolution: ctx.policy.engine_evolution,
    scenario_genome: { genome_id: ctx.genome.genome_id, genome_sha256: ctx.genome.genome_sha256 },
    capability_ratchet: { ratchet_id: ctx.capability.ratchet_id, ratchet_epoch: ctx.capability.ratchet_epoch, ratchet_anchor_sha256: ctx.capability.ratchet_anchor_sha256 },
    technical_debt_ratchet: { ratchet_id: ctx.debt.ratchet_id, ratchet_epoch: ctx.debt.ratchet_epoch, ratchet_anchor_sha256: ctx.debt.ratchet_anchor_sha256 },
    release_graph: {
      graph_id: ctx.graph.graph_id,
      stage_count: ctx.graph.stages.length,
      target_count: Object.keys(ctx.graph.targets).length,
      binding_mode: COMPILED.graphBindingMode,
      contract_sha256: graphContractSha256(ctx.graph),
    },
    capability_floor: { scenario_experience: ctx.capability.hard_floors.scenario_experience, scenario_contract: ctx.capability.hard_floors.scenario_contract },
    offline_guarantees: ctx.policy.offline_guarantees,
    truth_boundary: ctx.policy.truth_boundary,
  };
}



function documentationRenderOptions(ctx) {
  return {
    graphBindingMode: COMPILED.graphBindingMode,
    graphContractSha256: graphContractSha256(ctx.graph),
  };
}

function canonicalEvolutionBlock(ctx) {
  return renderEvolutionBlock(ctx, documentationRenderOptions(ctx));
}



function exactMarkedSection(text, start, end, label, errors) {
  const startCount = text.split(start).length - 1;
  const endCount = text.split(end).length - 1;
  if (startCount !== 1 || endCount !== 1) {
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

function buildDescriptor(repo, ctx) {
  const artifacts = Object.entries(ARTIFACTS).sort(([a], [b]) => a.localeCompare(b)).map(([name, relative]) => {
    const raw = readBytes(repo, relative);
    return { name, path: relative, bytes: raw.length, sha256: sha256(raw) };
  });
  const exp = ctx.capability.hard_floors.scenario_experience;
  const descriptor = {
    schema_version: '1.1.0',
    release_id: ctx.policy.release_id,
    display_version: ctx.policy.display_version,
    engine_evolution: ctx.policy.engine_evolution,
    policy: { path: 'config/release/OFFLINE_SCENARIO_RELEASE.json', file_sha256: sha256(readBytes(repo, 'config/release/OFFLINE_SCENARIO_RELEASE.json')) },
    scenario_genome: { path: 'public/data/scenario_core/verified_scenario_genome.json', genome_id: ctx.genome.genome_id, genome_sha256: ctx.genome.genome_sha256 },
    capability_ratchet: { path: 'config/release/SCENARIO_CAPABILITY_RATCHET.json', ratchet_id: ctx.capability.ratchet_id, ratchet_epoch: ctx.capability.ratchet_epoch, ratchet_anchor_sha256: ctx.capability.ratchet_anchor_sha256 },
    technical_debt_ratchet: { path: 'config/release/TECHNICAL_DEBT_RATCHET.json', ratchet_id: ctx.debt.ratchet_id, ratchet_epoch: ctx.debt.ratchet_epoch, ratchet_anchor_sha256: ctx.debt.ratchet_anchor_sha256 },
    release_graph: {
      path: 'config/release/RELEASE_GRAPH.json',
      graph_id: ctx.graph.graph_id,
      stage_count: ctx.graph.stages.length,
      target_count: Object.keys(ctx.graph.targets).length,
      binding_mode: COMPILED.graphBindingMode,
      contract_sha256: graphContractSha256(ctx.graph),
    },
    artifacts,
    required_capabilities: [...ctx.policy.required_capabilities].sort(),
    offline_guarantees: ctx.policy.offline_guarantees,
    truth_boundary: ctx.policy.truth_boundary,
    repository_documentation: {
      canonical_repository_url: ctx.policy.canonical_repository_url,
      root_start_marker: ctx.policy.documentation_contract.root_start_marker,
      root_end_marker: ctx.policy.documentation_contract.root_end_marker,
      scenario_experience_floor: exp.generated_cases,
      scenario_context_floor: exp.unique_operational_contexts,
      static_exercise_catalog_count: 100,
      deployment_claim_mode: 'CONFIGURATION_INSTRUCTIONS_ONLY_NO_LIVE_HEALTH_CLAIM',
    },
  };
  descriptor.release_sha256 = canonicalSha(descriptor);
  return descriptor;
}

function validateRuntime(repo, ctx, errors) {
  const html = readText(repo, 'examples/facility-arrival/playable.html');
  const csp = html.match(/<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]+)"/i);
  requireCheck(Boolean(csp?.[1]?.includes("connect-src 'none'")), errors, 'playable CSP connection boundary missing');
  const patterns = [/<script\b[^>]*\bsrc\s*=/i, /<link\b[^>]*\brel\s*=\s*['"]?stylesheet/i, /\bfetch\s*\(/i, /\bXMLHttpRequest\b/i, /\bWebSocket\s*\(/i, /\bEventSource\s*\(/i, /\bnavigator\.sendBeacon\s*\(/i];
  for (const pattern of patterns) if (pattern.test(html)) errors.push(`playable forbidden runtime pattern:${pattern.source}`);
  const match = html.match(/<script\s+type="application\/json"\s+id="asklepios-scenario-data">(.*?)<\/script>/s);
  if (!match) { errors.push('playable embedded payload missing'); return; }
  let payload;
  try { payload = JSON.parse(match[1]); } catch { errors.push('playable embedded payload malformed'); return; }
  requireCheck(payload.release_id === ctx.policy.release_id, errors, 'playable release identity differs');
  requireCheck(payload.standalone_mode === 'single_file_no_network', errors, 'playable standalone mode differs');
  requireCheck(same(payload.scenario_evolution, evolutionBinding(ctx)), errors, 'playable scenario-evolution binding differs');
  requireCheck(payload.authority?.patient_care_use === 'PROHIBITED', errors, 'playable patient-care authority escalated');
}




function validateDocumentation(repo, ctx, errors) {
  const docs = ctx.policy.documentation_contract;
  const surfaces = {
    root: docs.root_readme,
    standalone: docs.standalone_readme,
    facility: docs.facility_readme,
    verified: docs.verified_readme,
  };
  const texts = {};
  for (const [surface, relative] of Object.entries(surfaces)) {
    try { texts[surface] = readText(repo, relative); }
    catch (error) { errors.push(`engine-evolution document missing or unsafe:${relative}`); }
  }
  const rootSection = exactMarkedSection(texts.root ?? '', docs.root_start_marker, docs.root_end_marker, 'root', errors);
  if (rootSection !== null) requireCheck(rootSection === renderSharedRootSection(ctx, documentationRenderOptions(ctx)), errors, 'canonical engine-evolution document differs:README.md');
  const standaloneSection = exactMarkedSection(texts.standalone ?? '', docs.standalone_start_marker, docs.standalone_end_marker, 'standalone', errors);
  if (standaloneSection !== null) requireCheck(standaloneSection === renderSharedStandaloneSection(ctx, documentationRenderOptions(ctx)), errors, 'canonical engine-evolution document differs:docs/FACILITY_ARRIVAL_STANDALONE.md');
  for (const surface of ['facility', 'verified']) {
    const section = exactMarkedSection(texts[surface] ?? '', EVOLUTION_START, EVOLUTION_END, surface, errors);
    if (section !== null) requireCheck(section === canonicalEvolutionBlock(ctx), errors, `canonical engine-evolution block differs:${surface}`);
  }
  const tokens = [
    ctx.policy.release_id, ctx.policy.display_version, ctx.policy.engine_evolution,
    ctx.genome.genome_id, ctx.genome.genome_sha256, ctx.capability.ratchet_id,
    String(ctx.capability.ratchet_epoch), ctx.capability.ratchet_anchor_sha256,
    ctx.debt.ratchet_id, String(ctx.debt.ratchet_epoch), ctx.debt.ratchet_anchor_sha256,
    ctx.graph.graph_id, String(ctx.graph.stages.length), String(Object.keys(ctx.graph.targets).length),
  ];
  for (const [surface, current] of Object.entries(texts)) {
    const folded = current.toLocaleLowerCase('en-US');
    for (const token of tokens) requireCheck(current.includes(token), errors, `engine-evolution identity missing:${surface}:${token}`);
    for (const phrase of DOC_PHRASES[surface]) requireCheck(folded.includes(phrase.toLocaleLowerCase('en-US')), errors, `engine-evolution guardrail missing:${surface}:${phrase}`);
    for (const literal of REQUIRED_DOC_LITERALS[surface] ?? []) requireCheck(folded.includes(literal.toLocaleLowerCase('en-US')), errors, `offline documentation required literal missing:${surface}:${literal}`);
    for (const forbidden of FORBIDDEN_DOC_CASEFOLD[surface] ?? []) requireCheck(!folded.includes(forbidden), errors, `offline documentation forbidden claim:${surface}:${forbidden}`);
  }
  const root = texts.root ?? '';
  const repositoryLines = root.split(/\r?\n/).map((line) => line.trim()).filter((line) => line.toLowerCase().startsWith('canonical repository:'));
  requireCheck(same(repositoryLines, [`Canonical repository: ${ctx.policy.canonical_repository_url}`]), errors, 'canonical repository declaration differs');
  requireCheck(root.includes('## Static exercise catalog (100 TOON-authored exercises)'), errors, 'static exercise catalog identity differs');
  const requiredRootLines = [
    '- Checker boundary: all Node scenario-release checkers share one strict cross-platform CLI, repository-relative path guard, and atomic report writer.',
    '- Artifact authority: every governed artifact class has one canonical writer and at least one independently implemented read-only verifier.',
    '- Evidence freshness: final joins authenticate the current graph, stage configuration, input hashes, output hashes, and receipt chain; a copied \`PASS\` report is insufficient.',
    `- Release-identity DAG: the offline descriptor binds \`${COMPILED.graphBindingMode}\` contract \`${graphContractSha256(ctx.graph)}\` rather than the graph's raw file hash, while the graph independently locks the descriptor. This prevents self-referential hash cycles.`,
    '- Route topology: only reachable, terminating, cycle-free routes with zero reachable nonterminal dead ends are admitted.',
    '- Technical-debt ratchet: reviewed debt records, blocker classifications, evidence floors, and final receipt obligations cannot be silently removed or weakened.',
    '- Diagnostic model: independent read-only branches may continue after a failure so one run can report the complete safe failure inventory; publication still fails closed.',
  ];
  const rootLines = new Set(root.split(/\r?\n/).map((line) => line.trim()));
  for (const line of requiredRootLines) requireCheck(rootLines.has(line), errors, `canonical root guardrail differs:${line.split(':', 1)[0]}`);
  const rootFolded = root.toLocaleLowerCase('en-US');
  for (const claim of PROHIBITED_LIVE_DEPLOYMENT_CLAIMS) requireCheck(!rootFolded.includes(claim), errors, `unsupported live deployment claim:${claim}`);
  requireCheck(!/^##\s+Generated scenario catalog \(107 TOON-authored exercises\)\s*$/im.test(root), errors, 'static exercise catalog conflated with generated scenarios');
}

function check(repo) {
  const errors = [];
  let ctx;
  try { ctx = context(repo, errors); } catch (error) { errors.push(`${error?.name ?? 'Error'}:${error?.message ?? String(error)}`); return { errors }; }
  let expected;
  try { expected = buildDescriptor(repo, ctx); } catch (error) { errors.push(`${error?.name ?? 'Error'}:${error?.message ?? String(error)}`); return { errors, ctx }; }
  let current;
  try { current = readObject(repo, ctx.policy.output_path); } catch (error) { errors.push(`offline descriptor unavailable:${error?.message ?? error}`); return { errors, ctx, expected }; }
  requireCheck(same(current, expected), errors, 'offline scenario release differs');
  const unsigned = { ...current }; delete unsigned.release_sha256;
  requireCheck(current.release_sha256 === canonicalSha(unsigned), errors, 'offline release self hash differs');
  validateRuntime(repo, ctx, errors);
  validateDocumentation(repo, ctx, errors);
  const root = readText(repo, ctx.policy.documentation_contract.root_readme);
  requireCheck(root.includes(String(ctx.capability.hard_floors.scenario_experience.generated_cases)), errors, 'scenario experience floor missing');
  requireCheck(root.includes(String(ctx.capability.hard_floors.scenario_experience.unique_operational_contexts)), errors, 'scenario context floor missing');
  return { errors, ctx, expected };
}

let parsed;
try {
  parsed = parseCheckerArgs(process.argv.slice(2), { outputFlags: ['--report', '--json-output', '--output'], allowPositionalRepo: true });
} catch (error) {
  const result = { schema_version: '1.2.0', classification: 'FAIL', status: 'FAIL', checker_profile: 'INDEPENDENT_NODE_OFFLINE_SCENARIO_RELEASE_V5', errors: [`${error?.name ?? 'Error'}:${error?.message ?? String(error)}`] };
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  process.exitCode = 3;
}
if (parsed) {
  let result;
  try {
    const { errors, ctx, expected } = check(parsed.repo);
    const classification = errors.length === 0 ? 'PASS' : 'FAIL';
    result = {
      schema_version: '1.2.0', classification, status: classification,
      checker_profile: 'INDEPENDENT_NODE_OFFLINE_SCENARIO_RELEASE_V5',
      release_id: expected?.release_id ?? ctx?.policy?.release_id ?? null,
      release_sha256: expected?.release_sha256 ?? null,
      graph_id: ctx?.graph?.graph_id ?? null,
      capability_ratchet_epoch: ctx?.capability?.ratchet_epoch ?? null,
      technical_debt_ratchet_epoch: ctx?.debt?.ratchet_epoch ?? null,
      artifacts: expected?.artifacts?.length ?? 0,
      errors: [...new Set(errors)].sort(),
    };
  } catch (error) {
    result = { schema_version: '1.2.0', classification: 'INTERNAL_ERROR', status: 'INTERNAL_ERROR', checker_profile: 'INDEPENDENT_NODE_OFFLINE_SCENARIO_RELEASE_V5', errors: [`${error?.name ?? 'Error'}:${error?.message ?? String(error)}`] };
  }
  process.exitCode = emitCheckerResult(result, { repo: parsed.repo, report: parsed.report });
}
