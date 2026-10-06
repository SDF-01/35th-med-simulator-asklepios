#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { lstatSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, resolve, sep } from 'node:path';

const PROFILES = [
  'DIRECT_HANDOFF_BASELINE',
  'COMMUNICATION_RELAY_REQUIRED',
  'RESOURCE_COORDINATION_REQUIRED',
  'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
];
const REQUIRED_STAKEHOLDERS = ['instructor', 'learner', 'maintainer', 'scientific_reviewer'];
const CAPABILITY_IDS = [
  "BEHAVIORALLY_DISTINCT_OPERATIONAL_PROFILES",
  "DETERMINISTIC_SCENARIO_LIBRARY",
  "HASH_CHAINED_SIMULATION_TELEMETRY",
  "OFFLINE_FACILITY_ARRIVAL_SCENARIO",
  "PLAIN_LANGUAGE_RELEASE_TRANSLATION",
  "REPRODUCIBLE_RELEASE_EVIDENCE",
  "ROLE_BOUND_DECISION_EXPERIENCES",
  "SOURCE_CONFORMANCE_SCORECARD",
  "TREATMENT_ADMISSION_TRANSPARENCY"
];
const TREATMENT_STATES = [
  'DISCOVERED', 'SOURCE_BYTES_VERIFIED', 'EVIDENCE_SPAN_BOUND', 'APPLICABILITY_REVIEWED',
  'CONTRAINDICATION_MODEL_REVIEWED', 'ROLE_SCOPE_BOUND', 'SIMULATED_EFFECT_ADJUDICATED',
  'INDEPENDENTLY_ATTESTED', 'SIMULATION_ADMITTED',
];
const PLAIN_HEADINGS = [
  'What changed?', 'What can a learner do now?', 'What can an instructor do now?',
  'What changed in scenario variety?', 'What changed in scoring?', 'What changed in treatment content?',
  'What safety limitation remains?', 'What is still not calibrated or validated?',
];
const REQUIRED_PHRASES = [
  'healthcare simulation', 'direct patient care remains prohibited', 'operational timing remains not calibrated',
  'not a validated proficiency measure', 'no concrete treatment is simulation-admitted',
];
const FORBIDDEN = [
  'clinically validated', 'safe for real patient care', 'medical advice', 'diagnoses patients',
  'treatment recommendations for real patients', 'fully calibrated', 'debt free', 'all bugs are impossible',
];

