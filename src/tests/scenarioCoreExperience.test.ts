import test from 'node:test';
import assert from 'node:assert/strict';
import { buildTemplateLockedScenario, selectNextNode, validateRouteGraph, validateScenarioExperience } from '../scenario-core/index';
import { RESEARCH_BRIDGE_FIXTURE } from '../test-fixtures/researchBridge.fixture';

const generated = buildTemplateLockedScenario(RESEARCH_BRIDGE_FIXTURE, {
  topic_id: 'airway',
  seed: 41027,
  retriever_track: 'hybrid_cc_loto',
});

function followBranch(firstContactTrigger: 'facilitator_event' | 'handoff_ready'): string[] {
  const visited: string[] = [];
  let node = generated.route.start_node_id;
  while (node !== 'complete') {
    assert.ok(node, 'route ended before completion');
    visited.push(node);
    const trigger = node === 'briefing'
      ? 'start'
      : node === 'approach'
        ? 'arrive'
        : node === 'contact'
          ? firstContactTrigger
          : node === 'handoff'
            ? 'close'
            : 'handoff_ready';
    node = selectNextNode(generated.route, node, trigger) ?? '';
  }
  visited.push(node);
  return visited;
}

test('verified scenario exposes a complete, bounded, plain-language experience', () => {
  const report = validateScenarioExperience(generated);
  assert.equal(report.status, 'PASS', JSON.stringify(report.issues));
  assert.equal(report.truth_boundaries.clinical_authority, 'NOT_GRANTED');
  assert.equal(report.truth_boundaries.patient_care_use, 'PROHIBITED');
  assert.equal(report.metrics.terminal_nodes, 1);
  assert.ok(report.metrics.branching_nodes >= 1);
  assert.equal(report.metrics.successful_routes, 2);
  assert.ok(report.metrics.maximum_route_steps >= 4);
});

test('a source node cannot expose two destinations behind the same trigger', () => {
  const route = structuredClone(generated.route);
  const original = route.edges[0]!;
  route.edges.push({
    ...original,
    edge_id: 'duplicate-trigger-different-priority',
    to: route.edges[1]!.to,
    priority: original.priority - 1,
  });
  const validation = validateRouteGraph(route);
  assert.equal(validation.valid, false);
  assert.equal(validation.deterministic_triggers, false);
  assert.ok(validation.issues.some((issue) => issue.includes('more than one destination for trigger')));
});

test('both admitted route branches terminate and preserve every profile requirement', () => {
  const pressurePath = followBranch('facilitator_event');
  const directPath = followBranch('handoff_ready');
  assert.equal(pressurePath.at(-1), 'complete');
  assert.equal(directPath.at(-1), 'complete');
  assert.notDeepEqual(pressurePath, directPath);

  const requiredNodes = generated.route.nodes
    .filter((node) => node.operational_semantic === 'communications_relay' || node.operational_semantic === 'resource_coordination')
    .map((node) => node.node_id);
  for (const requiredNode of requiredNodes) {
    assert.ok(pressurePath.includes(requiredNode), `pressure path bypassed ${requiredNode}`);
    assert.ok(directPath.includes(requiredNode), `alternate path bypassed ${requiredNode}`);
  }
});
