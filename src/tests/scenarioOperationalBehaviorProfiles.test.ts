import assert from 'node:assert/strict';
import test from 'node:test';
import { resolveScenarioOperationalBehaviorProfile } from '../scenario-core/behaviorProfiles';
import {
  buildFieldRoute,
  enumerateSuccessfulRouteWitnesses,
  replayRouteWitness,
  selectNextNode,
  validateRouteGraph,
} from '../scenario-core/route';

const CONDITIONS = [
  ['degraded', 'constrained'],
  ['intermittent', 'constrained'],
  ['degraded', 'overwhelmed'],
  ['unavailable', 'overwhelmed'],
] as const;


test('reviewed operational conditions resolve to four deterministic profiles', () => {
  assert.equal(resolveScenarioOperationalBehaviorProfile('degraded', 'constrained').profile_id, 'DIRECT_HANDOFF_BASELINE');
  assert.equal(resolveScenarioOperationalBehaviorProfile('intermittent', 'constrained').profile_id, 'COMMUNICATION_RELAY_REQUIRED');
  assert.equal(resolveScenarioOperationalBehaviorProfile('degraded', 'overwhelmed').profile_id, 'RESOURCE_COORDINATION_REQUIRED');
  assert.equal(resolveScenarioOperationalBehaviorProfile('unavailable', 'overwhelmed').profile_id, 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION');
});

test('every operational profile preserves two valid routes and every mandatory teamwork step', () => {
  for (const [communications, resources] of CONDITIONS) {
    const profile = resolveScenarioOperationalBehaviorProfile(communications, resources);
    const route = buildFieldRoute('fixture', profile.profile_id);
    const report = validateRouteGraph(route);
    assert.equal(report.valid, true, `${profile.profile_id}:${report.issues.join(',')}`);
    assert.equal(report.meaningful_branch, true, profile.profile_id);
    assert.equal(report.successful_route_count, 2, profile.profile_id);
    assert.equal(report.profile_requirements_preserved, true, profile.profile_id);
    assert.equal(route.nodes.length, 6 + profile.intermediate_handoff_steps);
    assert.equal(route.edges.length, route.nodes.length);

    const expectedFirst = profile.communications_constraint === 'RELAY_REQUIRED'
      ? 'communications-relay'
      : profile.resource_constraint === 'COORDINATION_REQUIRED'
        ? 'resource-coordination'
        : 'handoff';
    const contactEdges = route.edges.filter((edge) => edge.from === 'contact');
    assert.deepEqual(
      contactEdges.map((edge) => `${edge.trigger}:${edge.to}`).sort(),
      [`facilitator_event:pressure`, `handoff_ready:${expectedFirst}`].sort(),
      profile.profile_id,
    );

    const reversedEdgeRoute = { ...route, edges: [...route.edges].reverse() };
    for (const candidate of [route, reversedEdgeRoute]) {
      assert.equal(selectNextNode(candidate, 'contact', 'facilitator_event'), 'pressure', profile.profile_id);
      assert.equal(selectNextNode(candidate, 'contact', 'handoff_ready'), expectedFirst, profile.profile_id);
      assert.equal(selectNextNode(candidate, 'pressure', 'handoff_ready'), expectedFirst, profile.profile_id);
    }

    const requiredSemantics: Array<'communications_relay' | 'resource_coordination'> = [];
    if (profile.communications_constraint === 'RELAY_REQUIRED') requiredSemantics.push('communications_relay');
    if (profile.resource_constraint === 'COORDINATION_REQUIRED') requiredSemantics.push('resource_coordination');
    const witnesses = enumerateSuccessfulRouteWitnesses(route);
    const reorderedWitnesses = enumerateSuccessfulRouteWitnesses(reversedEdgeRoute);
    assert.deepEqual(reorderedWitnesses, witnesses, `${profile.profile_id}:witness inventory depends on edge storage order`);
    assert.equal(witnesses.length, 2, profile.profile_id);
    const pressureWitness = witnesses.find((witness) => witness.node_ids.includes('pressure'));
    const directWitness = witnesses.find((witness) => !witness.node_ids.includes('pressure'));
    assert.ok(pressureWitness, `${profile.profile_id}:pressure witness missing`);
    assert.ok(directWitness, `${profile.profile_id}:direct witness missing`);
    assert.equal(pressureWitness.triggers.length, 5 + profile.intermediate_handoff_steps, profile.profile_id);
    assert.equal(directWitness.triggers.length, 4 + profile.intermediate_handoff_steps, profile.profile_id);

    for (const witness of witnesses) {
      assert.equal(replayRouteWitness(route, witness), true, `${profile.profile_id}:canonical witness replay`);
      assert.equal(replayRouteWitness(reversedEdgeRoute, witness), true, `${profile.profile_id}:reordered witness replay`);
      const semantics = witness.node_ids.map((nodeId) => (
        route.nodes.find((node) => node.node_id === nodeId)?.operational_semantic ?? ''
      ));
      let previousIndex = -1;
      for (const semantic of requiredSemantics) {
        const index = semantics.indexOf(semantic);
        assert.ok(index > previousIndex, `${profile.profile_id}:${semantic}:${semantics.join('>')}`);
        previousIndex = index;
      }
      assert.equal(semantics.at(-1), 'completion', profile.profile_id);
    }
  }
});

test('a profile requirement cannot be bypassed by the alternate branch', () => {
  for (const [communications, resources] of CONDITIONS.slice(1)) {
    const profile = resolveScenarioOperationalBehaviorProfile(communications, resources);
    const route = structuredClone(buildFieldRoute('fixture', profile.profile_id));
    const alternate = route.edges.find((edge) => edge.from === 'contact' && edge.trigger === 'handoff_ready');
    if (!alternate) throw new Error(`alternate branch missing:${profile.profile_id}`);
    alternate.to = 'handoff';
    const report = validateRouteGraph(route);
    assert.equal(report.valid, false, profile.profile_id);
    assert.equal(report.profile_requirements_preserved, false, profile.profile_id);
    assert.ok(report.issues.some((issue) => issue.includes('bypasses')), profile.profile_id);
  }
});
