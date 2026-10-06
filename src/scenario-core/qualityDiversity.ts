import { canonicalJson, sha256Canonical } from './hash';
import type { ScenarioRouteGraph, VerifiedScenarioPackage } from './types';

export const SCENARIO_BEHAVIOR_DESCRIPTOR_PROFILE = 'INTERPRETABLE_OPERATIONAL_BEHAVIOR_DESCRIPTOR_V1' as const;
export const SCENARIO_BEHAVIOR_CELL_PROFILE = 'TOPIC_COMMUNICATIONS_RESOURCES_ROUTE_SHAPE_V1' as const;
export const SCENARIO_BEHAVIOR_FEASIBILITY_PROFILE = 'TOPIC_X_OBSERVED_FEASIBLE_OPERATIONAL_POLICY_SHAPE_V1' as const;
export const SCENARIO_ASSURANCE_QUALITY_PROFILE = 'NONCLINICAL_ASSURANCE_AND_COVERAGE_VECTOR_V1' as const;
export const SCENARIO_BEHAVIOR_ARCHIVE_PROFILE = 'DETERMINISTIC_QUALITY_DIVERSITY_ARCHIVE_V1' as const;
export const SCENARIO_BEHAVIOR_SELECTION_BOUNDARY = 'SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING' as const;
export const SCENARIO_HUMAN_BEHAVIOR_BOUNDARY = 'STRUCTURAL_ONLY_NOT_CALIBRATED' as const;

export interface ScenarioBehaviorDescriptor {
  schema_version: '1.0.0';
  descriptor_profile: typeof SCENARIO_BEHAVIOR_DESCRIPTOR_PROFILE;
  topic_id: string;
  operational_context: {
    location: string;
    weather: string;
    visibility: string;
    communications: string;
    resources: string;
    resource_event: string;
  };
  route_shape: {
    topology_profile: 'REACHABLE_TERMINATING_DAG_V1';
    route_nodes: number;
    route_edges: number;
    terminal_nodes: number;
    branching_nodes: number;
    pressure_nodes: number;
    maximum_route_steps: number;
    successful_route_count: number;
  };
  expected_action_counts: {
    critical: number;
    important: number;
    optional: number;
    unsafe: number;
  };
}

export interface ScenarioBehaviorCellDescriptor {
  schema_version: '1.0.0';
  cell_profile: typeof SCENARIO_BEHAVIOR_CELL_PROFILE;
  topic_id: string;
  communications: string;
  resources: string;
  branching_nodes: number;
  maximum_route_steps: number;
}

export interface ScenarioAssuranceQualityVector {
  schema_version: '1.0.0';
  quality_profile: typeof SCENARIO_ASSURANCE_QUALITY_PROFILE;
  unique_interactions: number;
  rarity_points: number;
  certificate_checks_passed: number;
  experience_checks: number;
  independent_checks: number;
  provenance_records: number;
  learning_cycle_records: number;
}

export interface ScenarioBehaviorCandidate {
  candidate_id: string;
  package_sha256: string;
  source_scenario_id: string;
  topic_id: string;
  seed: number;
  retriever_track: string;
  factor_assignment: Record<string, string>;
  behavior_signature_sha256: string;
  behavior_descriptor: ScenarioBehaviorDescriptor;
  cell_id: string;
  cell_descriptor: ScenarioBehaviorCellDescriptor;
  quality_vector: ScenarioAssuranceQualityVector;
}

export interface ScenarioBehaviorArchiveCell {
  cell_id: string;
  cell_descriptor: ScenarioBehaviorCellDescriptor;
  candidate_ids: string[];
  elite_candidate_id: string;
}

