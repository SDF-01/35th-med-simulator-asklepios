import test from 'node:test';
import assert from 'node:assert/strict';
import { scenariosById } from '../content/scenarios';
import { verifyScenarioPackage } from '../scenario-checker/verify';
import { buildTemplateLockedScenario } from '../scenario-core/assembly';
import { buildPairCoverageSchedule, countUncoveredPairs } from '../scenario-core/coverage';
import { protectedScenarioProjection } from '../scenario-core/projection';
import { RESEARCH_BRIDGE_FIXTURE } from '../test-fixtures/researchBridge.fixture';

test('record ordering does not change the generated package', () => {
  const request = { topic_id: 'airway' as const, seed: 44, retriever_track: 'hybrid_cc_loto' };
  const baseline = buildTemplateLockedScenario(RESEARCH_BRIDGE_FIXTURE, request);
  const reordered = {
    ...RESEARCH_BRIDGE_FIXTURE,
    sources: [...RESEARCH_BRIDGE_FIXTURE.sources].reverse(),
    evidence_refs: [...RESEARCH_BRIDGE_FIXTURE.evidence_refs].reverse(),
    prototypes: [...RESEARCH_BRIDGE_FIXTURE.prototypes].reverse(),
  };
  assert.deepEqual(buildTemplateLockedScenario(reordered, request), baseline);
});

test('changing the seed changes only admitted fields', async () => {
  const first = buildTemplateLockedScenario(RESEARCH_BRIDGE_FIXTURE, { topic_id: 'airway', seed: 1 });
  const second = buildTemplateLockedScenario(RESEARCH_BRIDGE_FIXTURE, { topic_id: 'airway', seed: 2 });
  assert.notEqual(first.certificate.package_sha256, second.certificate.package_sha256);
  assert.deepEqual(protectedScenarioProjection(first.scenario), protectedScenarioProjection(second.scenario));
  const base = scenariosById[first.build.source_scenario_id]!;
  assert.equal((await verifyScenarioPackage(base, first)).status, 'PASS');
  assert.equal((await verifyScenarioPackage(base, second)).status, 'PASS');
});

test('compact factor schedule covers all value pairs', () => {
  const factors = {
    location: ['a', 'b', 'c'],
    weather: ['clear', 'rain', 'cold'],
    communications: ['degraded', 'intermittent', 'unavailable'],
    resources: ['constrained', 'overwhelmed'],
  } as const;
  const schedule = buildPairCoverageSchedule(factors);
  assert.equal(countUncoveredPairs(schedule, factors), 0);
  assert.ok(schedule.length < 54);
});

test('retriever changes evidence binding without changing the operational world', () => {
  const candidate = RESEARCH_BRIDGE_FIXTURE.prototypes[0]!;
  const baseline = {
    ...candidate,
    prototype_id: 'research-airway-fixture-baseline',
    retriever_track: 'fts5_baseline',
    evidence_ids: candidate.evidence_ids.split('|').reverse().join('|'),
    prototype_sha256: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
  };
  const bridge = {
    ...RESEARCH_BRIDGE_FIXTURE,
    prototypes: [candidate, baseline],
  };
  const candidatePackage = buildTemplateLockedScenario(bridge, {
    topic_id: 'airway',
    seed: 77,
    retriever_track: 'hybrid_cc_loto',
  });
  const baselinePackage = buildTemplateLockedScenario(bridge, {
    topic_id: 'airway',
    seed: 77,
    retriever_track: 'fts5_baseline',
  });
  assert.deepEqual(candidatePackage.scenario, baselinePackage.scenario);
  assert.deepEqual(candidatePackage.route, baselinePackage.route);
  assert.notEqual(candidatePackage.build.build_id, baselinePackage.build.build_id);
  assert.notEqual(candidatePackage.certificate.package_sha256, baselinePackage.certificate.package_sha256);
});
