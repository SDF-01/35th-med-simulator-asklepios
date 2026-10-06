import test from 'node:test';
import assert from 'node:assert/strict';
import { scenariosById } from '../content/scenarios';
import { verifyScenarioPackage } from '../scenario-checker/verify';
import { buildTemplateLockedScenario } from '../scenario-core/assembly';
import { protectedScenarioProjection } from '../scenario-core/projection';
import { validateScenarioPackage } from '../scenario-core/validator';
import { RESEARCH_BRIDGE_FIXTURE } from '../test-fixtures/researchBridge.fixture';

test('a broad deterministic seed sweep preserves the source scaffold', async () => {
  const locations = new Set<string>();
  const weather = new Set<string>();
  const communications = new Set<string>();
  const resources = new Set<string>();
  const base = scenariosById['ASK-A-001']!;
  const protectedBase = protectedScenarioProjection(base);

  for (let seed = 0; seed < 512; seed += 1) {
    const generated = buildTemplateLockedScenario(RESEARCH_BRIDGE_FIXTURE, {
      topic_id: 'airway',
      seed,
      retriever_track: 'hybrid_cc_loto',
    });
    assert.equal(validateScenarioPackage(generated).status, 'PASS', `seed ${seed}`);
    assert.deepEqual(protectedScenarioProjection(generated.scenario), protectedBase);
    if (seed % 32 === 0) {
      assert.equal((await verifyScenarioPackage(base, generated)).status, 'PASS', `independent seed ${seed}`);
    }
    locations.add(generated.scenario.operational_context.location_type);
    weather.add(generated.scenario.operational_context.weather);
    communications.add(generated.scenario.operational_context.comms_status);
    resources.add(generated.scenario.operational_context.resource_status);
  }

  assert.ok(locations.size >= 1);
  assert.ok(weather.size >= 1);
  assert.ok(communications.size >= 1);
  assert.ok(resources.size >= 2);
});
