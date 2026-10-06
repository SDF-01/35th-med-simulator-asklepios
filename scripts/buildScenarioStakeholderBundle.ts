import { lstatSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, resolve, sep } from 'node:path';
import { buildFieldRoute } from '../src/scenario-core/route';
import { buildScenarioSourceConformanceScorecard } from '../src/scenario-core/scorecard';
import type { ScenarioRunTrace } from '../src/scenario-core/scorecard';
import type { ScenarioOperationalBehaviorProfileId } from '../src/scenario-core/behaviorProfiles';
import { canonicalJson, sha256Canonical } from '../src/scenario-core/hash';

interface Args {
  repo: string;
  check: boolean;
  jsonOutput: string;
}

const PROFILES: readonly ScenarioOperationalBehaviorProfileId[] = [
  'DIRECT_HANDOFF_BASELINE',
  'COMMUNICATION_RELAY_REQUIRED',
  'RESOURCE_COORDINATION_REQUIRED',
  'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
];

function parseArgs(argv: string[]): Args {
  const result: Args = { repo: '.', check: false, jsonOutput: 'reports/stakeholder-product-bundle.json' };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (item === '--repo') result.repo = argv[++index] ?? '';
    else if (item === '--check') result.check = true;
    else if (item === '--json-output') result.jsonOutput = argv[++index] ?? '';
    else throw new Error(`unknown argument:${item}`);
  }
  return result;
}

function safeRepoPath(root: string, value: string, label: string): string {
  if (!value || value.includes('\0') || value.includes('\\') || isAbsolute(value)) throw new Error(`unsafe repository path:${label}`);
  const parts = value.split('/');
  if (parts.some((part) => !part || part === '.' || part === '..' || part.includes(':') || part.endsWith(' ') || part.endsWith('.'))) {
    throw new Error(`unsafe repository path:${label}`);
  }
  const candidate = resolve(root, ...parts);
  const prefix = root.endsWith(sep) ? root : `${root}${sep}`;
  if (candidate !== root && !candidate.startsWith(prefix)) throw new Error(`repository path escapes root:${label}`);
  let current = root;
  for (const part of parts.slice(0, -1)) {
    current = resolve(current, part);
    try {
      if (lstatSync(current).isSymbolicLink()) throw new Error(`symlinked repository parent rejected:${label}`);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    }
  }
  return candidate;
}

function readJson(path: string): Record<string, unknown> {
  const value = JSON.parse(readFileSync(path, 'utf8')) as unknown;
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`JSON object required:${path}`);
  return value as Record<string, unknown>;
}

