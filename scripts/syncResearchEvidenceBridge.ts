import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

interface BridgeShape {
  contains_licensed_source_text: boolean;
  authority: {
    clinical_authority: string;
    scoring_enabled: boolean;
    unscored_research_sandbox_only: boolean;
  };
  sources: unknown[];
  evidence_refs: unknown[];
  prototypes: unknown[];
}

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const argument = process.argv.find((value) => value.startsWith('--scrape-repo='));
const scrapeRoot = resolve(
  argument?.split('=', 2)[1]
    ?? process.env.ASKLEPIOS_SCRAPE_REPO
    ?? resolve(appRoot, '..', 'Project-Asklepios-Scrape'),
);
const sourceCandidates = [
  resolve(scrapeRoot, 'data/public/runtime_bridge_v2/runtime_bridge.compact.json'),
  resolve(scrapeRoot, 'data/public/runtime_bridge_v2/runtime_bridge.json'),
];
const source = sourceCandidates.find(existsSync);
if (!source) {
  throw new Error(`No public runtime bridge was found under ${scrapeRoot}.`);
}

const raw = readFileSync(source, 'utf8');
const payload = JSON.parse(raw) as BridgeShape;
if (
  payload.contains_licensed_source_text !== false ||
  payload.authority?.clinical_authority !== 'NOT_GRANTED' ||
  payload.authority?.scoring_enabled !== false ||
  payload.authority?.unscored_research_sandbox_only !== true
) {
  throw new Error('Source bridge failed the public authority boundary.');
}
if (!Array.isArray(payload.sources) || !Array.isArray(payload.evidence_refs) || !Array.isArray(payload.prototypes)) {
  throw new Error('Source bridge is structurally incomplete.');
}

const destination = resolve(appRoot, 'public/data/research_sandbox/runtime_bridge.json');
mkdirSync(dirname(destination), { recursive: true });
copyFileSync(source, destination);
writeFileSync(
  resolve(appRoot, 'public/data/research_sandbox/sync_receipt.json'),
  `${JSON.stringify({
    schema_version: '1.0.0',
    source_path: source,
    sources: payload.sources.length,
    evidence_refs: payload.evidence_refs.length,
    prototypes: payload.prototypes.length,
    contains_licensed_source_text: false,
    clinical_authority: 'NOT_GRANTED',
    scoring_enabled: false,
  }, null, 2)}\n`,
  'utf8',
);
console.log(`Synced citation-only bridge from ${source}`);
console.log(`Sources: ${payload.sources.length}; evidence refs: ${payload.evidence_refs.length}; prototypes: ${payload.prototypes.length}`);