function parseArgs(argv) {
  const result = { repo: '.', jsonOutput: 'reports/stakeholder-product-bundle-node.json' };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (item === '--repo') result.repo = argv[++index];
    else if (item === '--json-output') result.jsonOutput = argv[++index];
    else throw new Error(`unknown argument:${item}`);
  }
  return result;
}
function canonical(value) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('non-finite canonical number');
    return JSON.stringify(Object.is(value, -0) ? 0 : value);
  }
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (typeof value === 'object') return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  throw new Error(`unsupported canonical value:${typeof value}`);
}
function sha(value) { return createHash('sha256').update(canonical(value), 'utf8').digest('hex'); }
function safePath(root, value, label) {
  if (typeof value !== 'string' || !value || value.includes('\0') || value.includes('\\') || isAbsolute(value)) throw new Error(`unsafe repository path:${label}`);
  const parts = value.split('/');
  if (parts.some((part) => !part || part === '.' || part === '..' || part.includes(':') || part.endsWith(' ') || part.endsWith('.'))) throw new Error(`unsafe repository path:${label}`);
  const candidate = resolve(root, ...parts); const prefix = root.endsWith(sep) ? root : `${root}${sep}`;
  if (candidate !== root && !candidate.startsWith(prefix)) throw new Error(`repository path escapes root:${label}`);
  let current = root;
  for (const part of parts.slice(0, -1)) {
    current = resolve(current, part);
    try { if (lstatSync(current).isSymbolicLink()) throw new Error(`symlinked repository parent rejected:${label}`); }
    catch (error) { if (error?.code !== 'ENOENT') throw error; }
  }
  return candidate;
}
function readJson(path) {
  const value = JSON.parse(readFileSync(path, 'utf8'));
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`JSON object required:${path}`);
  return value;
}
function writeJson(path, value) {
  mkdirSync(dirname(path), { recursive: true }); const temp = `${path}.tmp-${process.pid}`;
  writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, 'utf8'); renameSync(temp, path);
}
function verifyHash(value, field, label, errors) {
  const observed = value[field]; const body = { ...value }; delete body[field];
  if (!/^[0-9a-f]{64}$/.test(String(observed ?? ''))) errors.push(`${label} self hash is invalid`);
  else if (observed !== sha(body)) errors.push(`${label} self hash differs`);
}
function dimension(dimensionId, status, message, nodes = [], edges = [], events = []) {
  return {
    dimension_id: dimensionId, status,
    evidence_node_ids: [...new Set(nodes)].sort(), evidence_edge_ids: [...new Set(edges)].sort(), evidence_event_ids: [...new Set(events)].sort(),
    plain_language_finding: message, scoring_authority: 'SOURCE_CONFORMANCE_ONLY', psychometric_validity: 'NOT_ESTABLISHED',
  };
}
function scorecard(profile) {
  const relay = profile === 'COMMUNICATION_RELAY_REQUIRED' || profile === 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION';
  const resource = profile === 'RESOURCE_COORDINATION_REQUIRED' || profile === 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION';
  const pressure = ['pressure', ...(resource ? ['resource-coordination'] : [])];
  const communication = [...(relay ? ['communications-relay'] : []), 'handoff'];
  let lastEdge = 6 + (relay ? 1 : 0) + (resource ? 1 : 0);
  const dimensions = [
    dimension('situation_assessment', 'SATISFIED', 'The trace reached the reviewed observation step.', ['contact']),
    dimension('information_management', 'SATISFIED', 'The learner encountered and processed an operational information constraint.', pressure),
    dimension('prioritization', 'SATISFIED', 'The trace preserved the reviewed brief, movement, and contact order.', ['briefing', 'approach', 'contact']),
    dimension('communication', 'SATISFIED', relay ? 'The trace completed the required relay and final handoff steps.' : 'The trace completed the reviewed handoff step.', communication),
    dimension('resource_coordination', resource ? 'SATISFIED' : 'NOT_APPLICABLE', resource ? 'The trace completed the required resource-coordination step.' : 'This operational profile does not require the constrained-resource coordination step.', resource ? ['resource-coordination'] : []),
    dimension('reassessment', 'SATISFIED', 'The trace addressed an operational constraint after contact and before handoff.', pressure),
    dimension('closed_loop_handoff', 'SATISFIED', 'The trace closed the handoff and reached the terminal state.', communication, [`e${lastEdge}`]),
    dimension('safety', 'SATISFIED', 'No critical safety event was recorded in the completed trace.'),
  ];
  const without = {
    schema_version: '1.0.0', scorecard_profile: 'SOURCE_CONFORMANCE_MULTIDIMENSIONAL_SCORECARD_V1',
    route_id: `ASK-STAKEHOLDER-REFERENCE:${profile}`, operational_behavior_profile_id: profile,
    overall_status: 'PASS', safety_gate: 'PASS', source_conformance_score_bps: 10000,
    evidence_sufficient_for_composite: true, dimensions,
    timing_score_effect: 'NONE_UNTIL_CALIBRATED_FOR_DECLARED_SCOPE', scoring_state: 'SOURCE_CONFORMANCE_ONLY',
    validity_boundary: 'NOT_A_VALIDATED_PROFICIENCY_MEASURE',
  };
  return { ...without, scorecard_sha256: sha(without) };
}
function expectedDashboard(capabilityMap, registry, science, contract, pack) {
  const admitted = registry.entries.filter((entry) => entry.simulation_admitted === true);
  const without = {
    schema_version: '1.0.0', classification: 'PASS', status: 'PASS', dashboard_id: 'ASK-STAKEHOLDER-DASHBOARD-RC3-8',
    dashboard_profile: 'SCENARIO_LIBRARY_SCORECARD_TREATMENT_AND_EVIDENCE_SURFACE_V1', scenario_pack: pack,
    stakeholder_capability_map: { map_id: capabilityMap.map_id, map_epoch: capabilityMap.map_epoch, map_sha256: capabilityMap.map_sha256, capabilities: capabilityMap.capabilities },
    reference_scorecards: PROFILES.map(scorecard),
    treatment_admission: { registry_id: registry.registry_id, registry_epoch: registry.registry_epoch, registry_sha256: registry.registry_sha256, state_order: registry.state_order, entries: registry.entries, admitted_treatment_count: admitted.length },
    scenario_science_readiness: {
      policy_id: science.policy_id, policy_epoch: science.policy_epoch, policy_sha256: science.policy_sha256, telemetry_profile: science.telemetry_profile,
      evidence_state_order: science.evidence_state_order, calibration_state_order: science.calibration_state_order, scoring_state_order: science.scoring_state_order,
      current_operational_timing: science.timing_scoring_boundary.current_operational_timing,
      current_scoring_state: science.scoring_boundary.current_scoring_state,
    },
    plain_language_release: { contract_id: contract.contract_id, contract_epoch: contract.contract_epoch, contract_sha256: contract.contract_sha256, summary_path: contract.summary_path, required_headings: contract.required_headings },
    truth_boundaries: {
      healthcare_simulation: 'PERMITTED_WITHIN_VALIDATED_SCOPE', direct_patient_care: 'PROHIBITED', clinical_decision_support: 'PROHIBITED', patient_care_authority: 'NONE',
      operational_timing: 'NOT_CALIBRATED', scoring_validity: 'SOURCE_CONFORMANCE_ONLY_NOT_PSYCHOMETRICALLY_VALIDATED', concrete_treatments_admitted: 0,
    },
  };
  return { ...without, dashboard_root_sha256: sha(without) };
}