function writeJsonAtomic(path: string, value: unknown): void {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.tmp-${process.pid}`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  renameSync(temporary, path);
}

function verifySelfHash(value: Record<string, unknown>, field: string, label: string): void {
  const observed = value[field];
  if (typeof observed !== 'string' || !/^[0-9a-f]{64}$/.test(observed)) throw new Error(`${label} self hash is invalid`);
  const body = { ...value };
  delete body[field];
  if (observed !== sha256Canonical(body)) throw new Error(`${label} self hash differs`);
}

function traceFor(profile: ScenarioOperationalBehaviorProfileId, routeId: string): ScenarioRunTrace {
  const route = buildFieldRoute(routeId, profile);
  const nodes = ['briefing', 'approach', 'contact', 'pressure'];
  if (profile === 'COMMUNICATION_RELAY_REQUIRED' || profile === 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION') nodes.push('communications-relay');
  if (profile === 'RESOURCE_COORDINATION_REQUIRED' || profile === 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION') nodes.push('resource-coordination');
  nodes.push('handoff', 'complete');
  const edgeByTransition = new Map(route.edges.map((edge) => [`${edge.from}->${edge.to}`, edge.edge_id]));
  const edges = nodes.slice(1).map((node, index) => {
    const edge = edgeByTransition.get(`${nodes[index]}->${node}`);
    if (!edge) throw new Error(`reference scorecard route edge missing:${profile}:${nodes[index]}:${node}`);
    return edge;
  });
  return {
    schema_version: '1.0.0',
    route_id: route.route_id,
    operational_behavior_profile_id: profile,
    visited_node_ids: nodes,
    traversed_edge_ids: edges,
    safety_event_ids: [],
    terminal_reached: true,
  };
}

function buildDashboard(root: string): Record<string, unknown> {
  const operationalPack = readJson(safeRepoPath(root, 'public/data/scenario_library/operational-pack.json', 'operational_pack'));
  const capabilityMap = readJson(safeRepoPath(root, 'config/product/STAKEHOLDER_CAPABILITY_MAP.json', 'capability_map'));
  const treatmentRegistry = readJson(safeRepoPath(root, 'config/scenario-science/TREATMENT_ADMISSION_REGISTRY.json', 'treatment_registry'));
  const sciencePolicy = readJson(safeRepoPath(root, 'config/scenario-science/SCENARIO_SCIENCE_POLICY.json', 'science_policy'));
  const plainContract = readJson(safeRepoPath(root, 'config/product/PLAIN_LANGUAGE_RELEASE_CONTRACT.json', 'plain_language_contract'));
  verifySelfHash(capabilityMap, 'map_sha256', 'stakeholder capability map');
  verifySelfHash(treatmentRegistry, 'registry_sha256', 'treatment admission registry');
  verifySelfHash(sciencePolicy, 'policy_sha256', 'scenario science policy');
  verifySelfHash(plainContract, 'contract_sha256', 'plain language release contract');
  if (operationalPack.classification !== 'PASS' || operationalPack.status !== 'PASS') throw new Error('operational scenario pack is not passing');
  if (operationalPack.entry_count !== 12) throw new Error('operational scenario pack must contain twelve entries');
  if (!Array.isArray(capabilityMap.capabilities) || capabilityMap.capabilities.length < 9) throw new Error('stakeholder capability map is incomplete');
  if (!Array.isArray(treatmentRegistry.entries)) throw new Error('treatment admission registry entries missing');
  const admitted = treatmentRegistry.entries.filter((entry) => (
    Boolean(entry) && typeof entry === 'object' && (entry as Record<string, unknown>).simulation_admitted === true
  ));
  if (admitted.length !== 0) throw new Error('concrete treatment unexpectedly simulation-admitted');

  const referenceScorecards = PROFILES.map((profile) => {
    const route = buildFieldRoute('ASK-STAKEHOLDER-REFERENCE', profile);
    return buildScenarioSourceConformanceScorecard(route, traceFor(profile, 'ASK-STAKEHOLDER-REFERENCE'));
  });
  const withoutHash = {
    schema_version: '1.0.0',
    classification: 'PASS',
    status: 'PASS',
    dashboard_id: 'ASK-STAKEHOLDER-DASHBOARD-RC3-8',
    dashboard_profile: 'SCENARIO_LIBRARY_SCORECARD_TREATMENT_AND_EVIDENCE_SURFACE_V1',
    scenario_pack: operationalPack,
    stakeholder_capability_map: {
      map_id: capabilityMap.map_id,
      map_epoch: capabilityMap.map_epoch,
      map_sha256: capabilityMap.map_sha256,
      capabilities: capabilityMap.capabilities,
    },
    reference_scorecards: referenceScorecards,
    treatment_admission: {
      registry_id: treatmentRegistry.registry_id,
      registry_epoch: treatmentRegistry.registry_epoch,
      registry_sha256: treatmentRegistry.registry_sha256,
      state_order: treatmentRegistry.state_order,
      entries: treatmentRegistry.entries,
      admitted_treatment_count: admitted.length,
    },
    scenario_science_readiness: {
      policy_id: sciencePolicy.policy_id,
      policy_epoch: sciencePolicy.policy_epoch,
      policy_sha256: sciencePolicy.policy_sha256,
      telemetry_profile: sciencePolicy.telemetry_profile,
      evidence_state_order: sciencePolicy.evidence_state_order,
      calibration_state_order: sciencePolicy.calibration_state_order,
      scoring_state_order: sciencePolicy.scoring_state_order,
      current_operational_timing: (sciencePolicy.timing_scoring_boundary as Record<string, unknown>).current_operational_timing,
      current_scoring_state: (sciencePolicy.scoring_boundary as Record<string, unknown>).current_scoring_state,
    },
    plain_language_release: {
      contract_id: plainContract.contract_id,
      contract_epoch: plainContract.contract_epoch,
      contract_sha256: plainContract.contract_sha256,
      summary_path: plainContract.summary_path,
      required_headings: plainContract.required_headings,
    },
    truth_boundaries: {
      healthcare_simulation: 'PERMITTED_WITHIN_VALIDATED_SCOPE',
      direct_patient_care: 'PROHIBITED',
      clinical_decision_support: 'PROHIBITED',
      patient_care_authority: 'NONE',
      operational_timing: 'NOT_CALIBRATED',
      scoring_validity: 'SOURCE_CONFORMANCE_ONLY_NOT_PSYCHOMETRICALLY_VALIDATED',
      concrete_treatments_admitted: 0,
    },
  };
  return { ...withoutHash, dashboard_root_sha256: sha256Canonical(withoutHash) };
}

let errors: string[] = [];
try {
  const args = parseArgs(process.argv.slice(2));
  const root = resolve(args.repo);
  const dashboard = buildDashboard(root);
  const output = safeRepoPath(root, 'public/data/scenario_library/stakeholder-dashboard.json', 'dashboard_output');
  const reportPath = safeRepoPath(root, args.jsonOutput, 'json_output');
  const mismatches: string[] = [];
  if (args.check) {
    try {
      const observed = readJson(output);
      if (canonicalJson(observed) !== canonicalJson(dashboard)) mismatches.push('public/data/scenario_library/stakeholder-dashboard.json');
    } catch {
      mismatches.push('public/data/scenario_library/stakeholder-dashboard.json');
    }
  } else {
    writeJsonAtomic(output, dashboard);
  }
  const result = {
    schema_version: '1.0.0',
    classification: mismatches.length ? 'FAIL' : 'PASS',
    status: mismatches.length ? 'FAIL' : 'PASS',
    mode: args.check ? 'check' : 'write',
    dashboard_id: dashboard.dashboard_id,
    dashboard_root_sha256: dashboard.dashboard_root_sha256,
    scenario_entries: (dashboard.scenario_pack as Record<string, unknown>).entry_count,
    capability_count: ((dashboard.stakeholder_capability_map as Record<string, unknown>).capabilities as unknown[]).length,
    reference_scorecards: (dashboard.reference_scorecards as unknown[]).length,
    admitted_treatments: (dashboard.treatment_admission as Record<string, unknown>).admitted_treatment_count,
    mismatches,
    errors: [],
  };
  writeJsonAtomic(reportPath, result);
  console.log(JSON.stringify(result, null, 2));
  if (mismatches.length) process.exitCode = 3;
} catch (error) {
  errors = [error instanceof Error ? error.message : String(error)];
  console.log(JSON.stringify({ schema_version: '1.0.0', classification: 'FAIL', status: 'FAIL', errors }, null, 2));
  process.exitCode = 3;
}
