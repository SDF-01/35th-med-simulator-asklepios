import test from 'node:test';
import assert from 'node:assert/strict';
import { scenariosById } from '../content/scenarios';
import { verifyScenarioPackage } from '../scenario-checker/verify';
import { buildTemplateLockedScenario } from '../scenario-core/assembly';
import { sha256Text } from '../scenario-core/hash';
import { protectedScenarioProjection } from '../scenario-core/projection';
import { validateScenarioPackage } from '../scenario-core/validator';
import { RESEARCH_BRIDGE_FIXTURE } from '../test-fixtures/researchBridge.fixture';

const request = { topic_id: 'airway' as const, seed: 41027, retriever_track: 'hybrid_cc_loto' };

test('SHA-256 implementation matches standard vectors', () => {
  assert.equal(
    sha256Text(''),
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  );
  assert.equal(
    sha256Text('abc'),
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
  );
});

test('builds a deterministic template-locked scenario with a valid certificate', async () => {
  const first = buildTemplateLockedScenario(RESEARCH_BRIDGE_FIXTURE, request);
  const second = buildTemplateLockedScenario(RESEARCH_BRIDGE_FIXTURE, request);
  assert.deepEqual(first, second);
  assert.equal(validateScenarioPackage(first).status, 'PASS');
  const base = scenariosById[first.build.source_scenario_id]!;
  assert.deepEqual(protectedScenarioProjection(first.scenario), protectedScenarioProjection(base));
  assert.equal((await verifyScenarioPackage(base, first)).status, 'PASS');
  assert.equal(first.evidence.length, 6);
  assert.equal(first.certificate.checks.protected_fields_unchanged, true);
  assert.equal(first.certificate.checks.route_has_reachable_terminal, true);
});