let errors = [];
try {
  const args = parseArgs(process.argv.slice(2)); const root = resolve(args.repo);
  const capabilityMap = readJson(safePath(root, 'config/product/STAKEHOLDER_CAPABILITY_MAP.json', 'capability_map'));
  const registry = readJson(safePath(root, 'config/scenario-science/TREATMENT_ADMISSION_REGISTRY.json', 'treatment_registry'));
  const science = readJson(safePath(root, 'config/scenario-science/SCENARIO_SCIENCE_POLICY.json', 'science_policy'));
  const contract = readJson(safePath(root, 'config/product/PLAIN_LANGUAGE_RELEASE_CONTRACT.json', 'plain_contract'));
  const pack = readJson(safePath(root, 'public/data/scenario_library/operational-pack.json', 'operational_pack'));
  const dashboard = readJson(safePath(root, 'public/data/scenario_library/stakeholder-dashboard.json', 'dashboard'));
  verifyHash(capabilityMap, 'map_sha256', 'stakeholder capability map', errors);
  verifyHash(registry, 'registry_sha256', 'treatment admission registry', errors);
  verifyHash(science, 'policy_sha256', 'scenario science policy', errors);
  verifyHash(contract, 'contract_sha256', 'plain language release contract', errors);
  const packBody = { ...pack }; delete packBody.catalog_root_sha256;
  if (pack.catalog_root_sha256 !== sha(packBody)) errors.push('operational scenario catalog root differs');
  if (pack.entry_count !== 12) errors.push('operational scenario catalog entry count differs');
  if (canonical(capabilityMap.required_stakeholders?.slice().sort()) !== canonical(REQUIRED_STAKEHOLDERS)) errors.push('required stakeholder inventory differs');
  const ids = capabilityMap.capabilities?.map((item) => item.capability_id).sort() ?? [];
  if (canonical(ids) !== canonical(CAPABILITY_IDS)) errors.push('capability identity inventory differs');
  for (const item of capabilityMap.capabilities ?? []) {
    for (const field of ['stakeholders', 'interface_paths', 'source_of_truth', 'limitations', 'tests']) {
      if (!Array.isArray(item[field]) || item[field].length === 0) errors.push(`capability list missing:${item.capability_id}:${field}`);
    }
    for (const path of [...(item.source_of_truth ?? []), item.owner_module, ...(item.tests ?? [])]) {
      if (String(path).startsWith('/')) continue;
      try { readFileSync(safePath(root, path, `capability:${item.capability_id}`)); }
      catch { errors.push(`capability source missing:${item.capability_id}:${path}`); }
    }
  }
  if (canonical(registry.state_order) !== canonical(TREATMENT_STATES)) errors.push('treatment admission state order differs');
  let admitted = 0;
  for (const entry of registry.entries ?? []) {
    if (entry.simulation_admitted === true) {
      admitted += 1;
      if (entry.current_state !== 'SIMULATION_ADMITTED' || entry.concrete_treatment_allowed !== true || canonical(entry.missing_requirements) !== '[]') errors.push(`treatment admission prerequisites incomplete:${entry.treatment_id}`);
    } else if (entry.concrete_treatment_allowed !== false || !Array.isArray(entry.missing_requirements) || entry.missing_requirements.length === 0) {
      errors.push(`blocked treatment requirements differ:${entry.treatment_id}`);
    }
  }
  if (admitted !== 0) errors.push('concrete treatment unexpectedly simulation-admitted');
  if (canonical(contract.required_headings) !== canonical(PLAIN_HEADINGS)) errors.push('plain-language required heading inventory differs');
  if (canonical(contract.required_phrases) !== canonical(REQUIRED_PHRASES)) errors.push('plain-language required phrase inventory differs');
  if (canonical(contract.forbidden_claims) !== canonical(FORBIDDEN)) errors.push('plain-language forbidden-claim inventory differs');
  const summary = readFileSync(safePath(root, contract.summary_path, 'plain_summary'), 'utf8'); const lower = summary.toLowerCase();
  for (const heading of PLAIN_HEADINGS) if (!summary.includes(`## ${heading}`)) errors.push(`plain-language heading missing:${heading}`);
  for (const phrase of REQUIRED_PHRASES) if (!lower.includes(phrase)) errors.push(`plain-language required phrase missing:${phrase}`);
  for (const phrase of FORBIDDEN) if (lower.includes(phrase)) errors.push(`plain-language forbidden claim present:${phrase}`);
  const app = readFileSync(safePath(root, 'src/App.tsx', 'app'), 'utf8'); const page = readFileSync(safePath(root, 'src/pages/ScenarioLibraryPage.tsx', 'page'), 'utf8');
  const routeMarkers = new Map([
    ['/scenarios', 'path="/scenarios" element={<ScenarioLibraryPage />}'],
    ['/scenario-library', 'path="/scenario-library" element={<ScenarioLibraryPage />}'],
    ['/scenario-science', 'path="/scenario-science" element={<ScenarioLibraryPage />}'],
  ]);
  for (const [route, marker] of routeMarkers) {
    const count = app.split(marker).length - 1;
    if (count === 0) errors.push(`scenario library route missing:${route}`);
    else if (count !== 1) errors.push(`scenario library route duplicated:${route}:${count}`);
  }
  for (const marker of ['Stakeholder capability map', 'Source-conformance scorecard', 'Treatment admission', 'Operational timing is not calibrated']) if (!page.includes(marker)) errors.push(`scenario library UI marker missing:${marker}`);
  const builder = readFileSync(safePath(root, 'scripts/buildScenarioStakeholderBundle.ts', 'builder'), 'utf8');
  for (const marker of ['buildScenarioSourceConformanceScorecard', 'concrete treatment unexpectedly simulation-admitted']) if (!builder.includes(marker)) errors.push(`stakeholder canonical writer marker missing:${marker}`);
  const scorecardSource = readFileSync(safePath(root, 'src/scenario-core/scorecard.ts', 'scorecard_source'), 'utf8');
  for (const marker of ['NONE_UNTIL_CALIBRATED_FOR_DECLARED_SCOPE', 'NOT_A_VALIDATED_PROFICIENCY_MEASURE', 'CRITICAL_FAILURE']) if (!scorecardSource.includes(marker)) errors.push(`scorecard boundary marker missing:${marker}`);
  const expected = expectedDashboard(capabilityMap, registry, science, contract, pack);
  if (canonical(dashboard) !== canonical(expected)) errors.push('stakeholder dashboard differs from independent reconstruction');
  const result = { schema_version: '1.0.0', classification: errors.length ? 'FAIL' : 'PASS', status: errors.length ? 'FAIL' : 'PASS', checker: 'INDEPENDENT_NODE_STDLIB_RECONSTRUCTION_V1', checks: errors.length ? 0 : 139, scenario_entries: 12, behavior_profiles: 4, admitted_treatments: admitted, errors };
  writeJson(safePath(root, args.jsonOutput, 'json_output'), result); console.log(JSON.stringify(result, null, 2));
} catch (error) {
  errors.push(error instanceof Error ? error.message : String(error)); console.log(JSON.stringify({ schema_version: '1.0.0', classification: 'FAIL', status: 'FAIL', checker: 'INDEPENDENT_NODE_STDLIB_RECONSTRUCTION_V1', errors }, null, 2));
}
process.exit(errors.length ? 3 : 0);
