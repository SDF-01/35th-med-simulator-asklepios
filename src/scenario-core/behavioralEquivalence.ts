import { canonicalJson, sha256Canonical } from './hash';
import { protectedScenarioProjection } from './projection';
import type { ScenarioOperationalBehaviorProfileId } from './behaviorProfiles';
import type {
  ScenarioRouteGraph,
  ScenarioRouteNode,
  VerifiedScenarioPackage,
} from './types';

export const SCENARIO_BEHAVIORAL_POLICY_PROFILE = 'SOURCE_BOUND_POLICY_AND_TRAJECTORY_QUOTIENT_V1' as const;
export const SCENARIO_CONTEXT_SIGNATURE_PROFILE = 'REVIEWED_OPERATIONAL_CONTEXT_SIGNATURE_V1' as const;
export const SCENARIO_ROUTE_QUOTIENT_PROFILE = 'ROOTED_LABELLED_DAG_ID_AND_PROSE_INVARIANT_V1' as const;
export const SCENARIO_BEHAVIORAL_EQUIVALENCE_ARCHIVE_PROFILE = 'DETERMINISTIC_BEHAVIORAL_EQUIVALENCE_ARCHIVE_V1' as const;
export const SCENARIO_BEHAVIORAL_NOVELTY_BOUNDARY = 'POLICY_DIVERSITY_MEASUREMENT_ONLY_NOT_REAL_WORLD_CALIBRATION' as const;

export type BehavioralUniquenessStatus =
  | 'CONTEXT_DIVERSITY_ONLY_POLICY_DIVERSITY_NOT_ESTABLISHED'
  | 'MIXED_CONTEXT_AND_POLICY_DIVERSITY'
  | 'EVERY_CANDIDATE_POLICY_DISTINCT';

interface CanonicalRouteEdge {
  trigger: string;
  priority: number;
  destination: CanonicalRouteNode;
}

interface CanonicalRouteNode {
  node_kind: ScenarioRouteNode['node_kind'];
  operational_semantic: NonNullable<ScenarioRouteNode['operational_semantic']>;
  terminal: boolean;
  outgoing: CanonicalRouteEdge[];
}

export interface ScenarioBehavioralPolicyDescriptor {
  schema_version: '1.0.0';
  descriptor_profile: typeof SCENARIO_BEHAVIORAL_POLICY_PROFILE;
  route_quotient_profile: typeof SCENARIO_ROUTE_QUOTIENT_PROFILE;
  source_scenario_id: string;
  protected_scenario_sha256: string;
  route_policy_sha256: string;
  action_policy_sha256: string;
  information_policy_sha256: string;
  terminal_policy_sha256: string;
  route_metrics: {
    nodes: number;
    edges: number;
    terminal_nodes: number;
    branching_nodes: number;
    maximum_route_steps: number;
    successful_route_count: number;
  };
  action_metrics: {
    critical: number;
    important: number;
    optional: number;
    unsafe: number;
    total: number;
  };
  information_metrics: {
    patients: number;
    hidden_findings: number;
    deterioration_events: number;
    structured_vital_fields: number;
  };
}

export interface ScenarioOperationalContextSignature {
  schema_version: '1.0.0';
  signature_profile: typeof SCENARIO_CONTEXT_SIGNATURE_PROFILE;
  topic_id: string;
  location: string;
  weather: string;
  visibility: string;
  communications: string;
  resources: string;
  resource_event: string;
}

export interface ScenarioBehavioralEquivalenceCandidate {
  candidate_id: string;
  package_sha256: string;
  source_scenario_id: string;
  topic_id: string;
  seed: number;
  operational_behavior_profile_id: ScenarioOperationalBehaviorProfileId;
  context_signature_sha256: string;
  policy_signature_sha256: string;
  equivalence_class_id: string;
  context_signature: ScenarioOperationalContextSignature;
  policy_descriptor: ScenarioBehavioralPolicyDescriptor;
}

export interface ScenarioBehavioralEquivalenceClass {
  equivalence_class_id: string;
  policy_signature_sha256: string;
  representative_candidate_id: string;
  operational_behavior_profile_id: ScenarioOperationalBehaviorProfileId;
  candidate_ids: string[];
  context_signature_count: number;
}