export interface ScenarioBehaviorArchive {
  schema_version: '1.0.0';
  classification: 'PASS';
  status: 'PASS';
  archive_profile: typeof SCENARIO_BEHAVIOR_ARCHIVE_PROFILE;
  behavior_descriptor_profile: typeof SCENARIO_BEHAVIOR_DESCRIPTOR_PROFILE;
  cell_profile: typeof SCENARIO_BEHAVIOR_CELL_PROFILE;
  cell_feasibility_profile: typeof SCENARIO_BEHAVIOR_FEASIBILITY_PROFILE;
  quality_profile: typeof SCENARIO_ASSURANCE_QUALITY_PROFILE;
  selection_boundary: typeof SCENARIO_BEHAVIOR_SELECTION_BOUNDARY;
  candidates: ScenarioBehaviorCandidate[];
  cells: ScenarioBehaviorArchiveCell[];
  summary: {
    candidate_count: number;
    unique_behavior_signatures: number;
    duplicate_behavior_candidates: number;
    occupied_cells: number;
    possible_cells_in_observed_domain: number;
    feasible_operational_policy_shapes: number;
    marginal_cartesian_cells_in_observed_domain: number;
    infeasible_cartesian_cells_excluded: number;
    occupied_cell_ratio_bps: number;
    elite_count: number;
    minimum_cell_occupancy: number;
    maximum_cell_occupancy: number;
    total_strength_three_interactions_observed: number;
    candidates_with_unique_interaction_contribution: number;
    narrative_or_provenance_only_variants_create_new_behavior: false;
  };
  truth_boundaries: {
    clinical_authority: 'NOT_GRANTED';
    patient_care_use: 'PROHIBITED';
    human_team_behavior: typeof SCENARIO_HUMAN_BEHAVIOR_BOUNDARY;
    operational_timing: 'NOT_CALIBRATED';
    patient_dynamics: 'SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY';
    scoring_behavior: 'inherited_unchanged';
    quality_vector_use: typeof SCENARIO_BEHAVIOR_SELECTION_BOUNDARY;
  };
  archive_root_sha256: string;
}

export interface ScenarioBehaviorCandidateInput {
  generated: VerifiedScenarioPackage;
  experience_checks: number;
  independent_checks: number;
}

interface RouteShape {
  route_nodes: number;
  route_edges: number;
  terminal_nodes: number;
  branching_nodes: number;
  pressure_nodes: number;
  maximum_route_steps: number;
  successful_route_count: number;
}

function require(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function requireNonnegativeInteger(value: number, label: string): void {
  require(Number.isSafeInteger(value) && value >= 0, `${label} must be a nonnegative safe integer.`);
}

function sortedRecord(value: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(value).sort(([left], [right]) => left.localeCompare(right)));
}

function combinations<T>(values: readonly T[], size: number): T[][] {
  const result: T[][] = [];
  const selected: T[] = [];
  const visit = (start: number): void => {
    if (selected.length === size) {
      result.push([...selected]);
      return;
    }
    for (let index = start; index <= values.length - (size - selected.length); index += 1) {
      selected.push(values[index]!);
      visit(index + 1);
      selected.pop();
    }
  };
  visit(0);
  return result;
}

function interactionKeys(assignment: Record<string, string>, strength = 3): string[] {
  const entries = Object.entries(sortedRecord(assignment));
  require(strength >= 1 && strength <= entries.length, 'Interaction strength is outside the assignment dimensions.');
  return combinations(entries, strength).map((items) => canonicalJson(items));
}

