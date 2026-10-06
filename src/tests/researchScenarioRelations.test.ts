import test from 'node:test';
import assert from 'node:assert/strict';
import { generateResearchScenario } from '../scenario-generation/generator';
import { validateGeneratedResearchScenario } from '../scenario-generation/validator';
import { RESEARCH_BRIDGE_FIXTURE } from '../test-fixtures/researchBridge.fixture';

test('record ordering does not change the generated scenario', () => {
  const request = { topic_id: 'airway' as const, seed: 44, retriever_track: 'hybrid_cc_loto' };
  const baseline = generateResearchScenario(RESEARCH_BRIDGE_FIXTURE, request);
  const reordered = {
    ...RESEARCH_BRIDGE_FIXTURE,
    sources: [...RESEARCH_BRIDGE_FIXTURE.sources].reverse(),
    evidence_refs: [...RESEARCH_BRIDGE_FIXTURE.evidence_refs].reverse(),
    prototypes: [...RESEARCH_BRIDGE_FIXTURE.prototypes].reverse(),
  };
  assert.deepEqual(generateResearchScenario(reordered, request), baseline);
});

test('many deterministic seeds remain inside all safety and compatibility constraints', () => {
  for (let seed = 0; seed < 256; seed += 1) {
    const generated = generateResearchScenario(RESEARCH_BRIDGE_FIXTURE, {
      topic_id: 'airway', seed, retriever_track: 'hybrid_cc_loto',
    });
    const report = validateGeneratedResearchScenario(generated);
    assert.equal(report.status, 'PASS', `seed ${seed}: ${JSON.stringify(report.issues)}`);
  }
});
