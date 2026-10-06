import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { ResearchRuntimeBridge } from '../src/research/types';
import { buildTemplateLockedScenario, validateScenarioExperience } from '../src/scenario-core/index';
import type { VerifiedScenarioPackage } from '../src/scenario-core/index';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const bridge = JSON.parse(
  await readFile(resolve(root, 'public/data/research_sandbox/runtime_bridge.json'), 'utf8'),
) as ResearchRuntimeBridge;
const baseline = buildTemplateLockedScenario(bridge, {
  topic_id: 'massive_hemorrhage',
  seed: 41027,
  retriever_track: bridge.retrieval_release.default_research_sandbox_retriever,
});

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

interface Attack {
  case_id: string;
  required_code: string;
  mutate: (value: VerifiedScenarioPackage) => void;
}

const attacks: Attack[] = [
  { case_id: 'blank_route_label', required_code: 'experience.route_labels', mutate: (value) => { value.route.nodes[1]!.label = ' '; } },
  { case_id: 'raw_identifier_route_label', required_code: 'experience.route_labels', mutate: (value) => { value.route.nodes[1]!.label = 'move_to_location'; } },
  { case_id: 'route_dead_end', required_code: 'experience.route_contract', mutate: (value) => { value.route.edges = value.route.edges.filter((edge) => edge.from !== 'pressure'); } },
  { case_id: 'terminal_outgoing_edge', required_code: 'experience.route_terminal_outgoing', mutate: (value) => { value.route.edges.push({ edge_id: 'terminal-loop', from: 'complete', to: 'briefing', trigger: 'start', priority: 1 }); } },
  { case_id: 'multiple_terminal_nodes', required_code: 'experience.route_terminal_count', mutate: (value) => { value.route.nodes[4]!.terminal = true; } },
  { case_id: 'route_cycle', required_code: 'experience.route_cycle', mutate: (value) => { value.route.edges.push({ edge_id: 'cycle', from: 'pressure', to: 'contact', trigger: 'facilitator_event', priority: 1 }); } },
  { case_id: 'training_boundary_removed', required_code: 'experience.boundary_notice', mutate: (value) => { value.scenario.fictionalization_notice = 'Fictional scenario.'; } },
  { case_id: 'narrative_factor_removed', required_code: 'experience.narrative_binding', mutate: (value) => { value.scenario.operational_context.narrative = value.scenario.operational_context.narrative.replace(value.scenario.operational_context.weather, 'conditions withheld'); } },
  { case_id: 'aar_removed', required_code: 'experience.aar', mutate: (value) => { value.scenario.aar_teaching_points = []; } },
  { case_id: 'authority_promoted', required_code: 'package.authority', mutate: (value) => { (value.authority as { clinical_authority: string }).clinical_authority = 'GRANTED'; } },
  { case_id: 'citation_title_removed', required_code: 'experience.evidence_label', mutate: (value) => { value.evidence[0]!.title = ''; } },
  { case_id: 'protected_action_changed', required_code: 'package.protected', mutate: (value) => { value.scenario.expected_actions.critical[0]!.points += 1; } },
  { case_id: 'origin_atom_missing', required_code: 'experience.origin_atoms', mutate: (value) => { value.field_origins[0]!.atom_ids = ['missing-atom']; } },
  { case_id: 'resource_event_outside_reviewed_pool', required_code: 'experience.factor_scope', mutate: (value) => { value.atoms.find((atom) => atom.atom_kind === 'resource_event')!.value = 'unreviewed event'; } },
  { case_id: 'meaningful_branch_removed', required_code: 'experience.meaningful_branch', mutate: (value) => { value.route.edges = value.route.edges.filter((edge) => !(edge.from === 'contact' && edge.trigger === 'handoff_ready')); } },
  { case_id: 'profile_requirement_bypassed', required_code: 'experience.profile_requirements', mutate: (value) => { const edge = value.route.edges.find((item) => item.from === 'contact' && item.trigger === 'handoff_ready'); if (!edge) throw new Error('alternate branch missing'); edge.to = 'handoff'; } },
  { case_id: 'profile_requirement_relabelled', required_code: 'experience.profile_requirements', mutate: (value) => { value.route.route_id = value.route.route_id.replace(/:[^:]+$/, ':DIRECT_HANDOFF_BASELINE'); } },
  { case_id: 'variant_identity_removed', required_code: 'experience.title', mutate: (value) => { value.scenario.title = 'Scenario'; } },
];

const baselineReport = validateScenarioExperience(baseline);
if (baselineReport.status !== 'PASS') {
  throw new Error(`Baseline experience is invalid: ${JSON.stringify(baselineReport.issues)}`);
}

const results = attacks.map((attack) => {
  const candidate = clone(baseline);
  attack.mutate(candidate);
  const report = validateScenarioExperience(candidate);
  const observedCodes = [...new Set(report.issues.map((item) => item.code))].sort();
  const exactDiagnosticObserved = observedCodes.includes(attack.required_code);
  const pass = report.status === 'FAIL' && exactDiagnosticObserved;
  return {
    case_id: attack.case_id,
    classification: pass ? 'EXPECTED_REJECTION' : 'FAIL',
    pass,
    required_code: attack.required_code,
    observed_status: report.status,
    observed_codes: observedCodes,
  };
});

const failures = results.filter((item) => !item.pass);
const classification = failures.length === 0 ? 'PASS' : 'FAIL';
const report = {
  schema_version: '1.0.0',
  classification,
  status: classification,
  cases: results.length + 1,
  baseline: {
    classification: baselineReport.status,
    checks_run: baselineReport.checks_run,
    pass: baselineReport.status === 'PASS',
  },
  attacks: results,
  failures: failures.map((item) => item.case_id),
};

const output = resolve(root, 'reports/scenario-experience-mutations.json');
await mkdir(dirname(output), { recursive: true });
await writeFile(output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(report, null, 2));
if (classification !== 'PASS') process.exitCode = 3;
