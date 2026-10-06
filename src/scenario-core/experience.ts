import { scenariosById } from '../content/scenarios';
import { canonicalJson } from './hash';
import { protectedScenarioProjection } from './projection';
import { validateRouteGraph } from './route';
import type { ScenarioRouteGraph, VerifiedScenarioPackage } from './types';
import { validateScenarioPackage } from './validator';

export interface ScenarioExperienceIssue {
  code: string;
  path: string;
  message: string;
}

export interface ScenarioExperienceMetrics {
  route_nodes: number;
  route_edges: number;
  terminal_nodes: number;
  branching_nodes: number;
  maximum_route_steps: number;
  evidence_references: number;
  operational_factors: number;
  training_objectives: number;
  aar_teaching_points: number;
  expected_action_labels: number;
  successful_routes: number;
}

export interface ScenarioExperienceReport {
  schema_version: '1.0.0';
  classification: 'PASS' | 'FAIL';
  status: 'PASS' | 'FAIL';
  checks_run: number;
  issues: ScenarioExperienceIssue[];
  metrics: ScenarioExperienceMetrics;
  truth_boundaries: {
    clinical_authority: 'NOT_GRANTED';
    deployment_scope: 'research_sandbox_only';
    patient_care_use: 'PROHIBITED';
    operational_timing: 'NOT_CALIBRATED';
  };
}

function normalized(value: string): string {
  return value.trim().replace(/\s+/g, ' ').toLowerCase();
}

function uniqueNormalized(values: readonly string[]): boolean {
  const normalizedValues = values.map(normalized);
  return normalizedValues.every(Boolean) && new Set(normalizedValues).size === normalizedValues.length;
}

function pathToTerminal(route: ScenarioRouteGraph): { allReachTerminal: boolean; maximumSteps: number; cyclic: boolean } {
  const outgoing = new Map<string, string[]>();
  for (const edge of route.edges) {
    const group = outgoing.get(edge.from) ?? [];
    group.push(edge.to);
    outgoing.set(edge.from, group);
  }
  const terminals = new Set(route.nodes.filter((node) => node.terminal).map((node) => node.node_id));
  const memo = new Map<string, number | null>();
  const visiting = new Set<string>();
  let cyclic = false;

  const longest = (nodeId: string): number | null => {
    if (terminals.has(nodeId)) return 0;
    if (memo.has(nodeId)) return memo.get(nodeId) ?? null;
    if (visiting.has(nodeId)) {
      cyclic = true;
      return null;
    }
    visiting.add(nodeId);
    const destinations = outgoing.get(nodeId) ?? [];
    const lengths = destinations.map(longest);
    visiting.delete(nodeId);
    if (lengths.length === 0 || lengths.some((value) => value === null)) {
      memo.set(nodeId, null);
      return null;
    }
    const result = 1 + Math.max(...(lengths as number[]));
    memo.set(nodeId, result);
    return result;
  };

  const lengths = route.nodes.map((node) => longest(node.node_id));
  return {
    allReachTerminal: lengths.every((value) => value !== null),
    maximumSteps: Math.max(0, ...(lengths.filter((value): value is number => value !== null))),
    cyclic,
  };
}