function routeShape(route: ScenarioRouteGraph): RouteShape {
  const nodeIds = route.nodes.map((node) => node.node_id);
  require(new Set(nodeIds).size === nodeIds.length, 'Route node IDs must be unique.');
  const nodeById = new Map(route.nodes.map((node) => [node.node_id, node] as const));
  require(nodeById.has(route.start_node_id), 'Route start node is missing.');

  const outgoing = new Map<string, string[]>();
  for (const nodeId of nodeIds) outgoing.set(nodeId, []);
  for (const edge of route.edges) {
    require(nodeById.has(edge.from), `Route edge ${edge.edge_id} has an unknown source.`);
    require(nodeById.has(edge.to), `Route edge ${edge.edge_id} has an unknown destination.`);
    outgoing.get(edge.from)!.push(edge.to);
  }
  for (const destinations of outgoing.values()) destinations.sort((left, right) => left.localeCompare(right));

  const reachable = new Set<string>();
  const stack = [route.start_node_id];
  while (stack.length > 0) {
    const nodeId = stack.pop()!;
    if (reachable.has(nodeId)) continue;
    reachable.add(nodeId);
    for (const destination of outgoing.get(nodeId) ?? []) stack.push(destination);
  }
  require(reachable.size === route.nodes.length, 'Route contains an unreachable node.');

  const visiting = new Set<string>();
  const memo = new Map<string, { routes: number; longest: number }>();
  const analyze = (nodeId: string): { routes: number; longest: number } => {
    const cached = memo.get(nodeId);
    if (cached) return cached;
    require(!visiting.has(nodeId), 'Route contains a cycle.');
    visiting.add(nodeId);
    const node = nodeById.get(nodeId)!;
    const destinations = outgoing.get(nodeId) ?? [];
    if (node.terminal) {
      require(destinations.length === 0, `Terminal route node ${nodeId} has an outgoing edge.`);
      const terminal = { routes: 1, longest: 0 };
      visiting.delete(nodeId);
      memo.set(nodeId, terminal);
      return terminal;
    }
    require(destinations.length > 0, `Reachable route node ${nodeId} is a nonterminal dead end.`);
    const descendants = destinations.map(analyze);
    const result = {
      routes: descendants.reduce((total, item) => total + item.routes, 0),
      longest: 1 + Math.max(...descendants.map((item) => item.longest)),
    };
    require(Number.isSafeInteger(result.routes), 'Successful route count exceeds the safe integer range.');
    visiting.delete(nodeId);
    memo.set(nodeId, result);
    return result;
  };

  const start = analyze(route.start_node_id);
  return {
    route_nodes: route.nodes.length,
    route_edges: route.edges.length,
    terminal_nodes: route.nodes.filter((node) => node.terminal).length,
    branching_nodes: route.nodes.filter((node) => (outgoing.get(node.node_id)?.length ?? 0) > 1).length,
    pressure_nodes: route.nodes.filter((node) => node.node_kind === 'pressure').length,
    maximum_route_steps: start.longest,
    successful_route_count: start.routes,
  };
}

function factorAssignment(generated: VerifiedScenarioPackage): Record<string, string> {
  const context = generated.scenario.operational_context;
  const resourceEvent = generated.atoms.find((atom) => atom.atom_kind === 'resource_event')?.value ?? '';
  require(Boolean(resourceEvent.trim()), 'Scenario behavior descriptor requires a resource event.');
  return sortedRecord({
    communications: context.comms_status,
    location: context.location_type,
    resource_event: resourceEvent,
    resources: context.resource_status,
    topic: generated.build.topic_id,
    visibility: context.visibility,
    weather: context.weather,
  });
}

export function buildScenarioBehaviorDescriptor(generated: VerifiedScenarioPackage): ScenarioBehaviorDescriptor {
  const assignment = factorAssignment(generated);
  const shape = routeShape(generated.route);
  return {
    schema_version: '1.0.0',
    descriptor_profile: SCENARIO_BEHAVIOR_DESCRIPTOR_PROFILE,
    topic_id: generated.build.topic_id,
    operational_context: {
      location: assignment.location!,
      weather: assignment.weather!,
      visibility: assignment.visibility!,
      communications: assignment.communications!,
      resources: assignment.resources!,
      resource_event: assignment.resource_event!,
    },
    route_shape: {
      topology_profile: 'REACHABLE_TERMINATING_DAG_V1',
      ...shape,
    },
    expected_action_counts: {
      critical: generated.scenario.expected_actions.critical.length,
      important: generated.scenario.expected_actions.important.length,
      optional: generated.scenario.expected_actions.optional.length,
      unsafe: generated.scenario.expected_actions.unsafe.length,
    },
  };
}

