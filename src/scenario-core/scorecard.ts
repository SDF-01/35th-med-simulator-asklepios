import type { ScenarioOperationalBehaviorProfileId } from './behaviorProfiles';
import { sha256Canonical } from './hash';
import type { ScenarioRouteGraph } from './types';

export const SCENARIO_SCORECARD_PROFILE = 'SOURCE_CONFORMANCE_MULTIDIMENSIONAL_SCORECARD_V1' as const;
export const SCENARIO_SCORECARD_VALIDITY = 'NOT_A_VALIDATED_PROFICIENCY_MEASURE' as const;

export type ScenarioScoreDimensionId =
  | 'situation_assessment'
  | 'information_management'
  | 'prioritization'
  | 'communication'
  | 'resource_coordination'
  | 'reassessment'
  | 'closed_loop_handoff'
  | 'safety';

export type ScenarioDimensionStatus =
  | 'SATISFIED'
  | 'NOT_SATISFIED'
  | 'INSUFFICIENT_EVIDENCE'
  | 'NOT_APPLICABLE'
  | 'CRITICAL_FAILURE';

export interface ScenarioRunTrace {
  schema_version: '1.0.0';
  route_id: string;
  operational_behavior_profile_id: ScenarioOperationalBehaviorProfileId;
  visited_node_ids: string[];
  traversed_edge_ids: string[];
  safety_event_ids: string[];
  terminal_reached: boolean;
}

export interface ScenarioScoreDimensionRecord {
  dimension_id: ScenarioScoreDimensionId;
  status: ScenarioDimensionStatus;
  evidence_node_ids: string[];
  evidence_edge_ids: string[];
  evidence_event_ids: string[];
  plain_language_finding: string;
  scoring_authority: 'SOURCE_CONFORMANCE_ONLY';
  psychometric_validity: 'NOT_ESTABLISHED';
}

export interface ScenarioSourceConformanceScorecard {
  schema_version: '1.0.0';
  scorecard_profile: typeof SCENARIO_SCORECARD_PROFILE;
  route_id: string;
  operational_behavior_profile_id: ScenarioOperationalBehaviorProfileId;
  overall_status: 'PASS' | 'FAIL' | 'INSUFFICIENT_EVIDENCE';
  safety_gate: 'PASS' | 'FAIL' | 'INSUFFICIENT_EVIDENCE';
  source_conformance_score_bps: number | null;
  evidence_sufficient_for_composite: boolean;
  dimensions: ScenarioScoreDimensionRecord[];
  timing_score_effect: 'NONE_UNTIL_CALIBRATED_FOR_DECLARED_SCOPE';
  scoring_state: 'SOURCE_CONFORMANCE_ONLY';
  validity_boundary: typeof SCENARIO_SCORECARD_VALIDITY;
  scorecard_sha256: string;
}

function uniqueSorted(values: readonly string[]): string[] {
  return [...new Set(values)].sort();
}

function routeProfile(route: ScenarioRouteGraph): ScenarioOperationalBehaviorProfileId {
  const value = route.route_id.split(':').at(-1);
  const admitted: readonly ScenarioOperationalBehaviorProfileId[] = [
    'DIRECT_HANDOFF_BASELINE',
    'COMMUNICATION_RELAY_REQUIRED',
    'RESOURCE_COORDINATION_REQUIRED',
    'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
  ];
  if (!admitted.includes(value as ScenarioOperationalBehaviorProfileId)) {
    throw new Error('Scenario route lacks a reviewed operational behavior profile.');
  }
  return value as ScenarioOperationalBehaviorProfileId;
}

function visitedInOrder(trace: ScenarioRunTrace, nodeIds: readonly string[]): boolean {
  let previous = -1;
  for (const nodeId of nodeIds) {
    const index = trace.visited_node_ids.indexOf(nodeId);
    if (index < 0 || index <= previous) return false;
    previous = index;
  }
  return true;
}

function record(
  dimension_id: ScenarioScoreDimensionId,
  status: ScenarioDimensionStatus,
  plain_language_finding: string,
  evidence_node_ids: readonly string[] = [],
  evidence_edge_ids: readonly string[] = [],
  evidence_event_ids: readonly string[] = [],
): ScenarioScoreDimensionRecord {
  return {
    dimension_id,
    status,
    evidence_node_ids: uniqueSorted(evidence_node_ids),
    evidence_edge_ids: uniqueSorted(evidence_edge_ids),
    evidence_event_ids: uniqueSorted(evidence_event_ids),
    plain_language_finding,
    scoring_authority: 'SOURCE_CONFORMANCE_ONLY',
    psychometric_validity: 'NOT_ESTABLISHED',
  };
}

/**
 * Build a transparent source-conformance scorecard from the deterministic route
 * trace. It deliberately does not infer clinical proficiency, real-world timing,
 * or treatment competence.
 */
