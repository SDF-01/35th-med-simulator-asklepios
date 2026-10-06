import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { ResearchRuntimeBridge } from '../src/research/types';
import { contentFingerprint } from '../src/scenario-generation/canonical';
import { generateResearchScenario } from '../src/scenario-generation/generator';
import { validateNarrativeDraft } from '../src/scenario-generation/narrativeProvider';
import { TOPIC_PROFILES } from '../src/scenario-generation/topicProfiles';
import { validateGeneratedResearchScenario } from '../src/scenario-generation/validator';
import type { GeneratedResearchScenario, ScenarioEvidenceTopic } from '../src/scenario-generation/types';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const bridge = JSON.parse(
  readFileSync(resolve(root, 'public/data/research_sandbox/runtime_bridge.json'), 'utf8'),
) as ResearchRuntimeBridge;

function require(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function repairFingerprint(value: GeneratedResearchScenario): GeneratedResearchScenario {
  const { content_fingerprint: _ignored, ...rest } = value;
  return { ...value, content_fingerprint: contentFingerprint(rest) };
}

const availableTopics = [...new Set(bridge.prototypes.map((item) => item.topic_id))]
  .filter((topic): topic is ScenarioEvidenceTopic => topic in TOPIC_PROFILES);
require(availableTopics.length > 0, 'Bridge contains no supported topics.');

let generatedCount = 0;
let relationChecks = 0;
let seededCases = 0;
let rejectedFaults = 0;

for (const topic of availableTopics) {
  for (let seed = 1; seed <= 64; seed += 1) {
    const request = { topic_id: topic, seed, retriever_track: bridge.retrieval_release.default_research_sandbox_retriever } as const;
    const generated = generateResearchScenario(bridge, request);
    require(validateGeneratedResearchScenario(generated).status === 'PASS', `${topic}/${seed} failed validation.`);
    const repeated = generateResearchScenario(bridge, request);
    require(JSON.stringify(generated) === JSON.stringify(repeated), `${topic}/${seed} is not reproducible.`);
    seededCases += 1;
    relationChecks += 1;
  }
  generatedCount += 1;
}

const topic = availableTopics[0]!;
const request = { topic_id: topic, seed: 20260727, retriever_track: bridge.retrieval_release.default_research_sandbox_retriever } as const;
const baseline = generateResearchScenario(bridge, request);

const reordered = {
  ...bridge,
  sources: [...bridge.sources].reverse(),
  evidence_refs: [...bridge.evidence_refs].reverse(),
  prototypes: [...bridge.prototypes].reverse(),
};
require(
  JSON.stringify(baseline) === JSON.stringify(generateResearchScenario(reordered, request)),
  'Reordering bridge arrays changed the generated scenario.',
);
relationChecks += 1;

const unrelated = clone(bridge);
unrelated.sources.push({
  source_index: 99999,
  source_id: 'unrelated',
  title: 'Unrelated administrative source',
  journal: 'Fixture',
  doi: '10.0000/unrelated',
  publication_date: '2026-01-01',
  source_file_sha256: 'a'.repeat(64),
});
require(
  JSON.stringify(baseline) === JSON.stringify(generateResearchScenario(unrelated, request)),
  'Adding an unrelated source changed the generated scenario.',
);
relationChecks += 1;

const changedSeed = generateResearchScenario(bridge, { ...request, seed: request.seed + 1 });
require(changedSeed.content_fingerprint !== baseline.content_fingerprint, 'Changing the seed did not change the fingerprint.');
require(validateGeneratedResearchScenario(changedSeed).status === 'PASS', 'Changed-seed scenario failed validation.');
relationChecks += 2;

const faultCases: Array<[string, (value: GeneratedResearchScenario) => void]> = [
  ['clinical authority', (value) => { (value.authority as { clinical_authority: string }).clinical_authority = 'GRANTED'; }],
  ['scoring', (value) => { (value.authority as { scoring_enabled: boolean }).scoring_enabled = true; }],
  ['critical action', (value) => { value.scenario.expected_actions.critical.push({ id: 'bad', label: 'Bad', priority: 'critical', synonyms: [], points: 1 }); }],
  ['invalid heart rate', (value) => { value.scenario.patients[0]!.initial_vitals.hr = 999; }],
  ['unknown injury', (value) => { value.scenario.patients[0]!.injury_profile_refs = ['unknown_profile']; }],
  ['broken chunk hash', (value) => { value.evidence[0]!.chunk_sha256 = 'bad'; }],
  ['duplicate patient', (value) => { value.scenario.patients.push(clone(value.scenario.patients[0]!)); value.scenario.casualty_count = 2; }],
  ['unknown evidence trace', (value) => { value.field_provenance[0]!.evidence_ids.push('missing-evidence'); }],
];

for (const [label, alter] of faultCases) {
  const candidate = clone(baseline);
  alter(candidate);
  const repaired = repairFingerprint(candidate);
  require(validateGeneratedResearchScenario(repaired).status === 'FAIL', `Validator accepted injected fault: ${label}.`);
  rejectedFaults += 1;
}

for (const draft of [
  { expected_actions: [] },
  { medication_dose: 'unsupported' },
  { scoring_rule: 'unsupported' },
  { physiology_transition: 'unsupported' },
]) {
  let rejected = false;
  try { validateNarrativeDraft(draft); } catch { rejected = true; }
  require(rejected, `Narrative filter accepted unsupported keys: ${Object.keys(draft).join(', ')}`);
  rejectedFaults += 1;
}

console.log(JSON.stringify({
  status: 'PASS',
  supported_topics_checked: availableTopics.length,
  seed_cases: seededCases,
  relation_checks: relationChecks,
  injected_faults_rejected: rejectedFaults,
  example_scenario: baseline.scenario.scenario_id,
  example_fingerprint: baseline.content_fingerprint,
  clinical_authority: baseline.authority.clinical_authority,
  scoring_enabled: baseline.authority.scoring_enabled,
}, null, 2));