export function validateScenarioExperience(generated: VerifiedScenarioPackage): ScenarioExperienceReport {
  const issues: ScenarioExperienceIssue[] = [];
  let checksRun = 0;
  const check = (condition: boolean, code: string, path: string, message: string): void => {
    checksRun += 1;
    if (!condition) issues.push({ code, path, message });
  };

  const packageReport = validateScenarioPackage(generated);
  checksRun += packageReport.checks_run;
  for (const item of packageReport.issues) {
    issues.push({ code: `package.${item.code}`, path: item.path, message: item.message });
  }

  const base = scenariosById[generated.build.source_scenario_id];
  check(Boolean(base), 'experience.source', 'build.source_scenario_id', 'The reviewed source template must be available.');
  if (base) {
    check(
      canonicalJson(protectedScenarioProjection(base)) === canonicalJson(protectedScenarioProjection(generated.scenario)),
      'experience.protected_projection',
      'scenario',
      'The protected clinical projection must remain byte-for-byte equivalent.',
    );
  }

  check(generated.authority.clinical_authority === 'NOT_GRANTED', 'experience.authority', 'authority.clinical_authority', 'Clinical authority must remain NOT_GRANTED.');
  check(generated.authority.deployment_scope === 'research_sandbox_only', 'experience.scope', 'authority.deployment_scope', 'Generated variants must remain inside the research sandbox.');
  check(generated.authority.evidence_authority === 'supporting_only', 'experience.evidence_scope', 'authority.evidence_authority', 'Evidence must remain supporting-only.');
  check(generated.authority.scoring_behavior === 'inherited_unchanged', 'experience.scoring_scope', 'authority.scoring_behavior', 'Scoring must remain inherited and unchanged.');

  const notice = normalized(generated.scenario.fictionalization_notice);
  check(notice.includes('operational details were varied for training'), 'experience.boundary_notice', 'scenario.fictionalization_notice', 'The variant notice must identify operational variation as training-only.');
  check(notice.includes('clinical scaffold was not changed'), 'experience.boundary_notice', 'scenario.fictionalization_notice', 'The variant notice must state that the clinical scaffold was not changed.');
  check(normalized(generated.scenario.title).includes('operational variant'), 'experience.title', 'scenario.title', 'The title must visibly identify the scenario as an operational variant.');

  const context = generated.scenario.operational_context;
  const resourceEvent = generated.atoms.find((atom) => atom.atom_kind === 'resource_event')?.value ?? '';
  const factorValues = [
    context.location_type,
    context.weather,
    context.visibility,
    context.comms_status,
    context.resource_status,
    resourceEvent,
  ];
  for (const [index, value] of factorValues.entries()) {
    check(normalized(value).length >= 3, 'experience.operational_factor', `scenario.operational_context.factor[${index}]`, 'Every operational factor must be present and human-readable.');
  }
  check(generated.blueprint.location_options.includes(context.location_type), 'experience.factor_scope', 'scenario.operational_context.location_type', 'Location must come from the reviewed finite pool.');
  check(generated.blueprint.weather_options.includes(context.weather), 'experience.factor_scope', 'scenario.operational_context.weather', 'Weather must come from the reviewed finite pool.');
  check(generated.blueprint.visibility_options.includes(context.visibility), 'experience.factor_scope', 'scenario.operational_context.visibility', 'Visibility must come from the reviewed finite pool.');
  check(generated.blueprint.communications_options.includes(context.comms_status), 'experience.factor_scope', 'scenario.operational_context.comms_status', 'Communications status must come from the reviewed finite pool.');
  check(generated.blueprint.resource_options.includes(context.resource_status), 'experience.factor_scope', 'scenario.operational_context.resource_status', 'Resource status must come from the reviewed finite pool.');
  check(generated.blueprint.resource_event_options.includes(resourceEvent), 'experience.factor_scope', 'atoms.resource_event', 'The facilitator event must come from the reviewed finite pool.');

  const narrative = normalized(context.narrative);
  for (const [path, value] of [
    ['location_type', context.location_type],
    ['weather', context.weather],
    ['visibility', context.visibility],
    ['comms_status', context.comms_status],
    ['resource_status', context.resource_status],
    ['resource_event', resourceEvent],
  ] as const) {
    check(narrative.includes(normalized(value)), 'experience.narrative_binding', `scenario.operational_context.${path}`, 'The operational narrative must name every selected factor.');
  }
  check(narrative.includes(normalized(generated.build.source_scenario_id)), 'experience.narrative_boundary', 'scenario.operational_context.narrative', 'The narrative must identify the inherited source template.');
  check(narrative.includes('inherited unchanged'), 'experience.narrative_boundary', 'scenario.operational_context.narrative', 'The narrative must state that protected behavior is inherited unchanged.');

  const routeResult = validateRouteGraph(generated.route);
  check(routeResult.valid, 'experience.route_contract', 'route', routeResult.issues.join(' '));
  check(routeResult.profile_requirements_preserved, 'experience.profile_requirements', 'route', 'Every successful route must preserve the selected teamwork profile requirements in the reviewed order.');
  check(routeResult.successful_route_count >= 2, 'experience.multiple_successful_routes', 'route.edges', 'The route must expose at least two terminating successful paths.');
  const terminalNodes = generated.route.nodes.filter((node) => node.terminal);
  check(terminalNodes.length === 1, 'experience.route_terminal_count', 'route.nodes', 'The route must have exactly one terminal node.');
  const outgoing = new Map<string, number>();
  for (const edge of generated.route.edges) outgoing.set(edge.from, (outgoing.get(edge.from) ?? 0) + 1);
  check(terminalNodes.every((node) => (outgoing.get(node.node_id) ?? 0) === 0), 'experience.route_terminal_outgoing', 'route.edges', 'Terminal nodes must not have outgoing edges.');
  check(generated.route.edges.every((edge) => edge.from !== edge.to), 'experience.route_self_loop', 'route.edges', 'The route must not contain self-loops.');
  check(new Set(generated.route.edges.map((edge) => edge.edge_id)).size === generated.route.edges.length, 'experience.route_edge_ids', 'route.edges', 'Route edge IDs must be unique.');
  check(uniqueNormalized(generated.route.nodes.map((node) => node.label)), 'experience.route_labels', 'route.nodes', 'Route labels must be non-empty and unique.');
  check(generated.route.nodes.every((node) => !node.label.includes('_') && normalized(node.label).split(' ').length >= 3), 'experience.route_labels', 'route.nodes', 'Route labels must be plain-language phrases rather than raw identifiers.');
  const requiredKinds: ReadonlySet<VerifiedScenarioPackage['route']['nodes'][number]['node_kind']> = new Set(['briefing', 'movement', 'observation', 'pressure', 'handoff', 'complete']);
  const observedKinds = new Set(generated.route.nodes.map((node) => node.node_kind));
  check([...requiredKinds].every((kind) => observedKinds.has(kind)), 'experience.route_shape', 'route.nodes', 'The route must include briefing, movement, observation, pressure, handoff, and completion.');
  const start = generated.route.nodes.find((node) => node.node_id === generated.route.start_node_id);
  check(start?.node_kind === 'briefing', 'experience.route_start', 'route.start_node_id', 'The route must begin with an operational brief.');
  check(terminalNodes[0]?.node_kind === 'complete', 'experience.route_completion', 'route.nodes', 'The single terminal node must be the completion step.');
  const pressure = generated.route.nodes.find((node) => node.node_kind === 'pressure');
  const handoff = generated.route.nodes.find((node) => node.node_kind === 'handoff');
  check(Boolean(pressure && generated.route.edges.some((edge) => edge.to === pressure.node_id && edge.trigger === 'facilitator_event')), 'experience.pressure_branch', 'route.edges', 'The route must include a facilitator-driven operational pressure branch.');
  check(Boolean(handoff && generated.route.edges.some((edge) => edge.to === handoff.node_id && edge.trigger === 'handoff_ready')), 'experience.handoff_branch', 'route.edges', 'The route must include a traceable handoff transition.');
  const branchingNodes = [...outgoing.values()].filter((count) => count > 1).length;
  check(branchingNodes >= 1, 'experience.meaningful_branch', 'route.edges', 'The route must expose at least one meaningful branch.');
  const termination = pathToTerminal(generated.route);
  check(termination.allReachTerminal, 'experience.route_liveness', 'route', 'Every admitted route path must reach completion.');
  check(!termination.cyclic, 'experience.route_cycle', 'route', 'The route must be acyclic so the learner cannot become trapped in a loop.');

  check(generated.scenario.training_objectives.length > 0 && uniqueNormalized(generated.scenario.training_objectives), 'experience.objectives', 'scenario.training_objectives', 'Training objectives must be present and unique.');
  check(generated.scenario.end_conditions.success.length > 0 && uniqueNormalized(generated.scenario.end_conditions.success), 'experience.success_conditions', 'scenario.end_conditions.success', 'Success conditions must be present and unique.');
  check(generated.scenario.end_conditions.failure.length > 0 && uniqueNormalized(generated.scenario.end_conditions.failure), 'experience.failure_conditions', 'scenario.end_conditions.failure', 'Failure conditions must be present and unique.');
  check(Number.isFinite(generated.scenario.end_conditions.timeout_minutes) && generated.scenario.end_conditions.timeout_minutes > 0, 'experience.timeout', 'scenario.end_conditions.timeout_minutes', 'The exercise timeout must be a positive finite value.');
  check(generated.scenario.aar_teaching_points.length > 0 && uniqueNormalized(generated.scenario.aar_teaching_points), 'experience.aar', 'scenario.aar_teaching_points', 'The AAR must contain distinct teaching points.');

  const actionLabels = [
    ...generated.scenario.expected_actions.critical,
    ...generated.scenario.expected_actions.important,
    ...generated.scenario.expected_actions.optional,
    ...generated.scenario.expected_actions.unsafe,
  ].map((action) => action.label);
  check(actionLabels.length > 0 && uniqueNormalized(actionLabels), 'experience.action_labels', 'scenario.expected_actions', 'Expected-action labels must be present and unique.');

  check(generated.evidence.length > 0, 'experience.evidence', 'evidence', 'At least one supporting citation is required.');
  for (const [index, citation] of generated.evidence.entries()) {
    check(normalized(citation.title).length >= 3, 'experience.evidence_label', `evidence[${index}].title`, 'Every citation needs a readable title.');
    check(normalized(citation.journal).length >= 2, 'experience.evidence_label', `evidence[${index}].journal`, 'Every citation needs a journal label.');
    check(/^10\.[^\s/]+\/.+/.test(citation.doi), 'experience.evidence_doi', `evidence[${index}].doi`, 'Every citation needs a DOI-shaped identifier.');
    check(normalized(citation.locator).length >= 2 || /^10\.[^\s/]+\/.+/.test(citation.doi), 'experience.evidence_locator', `evidence[${index}].locator`, 'Every citation needs a source locator or DOI-bound source identity.');
  }
  const evidenceIds = new Set(generated.evidence.map((citation) => citation.evidence_id));
  const supportingAtomEvidence = new Set(generated.atoms.filter((atom) => atom.authority === 'supporting_only').flatMap((atom) => atom.evidence_ids));
  check([...evidenceIds].every((id) => supportingAtomEvidence.has(id)), 'experience.evidence_trace', 'atoms', 'Every citation must be represented by a supporting-only atom.');

  const atomIds = new Set(generated.atoms.map((atom) => atom.atom_id));
  check(generated.field_origins.every((origin) => origin.atom_ids.every((id) => atomIds.has(id))), 'experience.origin_atoms', 'field_origins', 'Every field origin must reference an existing atom.');
  check(generated.field_origins.every((origin) => origin.evidence_ids.every((id) => evidenceIds.has(id))), 'experience.origin_evidence', 'field_origins', 'Every field-origin evidence reference must exist.');
  check(new Set(generated.field_origins.map((origin) => origin.field_path)).size === generated.field_origins.length, 'experience.origin_paths', 'field_origins', 'Field-origin paths must be unique.');

  const scenarioText = normalized([
    generated.scenario.title,
    generated.scenario.fictionalization_notice,
    generated.scenario.operational_context.narrative,
  ].join(' '));
  check(generated.evidence.every((citation) => !scenarioText.includes(normalized(citation.doi))), 'experience.evidence_non_authoring', 'scenario', 'Citation identifiers must not be copied into scenario prose.');
  check(generated.evidence.every((citation) => !scenarioText.includes(normalized(citation.evidence_id))), 'experience.evidence_non_authoring', 'scenario', 'Evidence IDs must not be copied into scenario prose.');

  const classification = issues.length === 0 ? 'PASS' : 'FAIL';
  return {
    schema_version: '1.0.0',
    classification,
    status: classification,
    checks_run: checksRun,
    issues,
    metrics: {
      route_nodes: generated.route.nodes.length,
      route_edges: generated.route.edges.length,
      terminal_nodes: terminalNodes.length,
      branching_nodes: branchingNodes,
      maximum_route_steps: termination.maximumSteps,
      evidence_references: generated.evidence.length,
      operational_factors: factorValues.length,
      training_objectives: generated.scenario.training_objectives.length,
      aar_teaching_points: generated.scenario.aar_teaching_points.length,
      expected_action_labels: actionLabels.length,
      successful_routes: routeResult.successful_route_count,
    },
    truth_boundaries: {
      clinical_authority: 'NOT_GRANTED',
      deployment_scope: 'research_sandbox_only',
      patient_care_use: 'PROHIBITED',
      operational_timing: 'NOT_CALIBRATED',
    },
  };
}

export function assertScenarioExperience(generated: VerifiedScenarioPackage): void {
  const report = validateScenarioExperience(generated);
  if (report.status === 'FAIL') {
    throw new Error(report.issues.map((item) => `${item.code}:${item.path}:${item.message}`).join('\n'));
  }
}