export function buildScenarioSourceConformanceScorecard(
  route: ScenarioRouteGraph,
  rawTrace: ScenarioRunTrace,
): ScenarioSourceConformanceScorecard {
  const profile = routeProfile(route);
  if (rawTrace.route_id !== route.route_id) throw new Error('Scorecard trace route differs.');
  if (rawTrace.operational_behavior_profile_id !== profile) throw new Error('Scorecard trace behavior profile differs.');

  const nodeIds = new Set(route.nodes.map((node) => node.node_id));
  const edgeIds = new Set(route.edges.map((edge) => edge.edge_id));
  if (rawTrace.visited_node_ids.some((id) => !nodeIds.has(id))) throw new Error('Scorecard trace contains an unknown route node.');
  if (rawTrace.traversed_edge_ids.some((id) => !edgeIds.has(id))) throw new Error('Scorecard trace contains an unknown route edge.');
  if (new Set(rawTrace.visited_node_ids).size !== rawTrace.visited_node_ids.length) throw new Error('Scorecard trace repeats a route node.');
  if (new Set(rawTrace.traversed_edge_ids).size !== rawTrace.traversed_edge_ids.length) throw new Error('Scorecard trace repeats a route edge.');

  const trace: ScenarioRunTrace = {
    ...rawTrace,
    visited_node_ids: [...rawTrace.visited_node_ids],
    traversed_edge_ids: [...rawTrace.traversed_edge_ids],
    safety_event_ids: uniqueSorted(rawTrace.safety_event_ids),
  };
  const visited = new Set(trace.visited_node_ids);
  const traversed = new Set(trace.traversed_edge_ids);
  const observationNodes = route.nodes.filter((node) => node.node_kind === 'observation').map((node) => node.node_id);
  const pressureNodes = route.nodes.filter((node) => node.node_kind === 'pressure').map((node) => node.node_id);
  const handoffNodes = route.nodes.filter((node) => node.node_kind === 'handoff').map((node) => node.node_id);
  const completeNode = route.nodes.find((node) => node.terminal)?.node_id;
  const resourceRequired = profile === 'RESOURCE_COORDINATION_REQUIRED' || profile === 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION';
  const resourceNode = route.nodes.find((node) => node.node_id === 'resource-coordination')?.node_id;
  const relayRequired = profile === 'COMMUNICATION_RELAY_REQUIRED' || profile === 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION';
  const relayNode = route.nodes.find((node) => node.node_id === 'communications-relay')?.node_id;

  const completeTrace = trace.terminal_reached && Boolean(completeNode && visited.has(completeNode));
  const safetyFailure = trace.safety_event_ids.length > 0;
  const dimensions: ScenarioScoreDimensionRecord[] = [];

  const assessmentSatisfied = observationNodes.length > 0 && observationNodes.every((id) => visited.has(id));
  dimensions.push(record(
    'situation_assessment',
    !completeTrace && !assessmentSatisfied ? 'INSUFFICIENT_EVIDENCE' : assessmentSatisfied ? 'SATISFIED' : 'NOT_SATISFIED',
    assessmentSatisfied ? 'The trace reached the reviewed observation step.' : 'The reviewed observation step was not completed.',
    observationNodes.filter((id) => visited.has(id)),
  ));

  const informationSatisfied = pressureNodes.some((id) => visited.has(id));
  dimensions.push(record(
    'information_management',
    !completeTrace && !informationSatisfied ? 'INSUFFICIENT_EVIDENCE' : informationSatisfied ? 'SATISFIED' : 'NOT_SATISFIED',
    informationSatisfied ? 'The learner encountered and processed an operational information constraint.' : 'No operational information constraint was observed in the trace.',
    pressureNodes.filter((id) => visited.has(id)),
  ));

  const prioritizationSatisfied = visitedInOrder(trace, ['briefing', 'approach', 'contact']);
  dimensions.push(record(
    'prioritization',
    !completeTrace && !prioritizationSatisfied ? 'INSUFFICIENT_EVIDENCE' : prioritizationSatisfied ? 'SATISFIED' : 'NOT_SATISFIED',
    prioritizationSatisfied ? 'The trace preserved the reviewed brief, movement, and contact order.' : 'The reviewed opening sequence was incomplete or out of order.',
    ['briefing', 'approach', 'contact'].filter((id) => visited.has(id)),
  ));

  const communicationRequiredNodes = relayRequired && relayNode ? [relayNode, 'handoff'] : ['handoff'];
  const communicationSatisfied = communicationRequiredNodes.every((id) => visited.has(id));
  dimensions.push(record(
    'communication',
    !completeTrace && !communicationSatisfied ? 'INSUFFICIENT_EVIDENCE' : communicationSatisfied ? 'SATISFIED' : 'NOT_SATISFIED',
    communicationSatisfied
      ? relayRequired ? 'The trace completed the required relay and final handoff steps.' : 'The trace completed the reviewed handoff step.'
      : relayRequired ? 'The required communications relay and handoff were not both completed.' : 'The reviewed handoff was not completed.',
    communicationRequiredNodes.filter((id) => visited.has(id)),
  ));

  if (!resourceRequired) {
    dimensions.push(record(
      'resource_coordination',
      'NOT_APPLICABLE',
      'This operational profile does not require the constrained-resource coordination step.',
    ));
  } else {
    const resourceSatisfied = Boolean(resourceNode && visited.has(resourceNode));
    dimensions.push(record(
      'resource_coordination',
      !completeTrace && !resourceSatisfied ? 'INSUFFICIENT_EVIDENCE' : resourceSatisfied ? 'SATISFIED' : 'NOT_SATISFIED',
      resourceSatisfied ? 'The trace completed the required resource-coordination step.' : 'The required resource-coordination step was not completed.',
      resourceSatisfied && resourceNode ? [resourceNode] : [],
    ));
  }

  const contactIndex = trace.visited_node_ids.indexOf('contact');
  const firstPressureIndex = Math.min(...pressureNodes.map((id) => trace.visited_node_ids.indexOf(id)).filter((index) => index >= 0));
  const firstHandoffIndex = Math.min(...handoffNodes.map((id) => trace.visited_node_ids.indexOf(id)).filter((index) => index >= 0));
  const reassessmentSatisfied = Number.isFinite(firstPressureIndex)
    && Number.isFinite(firstHandoffIndex)
    && contactIndex >= 0
    && firstPressureIndex > contactIndex
    && firstHandoffIndex > firstPressureIndex;
  dimensions.push(record(
    'reassessment',
    !completeTrace && !reassessmentSatisfied ? 'INSUFFICIENT_EVIDENCE' : reassessmentSatisfied ? 'SATISFIED' : 'NOT_SATISFIED',
    reassessmentSatisfied ? 'The trace addressed an operational constraint after contact and before handoff.' : 'The trace does not show the reviewed reassessment sequence.',
    pressureNodes.filter((id) => visited.has(id)),
  ));

  const finalEdge = route.edges.find((edge) => edge.to === completeNode)?.edge_id;
  const handoffSatisfied = Boolean(completeTrace && finalEdge && traversed.has(finalEdge));
  dimensions.push(record(
    'closed_loop_handoff',
    !completeTrace ? 'INSUFFICIENT_EVIDENCE' : handoffSatisfied ? 'SATISFIED' : 'NOT_SATISFIED',
    handoffSatisfied ? 'The trace closed the handoff and reached the terminal state.' : 'The trace did not prove a closed-loop terminal handoff.',
    handoffNodes.filter((id) => visited.has(id)),
    finalEdge && traversed.has(finalEdge) ? [finalEdge] : [],
  ));

  dimensions.push(record(
    'safety',
    safetyFailure ? 'CRITICAL_FAILURE' : completeTrace ? 'SATISFIED' : 'INSUFFICIENT_EVIDENCE',
    safetyFailure ? 'A critical safety event was recorded. No composite score may override this failure.' : completeTrace ? 'No critical safety event was recorded in the completed trace.' : 'The run is incomplete, so the safety dimension does not have enough evidence.',
    [],
    [],
    trace.safety_event_ids,
  ));

  const scoreable = dimensions.filter((item) => !['NOT_APPLICABLE', 'INSUFFICIENT_EVIDENCE'].includes(item.status));
  const satisfied = scoreable.filter((item) => item.status === 'SATISFIED').length;
  const evidenceSufficient = completeTrace && dimensions.every((item) => item.status !== 'INSUFFICIENT_EVIDENCE');
  const score = evidenceSufficient && scoreable.length > 0
    ? Math.floor((satisfied * 10_000) / scoreable.length)
    : null;
  const safetyGate: ScenarioSourceConformanceScorecard['safety_gate'] = safetyFailure
    ? 'FAIL'
    : completeTrace
      ? 'PASS'
      : 'INSUFFICIENT_EVIDENCE';
  const overallStatus: ScenarioSourceConformanceScorecard['overall_status'] = safetyFailure
    ? 'FAIL'
    : evidenceSufficient
      ? dimensions.some((item) => item.status === 'NOT_SATISFIED') ? 'FAIL' : 'PASS'
      : 'INSUFFICIENT_EVIDENCE';

  const withoutHash: Omit<ScenarioSourceConformanceScorecard, 'scorecard_sha256'> = {
    schema_version: '1.0.0',
    scorecard_profile: SCENARIO_SCORECARD_PROFILE,
    route_id: route.route_id,
    operational_behavior_profile_id: profile,
    overall_status: overallStatus,
    safety_gate: safetyGate,
    source_conformance_score_bps: safetyFailure ? 0 : score,
    evidence_sufficient_for_composite: evidenceSufficient,
    dimensions,
    timing_score_effect: 'NONE_UNTIL_CALIBRATED_FOR_DECLARED_SCOPE',
    scoring_state: 'SOURCE_CONFORMANCE_ONLY',
    validity_boundary: SCENARIO_SCORECARD_VALIDITY,
  };
  return { ...withoutHash, scorecard_sha256: sha256Canonical(withoutHash) };
}
