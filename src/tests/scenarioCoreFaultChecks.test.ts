import test from 'node:test';
import assert from 'node:assert/strict';
import { scenariosById } from '../content/scenarios';
import { verifyScenarioPackage } from '../scenario-checker/verify';
import { buildTemplateLockedScenario } from '../scenario-core/assembly';
import { assertAcceptedScenarioBuildProposal, validateScenarioBuildProposal } from '../scenario-core/proposal';
import { validateScenarioPackage } from '../scenario-core/validator';
import type { VerifiedScenarioPackage } from '../scenario-core/types';
import { RESEARCH_BRIDGE_FIXTURE } from '../test-fixtures/researchBridge.fixture';

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const baseline = buildTemplateLockedScenario(RESEARCH_BRIDGE_FIXTURE, {
  topic_id: 'airway',
  seed: 7,
  retriever_track: 'hybrid_cc_loto',
});
const baseScenario = scenariosById[baseline.build.source_scenario_id]!;

const alterations: Array<[string, (value: VerifiedScenarioPackage) => void]> = [
  ['protected action', (value) => { value.scenario.expected_actions.critical[0]!.points += 1; }],
  ['route destination', (value) => { value.route.edges[0]!.to = 'missing'; }],
  ['ambiguous route trigger', (value) => {
    const original = value.route.edges[0]!;
    value.route.edges.push({ ...original, edge_id: 'ambiguous-trigger', to: value.route.edges[1]!.to, priority: original.priority - 1 });
  }],
  ['field origin', (value) => { value.field_origins = value.field_origins.filter((origin) => origin.field_path !== 'scenario.operational_context.weather'); }],
  ['stage chain', (value) => { value.stages[2]!.input_sha256 = '0'.repeat(64); }],
  ['evidence hash', (value) => { value.evidence[0]!.chunk_sha256 = '1'.repeat(64); }],
  ['authority', (value) => { (value.authority as { evidence_authority: string }).evidence_authority = 'governing'; }],
  ['package hash', (value) => { value.certificate.package_sha256 = 'f'.repeat(64); }],
];

for (const [label, alter] of alterations) {
  test(`rejects altered ${label}`, async () => {
    const candidate = clone(baseline);
    alter(candidate);
    const local = validateScenarioPackage(candidate);
    const independent = await verifyScenarioPackage(baseScenario, candidate);
    assert.ok(local.status === 'FAIL' || independent.status === 'FAIL');
    assert.equal(independent.status, 'FAIL');
  });
}

test('build-time proposal parser rejects protected or authority-bearing fields', () => {
  for (const candidate of [
    { expected_actions: [] },
    { scoring_rules: [] },
    { medication_doses: [] },
    { physiology_transitions: [] },
    { provider_scope: [] },
  ]) {
    assert.throws(() => validateScenarioBuildProposal(candidate));
  }
});


test('build-time proposal parser rejects hidden clinical or executable content', () => {
  const base = {
    proposal_version: '1.0.0',
    source_scenario_id: 'ASK-A-001',
    review: {
      status: 'accepted',
      reviewer: 'reviewer-1',
      reviewed_at_utc: '2026-07-27T00:00:00Z',
      source_scenario_sha256: 'a'.repeat(64),
    },
  };
  for (const candidate of [
    { ...base, resource_event_options: ['Administer 10 mg now'] },
    { ...base, location_options: ['<script>alert(1)</script>'] },
    { ...base, proposed_title_suffix: 'Score 10 points' },
  ]) {
    assert.throws(() => validateScenarioBuildProposal(candidate));
  }
});

test('only an accepted proposal bound to the exact source revision is admitted', () => {
  const accepted = {
    proposal_version: '1.0.0',
    source_scenario_id: 'ASK-A-001',
    location_options: ['damaged operations perimeter'],
    review: {
      status: 'accepted',
      reviewer: 'reviewer-1',
      reviewed_at_utc: '2026-07-27T00:00:00Z',
      source_scenario_sha256: 'a'.repeat(64),
    },
  };
  assert.equal(
    assertAcceptedScenarioBuildProposal(accepted, 'ASK-A-001', 'a'.repeat(64)).review.status,
    'accepted',
  );
  assert.throws(() => assertAcceptedScenarioBuildProposal(
    { ...accepted, review: { ...accepted.review, status: 'pending' } },
    'ASK-A-001',
    'a'.repeat(64),
  ));
  assert.throws(() => assertAcceptedScenarioBuildProposal(accepted, 'ASK-A-002', 'a'.repeat(64)));
  assert.throws(() => assertAcceptedScenarioBuildProposal(accepted, 'ASK-A-001', 'b'.repeat(64)));
});


test('missing requested retriever track fails closed', () => {
  assert.throws(() => buildTemplateLockedScenario(RESEARCH_BRIDGE_FIXTURE, {
    topic_id: 'airway',
    seed: 7,
    retriever_track: 'missing-track',
  }));
});
