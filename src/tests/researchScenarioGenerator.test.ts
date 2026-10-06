import test from 'node:test';
import assert from 'node:assert/strict';
import { generateResearchScenario } from '../scenario-generation/generator';
import { validateGeneratedResearchScenario } from '../scenario-generation/validator';
import { RESEARCH_BRIDGE_FIXTURE } from '../test-fixtures/researchBridge.fixture';

test('generates a deterministic app-compatible unscored scenario', () => {
  const request = { topic_id: 'airway' as const, seed: 20260727, retriever_track: 'hybrid_cc_loto' };
  const first = generateResearchScenario(RESEARCH_BRIDGE_FIXTURE, request);
  const second = generateResearchScenario(RESEARCH_BRIDGE_FIXTURE, request);
  assert.deepEqual(first, second);
  assert.equal(validateGeneratedResearchScenario(first).status, 'PASS');
  assert.equal(first.scenario.casualty_count, first.scenario.patients.length);
  assert.equal(first.scenario.expected_actions.critical.length, 0);
  assert.equal(first.scenario.expected_actions.unsafe.length, 0);
  assert.equal(first.authority.clinical_authority, 'NOT_GRANTED');
  assert.equal(first.authority.scoring_enabled, false);
  assert.equal(first.evidence.length, 6);
});

test('changes content for a changed seed while retaining validity', () => {
  const first = generateResearchScenario(RESEARCH_BRIDGE_FIXTURE, { topic_id: 'airway', seed: 1 });
  const second = generateResearchScenario(RESEARCH_BRIDGE_FIXTURE, { topic_id: 'airway', seed: 2 });
  assert.notEqual(first.content_fingerprint, second.content_fingerprint);
  assert.equal(validateGeneratedResearchScenario(first).status, 'PASS');
  assert.equal(validateGeneratedResearchScenario(second).status, 'PASS');
});
