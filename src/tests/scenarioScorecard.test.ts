import assert from 'node:assert/strict';
import test from 'node:test';
import { buildFieldRoute } from '../scenario-core/route';
import { buildScenarioSourceConformanceScorecard } from '../scenario-core/scorecard';
import type { ScenarioRunTrace } from '../scenario-core/scorecard';

function canonicalTrace(profile: ScenarioRunTrace['operational_behavior_profile_id']): { route: ReturnType<typeof buildFieldRoute>; trace: ScenarioRunTrace } {
  const route = buildFieldRoute('ASK-ROUTE-TEST', profile);
  const nodes = ['briefing', 'approach', 'contact', 'pressure'];
  if (profile === 'COMMUNICATION_RELAY_REQUIRED' || profile === 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION') nodes.push('communications-relay');
  if (profile === 'RESOURCE_COORDINATION_REQUIRED' || profile === 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION') nodes.push('resource-coordination');
  nodes.push('handoff', 'complete');
  const edgeByTransition = new Map(route.edges.map((edge) => [`${edge.from}->${edge.to}`, edge.edge_id]));
  const edges = nodes.slice(1).map((node, index) => {
    const key = `${nodes[index]}->${node}`;
    const id = edgeByTransition.get(key);
    if (!id) throw new Error(`missing edge ${key}`);
    return id;
  });
  return {
    route,
    trace: {
      schema_version: '1.0.0',
      route_id: route.route_id,
      operational_behavior_profile_id: profile,
      visited_node_ids: nodes,
      traversed_edge_ids: edges,
      safety_event_ids: [],
      terminal_reached: true,
    },
  };
}

test('all four reviewed behavior profiles produce passing source-conformance scorecards', () => {
  for (const profile of [
    'DIRECT_HANDOFF_BASELINE',
    'COMMUNICATION_RELAY_REQUIRED',
    'RESOURCE_COORDINATION_REQUIRED',
    'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
  ] as const) {
    const { route, trace } = canonicalTrace(profile);
    const scorecard = buildScenarioSourceConformanceScorecard(route, trace);
    assert.equal(scorecard.overall_status, 'PASS');
    assert.equal(scorecard.safety_gate, 'PASS');
    assert.equal(scorecard.source_conformance_score_bps, 10_000);
    assert.equal(scorecard.validity_boundary, 'NOT_A_VALIDATED_PROFICIENCY_MEASURE');
    assert.equal(scorecard.timing_score_effect, 'NONE_UNTIL_CALIBRATED_FOR_DECLARED_SCOPE');
    assert.match(scorecard.scorecard_sha256, /^[0-9a-f]{64}$/);
  }
});

test('critical safety evidence hard-fails and cannot be averaged away', () => {
  const { route, trace } = canonicalTrace('DIRECT_HANDOFF_BASELINE');
  trace.safety_event_ids = ['unsafe-treatment-change'];
  const scorecard = buildScenarioSourceConformanceScorecard(route, trace);
  assert.equal(scorecard.overall_status, 'FAIL');
  assert.equal(scorecard.safety_gate, 'FAIL');
  assert.equal(scorecard.source_conformance_score_bps, 0);
  assert.equal(scorecard.dimensions.find((item) => item.dimension_id === 'safety')?.status, 'CRITICAL_FAILURE');
});

test('incomplete traces return insufficient evidence instead of a fabricated score', () => {
  const route = buildFieldRoute('ASK-ROUTE-TEST', 'COMMUNICATION_RELAY_REQUIRED');
  const trace: ScenarioRunTrace = {
    schema_version: '1.0.0',
    route_id: route.route_id,
    operational_behavior_profile_id: 'COMMUNICATION_RELAY_REQUIRED',
    visited_node_ids: ['briefing', 'approach'],
    traversed_edge_ids: ['e1'],
    safety_event_ids: [],
    terminal_reached: false,
  };
  const scorecard = buildScenarioSourceConformanceScorecard(route, trace);
  assert.equal(scorecard.overall_status, 'INSUFFICIENT_EVIDENCE');
  assert.equal(scorecard.source_conformance_score_bps, null);
  assert.equal(scorecard.evidence_sufficient_for_composite, false);
});

test('unknown nodes and mismatched profile identities are rejected', () => {
  const { route, trace } = canonicalTrace('RESOURCE_COORDINATION_REQUIRED');
  assert.throws(
    () => buildScenarioSourceConformanceScorecard(route, { ...trace, visited_node_ids: [...trace.visited_node_ids, 'unknown'] }),
    /unknown route node/,
  );
  assert.throws(
    () => buildScenarioSourceConformanceScorecard(route, { ...trace, operational_behavior_profile_id: 'DIRECT_HANDOFF_BASELINE' }),
    /behavior profile differs/,
  );
});