export function scenarioBehaviorSignature(descriptor: ScenarioBehaviorDescriptor): string {
  return sha256Canonical(descriptor);
}

export function buildScenarioBehaviorCell(descriptor: ScenarioBehaviorDescriptor): ScenarioBehaviorCellDescriptor {
  return {
    schema_version: '1.0.0',
    cell_profile: SCENARIO_BEHAVIOR_CELL_PROFILE,
    topic_id: descriptor.topic_id,
    communications: descriptor.operational_context.communications,
    resources: descriptor.operational_context.resources,
    branching_nodes: descriptor.route_shape.branching_nodes,
    maximum_route_steps: descriptor.route_shape.maximum_route_steps,
  };
}

export function scenarioBehaviorCellId(cell: ScenarioBehaviorCellDescriptor): string {
  return `ASK-QD-CELL-${sha256Canonical(cell).slice(0, 16).toUpperCase()}`;
}

function qualityTuple(vector: ScenarioAssuranceQualityVector): number[] {
  return [
    vector.unique_interactions,
    vector.rarity_points,
    vector.certificate_checks_passed,
    vector.experience_checks,
    vector.independent_checks,
    vector.provenance_records,
    vector.learning_cycle_records,
  ];
}

export function compareScenarioBehaviorCandidates(
  left: ScenarioBehaviorCandidate,
  right: ScenarioBehaviorCandidate,
): number {
  const leftTuple = qualityTuple(left.quality_vector);
  const rightTuple = qualityTuple(right.quality_vector);
  for (let index = 0; index < leftTuple.length; index += 1) {
    const difference = rightTuple[index]! - leftTuple[index]!;
    if (difference !== 0) return difference;
  }
  return left.package_sha256.localeCompare(right.package_sha256);
}

function archiveRoot(value: Omit<ScenarioBehaviorArchive, 'archive_root_sha256'>): string {
  return sha256Canonical(value);
}