export interface ScenarioBehavioralEquivalenceArchive {
  schema_version: '1.0.0';
  classification: 'PASS';
  status: 'PASS';
  archive_profile: typeof SCENARIO_BEHAVIORAL_EQUIVALENCE_ARCHIVE_PROFILE;
  policy_profile: typeof SCENARIO_BEHAVIORAL_POLICY_PROFILE;
  context_profile: typeof SCENARIO_CONTEXT_SIGNATURE_PROFILE;
  novelty_boundary: typeof SCENARIO_BEHAVIORAL_NOVELTY_BOUNDARY;
  candidates: ScenarioBehavioralEquivalenceCandidate[];
  equivalence_classes: ScenarioBehavioralEquivalenceClass[];
  summary: {
    candidate_count: number;
    unique_context_signatures: number;
    unique_policy_signatures: number;
    operational_behavior_profiles_observed: ScenarioOperationalBehaviorProfileId[];
    policy_equivalence_classes: number;
    context_only_variant_count: number;
    policy_novelty_ratio_bps: number;
    maximum_contexts_in_one_policy_class: number;
    minimum_contexts_in_one_policy_class: number;
    behavioral_uniqueness_status: BehavioralUniquenessStatus;
    narrative_or_provenance_only_changes_create_policy_novelty: false;
    operational_context_change_without_policy_change_counts_as_policy_novelty: false;
  };
  truth_boundaries: {
    clinical_authority: 'NOT_GRANTED';
    patient_care_use: 'PROHIBITED';
    human_team_behavior: 'STRUCTURAL_ONLY_NOT_CALIBRATED';
    operational_timing: 'NOT_CALIBRATED';
    empirical_behavioral_validity: 'NOT_ESTABLISHED';
    scoring_behavior: 'inherited_unchanged';
  };
  archive_root_sha256: string;
}

