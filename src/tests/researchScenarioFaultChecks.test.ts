import test from 'node:test';
import assert from 'node:assert/strict';
import { contentFingerprint } from '../scenario-generation/canonical';
import { generateResearchScenario } from '../scenario-generation/generator';
import { validateNarrativeDraft } from '../scenario-generation/narrativeProvider';
import { validateGeneratedResearchScenario } from '../scenario-generation/validator';
import type { GeneratedResearchScenario } from '../scenario-generation/types';
import { RESEARCH_BRIDGE_FIXTURE } from '../test-fixtures/researchBridge.fixture';

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function rehash(value: GeneratedResearchScenario): GeneratedResearchScenario {
  const { content_fingerprint: _ignored, ...rest } = value;
  return { ...value, content_fingerprint: contentFingerprint(rest) };
}

const baseline = generateResearchScenario(RESEARCH_BRIDGE_FIXTURE, { topic_id: 'airway', seed: 7 });

const faults: Array<[string, (value: GeneratedResearchScenario) => void]> = [
  ['authority', (value) => { (value.authority as { clinical_authority: string }).clinical_authority = 'GRANTED'; }],
  ['scoring', (value) => { (value.authority as { scoring_enabled: boolean }).scoring_enabled = true; }],
  ['actions', (value) => { value.scenario.expected_actions.critical.push({ id: 'x', label: 'x', priority: 'critical', synonyms: [], points: 1 }); }],
  ['vitals', (value) => { value.scenario.patients[0]!.initial_vitals.spo2 = 150; }],
  ['citation', (value) => { value.evidence[0]!.chunk_sha256 = 'not-a-hash'; }],
  ['profile', (value) => { value.scenario.patients[0]!.injury_profile_refs = ['not_registered']; }],
];

for (const [name, alter] of faults) {
  test(`rejects an altered ${name} invariant`, () => {
    const candidate = clone(baseline);
    alter(candidate);
    assert.equal(validateGeneratedResearchScenario(rehash(candidate)).status, 'FAIL');
  });
}

test('narrative adapter rejects unsupported authority-bearing fields', () => {
  for (const candidate of [
    { expected_actions: [] },
    { medication_dose: 'x' },
    { scoring_rule: 'x' },
    { provider_scope: 'x' },
  ]) {
    assert.throws(() => validateNarrativeDraft(candidate));
  }
});