export function buildScenarioBehaviorArchive(
  inputs: readonly ScenarioBehaviorCandidateInput[],
): ScenarioBehaviorArchive {
  require(inputs.length > 0, 'Scenario behavior archive requires at least one candidate.');

  const provisional = inputs.map((input) => {
    requireNonnegativeInteger(input.experience_checks, 'experience_checks');
    requireNonnegativeInteger(input.independent_checks, 'independent_checks');
    const generated = input.generated;
    const packageSha = generated.certificate.package_sha256;
    require(/^[0-9a-f]{64}$/.test(packageSha), 'Scenario package hash is malformed.');
    const descriptor = buildScenarioBehaviorDescriptor(generated);
    const assignment = factorAssignment(generated);
    const behaviorSignature = scenarioBehaviorSignature(descriptor);
    const cellDescriptor = buildScenarioBehaviorCell(descriptor);
    const cellId = scenarioBehaviorCellId(cellDescriptor);
    const interactions = interactionKeys(assignment, 3);
    const certificateChecksPassed = Object.values(generated.certificate.checks).filter((value) => value === true).length;
    const provenanceRecords = generated.evidence.length + generated.atoms.length + generated.field_origins.length + generated.stages.length;
    const learningCycleRecords = generated.scenario.training_objectives.length + generated.scenario.aar_teaching_points.length;
    return {
      generated,
      experienceChecks: input.experience_checks,
      independentChecks: input.independent_checks,
      packageSha,
      descriptor,
      assignment,
      behaviorSignature,
      cellDescriptor,
      cellId,
      interactions,
      certificateChecksPassed,
      provenanceRecords,
      learningCycleRecords,
    };
  });

  require(new Set(provisional.map((item) => item.packageSha)).size === provisional.length, 'Scenario behavior archive contains duplicate package identities.');

  const interactionFrequency = new Map<string, number>();
  for (const item of provisional) {
    for (const key of item.interactions) interactionFrequency.set(key, (interactionFrequency.get(key) ?? 0) + 1);
  }

  const candidates: ScenarioBehaviorCandidate[] = provisional.map((item) => {
    const uniqueInteractions = item.interactions.filter((key) => interactionFrequency.get(key) === 1).length;
    const rarityPoints = item.interactions.reduce((total, key) => {
      const frequency = interactionFrequency.get(key)!;
      return total + Math.floor(1_000_000 / frequency);
    }, 0);
    const qualityVector: ScenarioAssuranceQualityVector = {
      schema_version: '1.0.0',
      quality_profile: SCENARIO_ASSURANCE_QUALITY_PROFILE,
      unique_interactions: uniqueInteractions,
      rarity_points: rarityPoints,
      certificate_checks_passed: item.certificateChecksPassed,
      experience_checks: item.experienceChecks,
      independent_checks: item.independentChecks,
      provenance_records: item.provenanceRecords,
      learning_cycle_records: item.learningCycleRecords,
    };
    Object.entries(qualityVector).forEach(([key, value]) => {
      if (typeof value === 'number') requireNonnegativeInteger(value, `quality_vector.${key}`);
    });
    return {
      candidate_id: `ASK-QD-CAND-${item.packageSha.slice(0, 16).toUpperCase()}`,
      package_sha256: item.packageSha,
      source_scenario_id: item.generated.build.source_scenario_id,
      topic_id: item.generated.build.topic_id,
      seed: item.generated.build.seed,
      retriever_track: item.generated.build.retriever_track,
      factor_assignment: item.assignment,
      behavior_signature_sha256: item.behaviorSignature,
      behavior_descriptor: item.descriptor,
      cell_id: item.cellId,
      cell_descriptor: item.cellDescriptor,
      quality_vector: qualityVector,
    };
  }).sort((left, right) => left.candidate_id.localeCompare(right.candidate_id));

  const candidateById = new Map(candidates.map((candidate) => [candidate.candidate_id, candidate] as const));
  const grouped = new Map<string, ScenarioBehaviorCandidate[]>();
  for (const candidate of candidates) {
    const group = grouped.get(candidate.cell_id) ?? [];
    group.push(candidate);
    grouped.set(candidate.cell_id, group);
  }

  const cells: ScenarioBehaviorArchiveCell[] = [...grouped.entries()]
    .map(([cellId, group]) => {
      group.sort(compareScenarioBehaviorCandidates);
      const descriptorJson = canonicalJson(group[0]!.cell_descriptor);
      require(group.every((candidate) => canonicalJson(candidate.cell_descriptor) === descriptorJson), `Behavior cell ${cellId} contains inconsistent descriptors.`);
      return {
        cell_id: cellId,
        cell_descriptor: group[0]!.cell_descriptor,
        candidate_ids: group.map((candidate) => candidate.candidate_id).sort((left, right) => left.localeCompare(right)),
        elite_candidate_id: group[0]!.candidate_id,
      };
    })
    .sort((left, right) => left.cell_id.localeCompare(right.cell_id));

  for (const cell of cells) {
    require(candidateById.has(cell.elite_candidate_id), `Behavior cell ${cell.cell_id} has an unknown elite.`);
  }

  const uniqueBehaviorSignatures = new Set(candidates.map((candidate) => candidate.behavior_signature_sha256)).size;
  const cellOccupancies = cells.map((cell) => cell.candidate_ids.length);
  const topics = new Set(candidates.map((candidate) => candidate.cell_descriptor.topic_id)).size;
  const communications = new Set(candidates.map((candidate) => candidate.cell_descriptor.communications)).size;
  const resources = new Set(candidates.map((candidate) => candidate.cell_descriptor.resources)).size;
  const routeShapes = new Set(candidates.map((candidate) => canonicalJson({
    branching_nodes: candidate.cell_descriptor.branching_nodes,
    maximum_route_steps: candidate.cell_descriptor.maximum_route_steps,
  }))).size;
  // Communications, resources, and route shape are not independent axes: the
  // reviewed operational profile deterministically binds them.  The feasible
  // archive domain is therefore topic x joint operational-policy shape, not
  // the impossible Cartesian product of each marginal value.
  const feasibleOperationalPolicyShapes = new Set(candidates.map((candidate) => canonicalJson({
    communications: candidate.cell_descriptor.communications,
    resources: candidate.cell_descriptor.resources,
    branching_nodes: candidate.cell_descriptor.branching_nodes,
    maximum_route_steps: candidate.cell_descriptor.maximum_route_steps,
  }))).size;
  const possibleCells = topics * feasibleOperationalPolicyShapes;
  const marginalCartesianCells = topics * communications * resources * routeShapes;
  const infeasibleCartesianCellsExcluded = marginalCartesianCells - possibleCells;
  require(possibleCells > 0, 'Observed feasible behavior-cell domain is empty.');
  require(
    possibleCells <= marginalCartesianCells && infeasibleCartesianCellsExcluded >= 0,
    'Feasible behavior-cell domain exceeds its marginal Cartesian envelope.',
  );

  const withoutRoot: Omit<ScenarioBehaviorArchive, 'archive_root_sha256'> = {
    schema_version: '1.0.0',
    classification: 'PASS',
    status: 'PASS',
    archive_profile: SCENARIO_BEHAVIOR_ARCHIVE_PROFILE,
    behavior_descriptor_profile: SCENARIO_BEHAVIOR_DESCRIPTOR_PROFILE,
    cell_profile: SCENARIO_BEHAVIOR_CELL_PROFILE,
    cell_feasibility_profile: SCENARIO_BEHAVIOR_FEASIBILITY_PROFILE,
    quality_profile: SCENARIO_ASSURANCE_QUALITY_PROFILE,
    selection_boundary: SCENARIO_BEHAVIOR_SELECTION_BOUNDARY,
    candidates,
    cells,
    summary: {
      candidate_count: candidates.length,
      unique_behavior_signatures: uniqueBehaviorSignatures,
      duplicate_behavior_candidates: candidates.length - uniqueBehaviorSignatures,
      occupied_cells: cells.length,
      possible_cells_in_observed_domain: possibleCells,
      feasible_operational_policy_shapes: feasibleOperationalPolicyShapes,
      marginal_cartesian_cells_in_observed_domain: marginalCartesianCells,
      infeasible_cartesian_cells_excluded: infeasibleCartesianCellsExcluded,
      occupied_cell_ratio_bps: Math.floor((cells.length * 10_000) / possibleCells),
      elite_count: cells.length,
      minimum_cell_occupancy: Math.min(...cellOccupancies),
      maximum_cell_occupancy: Math.max(...cellOccupancies),
      total_strength_three_interactions_observed: interactionFrequency.size,
      candidates_with_unique_interaction_contribution: candidates.filter((candidate) => candidate.quality_vector.unique_interactions > 0).length,
      narrative_or_provenance_only_variants_create_new_behavior: false,
    },
    truth_boundaries: {
      clinical_authority: 'NOT_GRANTED',
      patient_care_use: 'PROHIBITED',
      human_team_behavior: SCENARIO_HUMAN_BEHAVIOR_BOUNDARY,
      operational_timing: 'NOT_CALIBRATED',
      patient_dynamics: 'SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY',
      scoring_behavior: 'inherited_unchanged',
      quality_vector_use: SCENARIO_BEHAVIOR_SELECTION_BOUNDARY,
    },
  };

  return {
    ...withoutRoot,
    archive_root_sha256: archiveRoot(withoutRoot),
  };
}