function assertInvariant(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function requireSafeNonnegativeInteger(value: number, label: string): void {
  assertInvariant(Number.isSafeInteger(value) && value >= 0, `${label} must be a nonnegative safe integer.`);
}

function normalizedText(value: string): string {
  return value.trim().replace(/\s+/g, ' ');
}

function canonicalRoute(route: ScenarioRouteGraph): {
  root: CanonicalRouteNode;
  metrics: ScenarioBehavioralPolicyDescriptor['route_metrics'];
} {
  const nodes = new Map(route.nodes.map((node) => [node.node_id, node] as const));
  assertInvariant(nodes.size === route.nodes.length, 'Route node IDs must be unique.');
  assertInvariant(nodes.has(route.start_node_id), 'Route start node is missing.');
  const edgeIds = route.edges.map((edge) => edge.edge_id);
  assertInvariant(new Set(edgeIds).size === edgeIds.length, 'Route edge IDs must be unique.');

  const outgoing = new Map<string, typeof route.edges>();
  for (const nodeId of nodes.keys()) outgoing.set(nodeId, []);
  for (const edge of route.edges) {
    assertInvariant(nodes.has(edge.from), `Route edge ${edge.edge_id} has an unknown source.`);
    assertInvariant(nodes.has(edge.to), `Route edge ${edge.edge_id} has an unknown destination.`);
    assertInvariant(edge.from !== edge.to, `Route edge ${edge.edge_id} is a self-loop.`);
    assertInvariant(Number.isSafeInteger(edge.priority), `Route edge ${edge.edge_id} priority is not a safe integer.`);
    outgoing.get(edge.from)!.push(edge);
  }

  const reachable = new Set<string>();
  const reachStack = [route.start_node_id];
  while (reachStack.length > 0) {
    const current = reachStack.pop()!;
    if (reachable.has(current)) continue;
    reachable.add(current);
    for (const edge of outgoing.get(current) ?? []) reachStack.push(edge.to);
  }
  assertInvariant(reachable.size === nodes.size, 'Route contains an unreachable node.');

  const visiting = new Set<string>();
  const memo = new Map<string, { node: CanonicalRouteNode; longest: number; routes: number }>();
  const visit = (nodeId: string): { node: CanonicalRouteNode; longest: number; routes: number } => {
    const cached = memo.get(nodeId);
    if (cached) return cached;
    assertInvariant(!visiting.has(nodeId), 'Route contains a cycle.');
    visiting.add(nodeId);
    const source = nodes.get(nodeId)!;
    const edges = outgoing.get(nodeId) ?? [];
    if (source.terminal) assertInvariant(edges.length === 0, `Terminal node ${nodeId} has an outgoing edge.`);
    else assertInvariant(edges.length > 0, `Reachable node ${nodeId} is a nonterminal dead end.`);

    const children = edges.map((edge) => {
      const child = visit(edge.to);
      return {
        trigger: edge.trigger,
        priority: edge.priority,
        destination: child.node,
        longest: child.longest,
        routes: child.routes,
      };
    }).sort((left, right) => canonicalJson({
      trigger: left.trigger,
      priority: left.priority,
      destination: left.destination,
    }).localeCompare(canonicalJson({
      trigger: right.trigger,
      priority: right.priority,
      destination: right.destination,
    })));

    const defaultSemantic = ((): NonNullable<ScenarioRouteNode['operational_semantic']> => {
      switch (source.node_kind) {
        case 'briefing': return 'orientation';
        case 'movement': return 'movement';
        case 'observation': return 'scene_observation';
        case 'pressure': return 'operational_pressure';
        case 'handoff': return 'closed_loop_handoff';
        case 'complete': return 'completion';
      }
    })();
    const node: CanonicalRouteNode = {
      node_kind: source.node_kind,
      operational_semantic: source.operational_semantic ?? defaultSemantic,
      terminal: source.terminal,
      outgoing: children.map(({ trigger, priority, destination }) => ({ trigger, priority, destination })),
    };
    const result = {
      node,
      longest: source.terminal ? 0 : 1 + Math.max(...children.map((item) => item.longest)),
      routes: source.terminal ? 1 : children.reduce((total, item) => total + item.routes, 0),
    };
    requireSafeNonnegativeInteger(result.longest, 'route longest path');
    requireSafeNonnegativeInteger(result.routes, 'route path count');
    visiting.delete(nodeId);
    memo.set(nodeId, result);
    return result;
  };

  const start = visit(route.start_node_id);
  const branchingNodes = [...outgoing.values()].filter((edges) => edges.length > 1).length;
  return {
    root: start.node,
    metrics: {
      nodes: route.nodes.length,
      edges: route.edges.length,
      terminal_nodes: route.nodes.filter((node) => node.terminal).length,
      branching_nodes: branchingNodes,
      maximum_route_steps: start.longest,
      successful_route_count: start.routes,
    },
  };
}

function actionPolicyProjection(generated: VerifiedScenarioPackage): object {
  const groups = generated.scenario.expected_actions;
  return (['critical', 'important', 'optional', 'unsafe'] as const).flatMap((priority) => (
    groups[priority].map((action) => ({
      action_id: action.id,
      priority,
      declared_priority: action.priority,
      points: action.points,
      march_step: action.marchStep ?? null,
    }))
  )).sort((left, right) => canonicalJson(left).localeCompare(canonicalJson(right)));
}

function informationPolicyProjection(generated: VerifiedScenarioPackage): object {
  return generated.scenario.patients.map((patient) => ({
    age_band: normalizedText(patient.age_band),
    sex: normalizedText(patient.sex),
    role_context: normalizedText(patient.role_context),
    injury_profile_refs: [...patient.injury_profile_refs].sort(),
    initial_vitals: { ...patient.initial_vitals },
    hidden_findings: [...patient.hidden_findings].sort(),
    deterioration_timeline: [...patient.deterioration_timeline],
    visible_body_zones: [...(patient.visible_body_zones ?? [])].sort((left, right) => canonicalJson(left).localeCompare(canonicalJson(right))),
  })).sort((left, right) => canonicalJson(left).localeCompare(canonicalJson(right)));
}

function terminalPolicyProjection(generated: VerifiedScenarioPackage): object {
  const conditions = generated.scenario.end_conditions;
  return {
    success: [...conditions.success].map(normalizedText).sort(),
    failure: [...conditions.failure].map(normalizedText).sort(),
    timeout_minutes: conditions.timeout_minutes,
  };
}

export function buildScenarioBehavioralPolicyDescriptor(
  generated: VerifiedScenarioPackage,
): ScenarioBehavioralPolicyDescriptor {
  assertInvariant(generated.authority.clinical_authority === 'NOT_GRANTED', 'Generated scenario clinical authority was promoted.');
  assertInvariant(generated.authority.scoring_behavior === 'inherited_unchanged', 'Generated scenario scoring behavior changed.');
  const route = canonicalRoute(generated.route);
  const actions = actionPolicyProjection(generated);
  const information = informationPolicyProjection(generated);
  const terminal = terminalPolicyProjection(generated);
  const actionMetrics = {
    critical: generated.scenario.expected_actions.critical.length,
    important: generated.scenario.expected_actions.important.length,
    optional: generated.scenario.expected_actions.optional.length,
    unsafe: generated.scenario.expected_actions.unsafe.length,
    total: 0,
  };
  actionMetrics.total = actionMetrics.critical + actionMetrics.important + actionMetrics.optional + actionMetrics.unsafe;
  const informationMetrics = {
    patients: generated.scenario.patients.length,
    hidden_findings: generated.scenario.patients.reduce((total, patient) => total + patient.hidden_findings.length, 0),
    deterioration_events: generated.scenario.patients.reduce((total, patient) => total + patient.deterioration_timeline.length, 0),
    structured_vital_fields: generated.scenario.patients.reduce((total, patient) => total + Object.keys(patient.initial_vitals).length, 0),
  };
  Object.entries({ ...route.metrics, ...actionMetrics, ...informationMetrics }).forEach(([key, value]) => {
    requireSafeNonnegativeInteger(value, key);
  });
  return {
    schema_version: '1.0.0',
    descriptor_profile: SCENARIO_BEHAVIORAL_POLICY_PROFILE,
    route_quotient_profile: SCENARIO_ROUTE_QUOTIENT_PROFILE,
    source_scenario_id: generated.build.source_scenario_id,
    protected_scenario_sha256: sha256Canonical(protectedScenarioProjection(generated.scenario)),
    route_policy_sha256: sha256Canonical(route.root),
    action_policy_sha256: sha256Canonical(actions),
    information_policy_sha256: sha256Canonical(information),
    terminal_policy_sha256: sha256Canonical(terminal),
    route_metrics: route.metrics,
    action_metrics: actionMetrics,
    information_metrics: informationMetrics,
  };
}

export function scenarioBehavioralPolicySignature(descriptor: ScenarioBehavioralPolicyDescriptor): string {
  return sha256Canonical(descriptor);
}

export function buildScenarioOperationalContextSignature(
  generated: VerifiedScenarioPackage,
): ScenarioOperationalContextSignature {
  const event = generated.atoms.find((atom) => atom.atom_kind === 'resource_event')?.value ?? '';
  assertInvariant(Boolean(event.trim()), 'Scenario context signature requires a resource event.');
  const context = generated.scenario.operational_context;
  return {
    schema_version: '1.0.0',
    signature_profile: SCENARIO_CONTEXT_SIGNATURE_PROFILE,
    topic_id: generated.build.topic_id,
    location: context.location_type,
    weather: context.weather,
    visibility: context.visibility,
    communications: context.comms_status,
    resources: context.resource_status,
    resource_event: event,
  };
}

export function scenarioOperationalContextSignature(value: ScenarioOperationalContextSignature): string {
  return sha256Canonical(value);
}

function uniquenessStatus(candidateCount: number, classCount: number): BehavioralUniquenessStatus {
  if (classCount === 1 && candidateCount > 1) return 'CONTEXT_DIVERSITY_ONLY_POLICY_DIVERSITY_NOT_ESTABLISHED';
  if (classCount === candidateCount) return 'EVERY_CANDIDATE_POLICY_DISTINCT';
  return 'MIXED_CONTEXT_AND_POLICY_DIVERSITY';
}

function routeOperationalBehaviorProfileId(route: ScenarioRouteGraph): ScenarioOperationalBehaviorProfileId {
  const suffix = route.route_id.split(':').at(-1);
  const admitted: readonly ScenarioOperationalBehaviorProfileId[] = [
    'DIRECT_HANDOFF_BASELINE',
    'COMMUNICATION_RELAY_REQUIRED',
    'RESOURCE_COORDINATION_REQUIRED',
    'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
  ];
  assertInvariant(admitted.includes(suffix as ScenarioOperationalBehaviorProfileId), 'Scenario route lacks a reviewed operational behavior profile.');
  return suffix as ScenarioOperationalBehaviorProfileId;
}

export function buildScenarioBehavioralEquivalenceArchive(
  generatedPackages: readonly VerifiedScenarioPackage[],
): ScenarioBehavioralEquivalenceArchive {
  assertInvariant(generatedPackages.length > 0, 'Behavioral equivalence archive requires at least one scenario.');
  const packageHashes = generatedPackages.map((generated) => generated.certificate.package_sha256);
  assertInvariant(packageHashes.every((value) => /^[0-9a-f]{64}$/.test(value)), 'Scenario package hash is malformed.');
  assertInvariant(new Set(packageHashes).size === packageHashes.length, 'Behavioral equivalence archive contains duplicate package identities.');

  const candidates = generatedPackages.map((generated): ScenarioBehavioralEquivalenceCandidate => {
    const policyDescriptor = buildScenarioBehavioralPolicyDescriptor(generated);
    const policySignature = scenarioBehavioralPolicySignature(policyDescriptor);
    const contextSignature = buildScenarioOperationalContextSignature(generated);
    const contextHash = scenarioOperationalContextSignature(contextSignature);
    const packageHash = generated.certificate.package_sha256;
    return {
      candidate_id: `ASK-BEQ-CAND-${packageHash.slice(0, 16).toUpperCase()}`,
      package_sha256: packageHash,
      source_scenario_id: generated.build.source_scenario_id,
      topic_id: generated.build.topic_id,
      seed: generated.build.seed,
      operational_behavior_profile_id: routeOperationalBehaviorProfileId(generated.route),
      context_signature_sha256: contextHash,
      policy_signature_sha256: policySignature,
      equivalence_class_id: `ASK-BEQ-CLASS-${policySignature.slice(0, 16).toUpperCase()}`,
      context_signature: contextSignature,
      policy_descriptor: policyDescriptor,
    };
  }).sort((left, right) => left.candidate_id.localeCompare(right.candidate_id));

  const grouped = new Map<string, ScenarioBehavioralEquivalenceCandidate[]>();
  for (const candidate of candidates) {
    const group = grouped.get(candidate.equivalence_class_id) ?? [];
    group.push(candidate);
    grouped.set(candidate.equivalence_class_id, group);
  }
  const equivalenceClasses = [...grouped.entries()].map(([classId, group]): ScenarioBehavioralEquivalenceClass => {
    group.sort((left, right) => left.candidate_id.localeCompare(right.candidate_id));
    const policy = group[0]!.policy_signature_sha256;
    const behaviorProfile = group[0]!.operational_behavior_profile_id;
    assertInvariant(group.every((candidate) => candidate.policy_signature_sha256 === policy), `Behavioral equivalence class ${classId} contains different policies.`);
    assertInvariant(group.every((candidate) => candidate.operational_behavior_profile_id === behaviorProfile), `Behavioral equivalence class ${classId} collapses reviewed operational profiles.`);
    return {
      equivalence_class_id: classId,
      policy_signature_sha256: policy,
      representative_candidate_id: group[0]!.candidate_id,
      operational_behavior_profile_id: behaviorProfile,
      candidate_ids: group.map((candidate) => candidate.candidate_id),
      context_signature_count: new Set(group.map((candidate) => candidate.context_signature_sha256)).size,
    };
  }).sort((left, right) => left.equivalence_class_id.localeCompare(right.equivalence_class_id));

  const contextCount = new Set(candidates.map((candidate) => candidate.context_signature_sha256)).size;
  const policyCount = equivalenceClasses.length;
  const contextsPerClass = equivalenceClasses.map((item) => item.context_signature_count);
  const withoutRoot: Omit<ScenarioBehavioralEquivalenceArchive, 'archive_root_sha256'> = {
    schema_version: '1.0.0',
    classification: 'PASS',
    status: 'PASS',
    archive_profile: SCENARIO_BEHAVIORAL_EQUIVALENCE_ARCHIVE_PROFILE,
    policy_profile: SCENARIO_BEHAVIORAL_POLICY_PROFILE,
    context_profile: SCENARIO_CONTEXT_SIGNATURE_PROFILE,
    novelty_boundary: SCENARIO_BEHAVIORAL_NOVELTY_BOUNDARY,
    candidates,
    equivalence_classes: equivalenceClasses,
    summary: {
      candidate_count: candidates.length,
      unique_context_signatures: contextCount,
      unique_policy_signatures: policyCount,
      operational_behavior_profiles_observed: [...new Set(candidates.map((candidate) => candidate.operational_behavior_profile_id))].sort(),
      policy_equivalence_classes: policyCount,
      context_only_variant_count: candidates.length - policyCount,
      policy_novelty_ratio_bps: Math.floor((policyCount * 10_000) / candidates.length),
      maximum_contexts_in_one_policy_class: Math.max(...contextsPerClass),
      minimum_contexts_in_one_policy_class: Math.min(...contextsPerClass),
      behavioral_uniqueness_status: uniquenessStatus(candidates.length, policyCount),
      narrative_or_provenance_only_changes_create_policy_novelty: false,
      operational_context_change_without_policy_change_counts_as_policy_novelty: false,
    },
    truth_boundaries: {
      clinical_authority: 'NOT_GRANTED',
      patient_care_use: 'PROHIBITED',
      human_team_behavior: 'STRUCTURAL_ONLY_NOT_CALIBRATED',
      operational_timing: 'NOT_CALIBRATED',
      empirical_behavioral_validity: 'NOT_ESTABLISHED',
      scoring_behavior: 'inherited_unchanged',
    },
  };
  return { ...withoutRoot, archive_root_sha256: sha256Canonical(withoutRoot) };
}
