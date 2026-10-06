import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { scenariosById } from '../src/content/scenarios';
import { SCENARIO_BLUEPRINTS } from '../src/scenario-core/blueprints';
import { sha256Canonical } from '../src/scenario-core/hash';
import { protectedScenarioProjection } from '../src/scenario-core/projection';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

async function writeJson(relative: string, value: unknown): Promise<void> {
  const path = resolve(root, relative);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

const snapshots = SCENARIO_BLUEPRINTS.map((blueprint) => {
  const scenario = scenariosById[blueprint.source_scenario_id];
  if (!scenario) throw new Error(`Missing source scenario ${blueprint.source_scenario_id}.`);
  return {
    schema_version: '1.0.0',
    source_scenario_id: scenario.scenario_id,
    source_scenario_sha256: sha256Canonical(scenario),
    protected_projection_sha256: sha256Canonical(protectedScenarioProjection(scenario)),
    scenario,
  };
});

for (const snapshot of snapshots) {
  await writeJson(`config/scenario-contracts/${snapshot.source_scenario_id}.json`, snapshot);
}

const catalog = {
  schema_version: '1.0.0',
  catalog_id: 'scenario-blueprint-catalog-v1',
  blueprints: SCENARIO_BLUEPRINTS.map((blueprint) => ({
    ...blueprint,
    blueprint_sha256: sha256Canonical(blueprint),
    source_contract: snapshots.find((item) => item.source_scenario_id === blueprint.source_scenario_id),
  })),
};

await writeJson('public/data/scenario_core/blueprint_catalog.json', catalog);
await writeJson('reports/scenario-blueprint-catalog.json', {
  status: 'PASS',
  blueprints: catalog.blueprints.length,
  source_scenarios: snapshots.length,
  catalog_sha256: sha256Canonical(catalog),
});

console.log('\n================ SCENARIO BLUEPRINT CATALOG ================');
console.log(JSON.stringify({
  status: 'PASS',
  blueprints: catalog.blueprints.length,
  source_scenarios: snapshots.length,
  catalog_sha256: sha256Canonical(catalog),
}, null, 2));
console.log('============================================================');
