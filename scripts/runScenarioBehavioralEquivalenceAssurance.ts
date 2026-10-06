import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { ResearchRuntimeBridge } from '../src/research/types';
import type { ScenarioEvidenceTopic } from '../src/scenario-generation/types';
import { buildTemplateLockedScenario } from '../src/scenario-core/assembly';
import { buildScenarioBehavioralEquivalenceArchive } from '../src/scenario-core/behavioralEquivalence';
import { canonicalJson, sha256Canonical } from '../src/scenario-core/hash';
import type { ScenarioOperationalBehaviorProfileId } from '../src/scenario-core/behaviorProfiles';

interface BehavioralDiversityPolicy {
  schema_version: '1.0.0';
  policy_id: string;
  policy_epoch: number;
  policy_sha256: string;
  archive_profile: string;
  policy_signature_profile: string;
  required_operational_profiles: ScenarioOperationalBehaviorProfileId[];
  ratchet_floors: {
    minimum_candidates: number;
    minimum_unique_context_signatures: number;
    minimum_policy_equivalence_classes: number;
    minimum_policy_novelty_ratio_bps: number;
    minimum_contexts_per_policy_class: number;
    maximum_reachable_nonterminal_dead_ends: number;
  };
  authority_boundaries: Record<string, string>;
  output_path: string;
}

interface ExperienceReport {
  classification: string;
  status: string;
  generated_cases: number;
  realized_rows: Array<{ topic: ScenarioEvidenceTopic; seed: number }>;
}

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

function assertCondition(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

async function loadJson<T>(relative: string): Promise<T> {
  return JSON.parse(await readFile(resolve(root, relative), 'utf8')) as T;
}

async function atomicWriteJson(relative: string, value: unknown): Promise<void> {
  const output = resolve(root, relative);
  const temporary = `${output}.tmp-${process.pid}`;
  await mkdir(dirname(output), { recursive: true });
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  await rename(temporary, output);
}

async function main(): Promise<void> {
  const policy = await loadJson<BehavioralDiversityPolicy>('config/scenario-science/BEHAVIORAL_DIVERSITY_POLICY.json');
  const { policy_sha256: observedPolicyHash, ...policyBody } = policy;
  assertCondition(observedPolicyHash === sha256Canonical(policyBody), 'Behavioral-diversity policy self-hash differs.');

  const bridge = await loadJson<ResearchRuntimeBridge>('public/data/research_sandbox/runtime_bridge.json');
  const experience = await loadJson<ExperienceReport>('reports/scenario-experience-assurance.json');
  assertCondition(experience.classification === 'PASS' && experience.status === 'PASS', 'Scenario-experience evidence is not passing.');
  assertCondition(experience.generated_cases === experience.realized_rows.length, 'Scenario-experience row inventory differs.');

  const generated = experience.realized_rows.map(({ topic, seed }) => buildTemplateLockedScenario(bridge, {
    topic_id: topic,
    seed,
    retriever_track: bridge.retrieval_release.default_research_sandbox_retriever,
  }));
  const archive = buildScenarioBehavioralEquivalenceArchive(generated);
  const summary = archive.summary;
  const observedProfiles = summary.operational_behavior_profiles_observed;
  const requiredProfiles = [...policy.required_operational_profiles].sort();

  assertCondition(archive.archive_profile === policy.archive_profile, 'Behavioral archive profile differs from policy.');
  assertCondition(archive.policy_profile === policy.policy_signature_profile, 'Behavioral signature profile differs from policy.');
  assertCondition(canonicalJson(archive.truth_boundaries) === canonicalJson(policy.authority_boundaries), 'Behavioral authority boundaries differ from policy.');
  assertCondition(summary.candidate_count >= policy.ratchet_floors.minimum_candidates, 'Behavioral candidate floor regressed.');
  assertCondition(summary.unique_context_signatures >= policy.ratchet_floors.minimum_unique_context_signatures, 'Behavioral context floor regressed.');
  assertCondition(summary.policy_equivalence_classes >= policy.ratchet_floors.minimum_policy_equivalence_classes, 'Behavioral policy-class floor regressed.');
  assertCondition(summary.policy_novelty_ratio_bps >= policy.ratchet_floors.minimum_policy_novelty_ratio_bps, 'Behavioral novelty-ratio floor regressed.');
  assertCondition(summary.minimum_contexts_in_one_policy_class >= policy.ratchet_floors.minimum_contexts_per_policy_class, 'Behavioral class context floor regressed.');
  assertCondition(canonicalJson(observedProfiles) === canonicalJson(requiredProfiles), 'Required operational behavior profiles are not all represented.');
  assertCondition(archive.equivalence_classes.every((item) => item.context_signature_count > 0), 'Behavioral policy class is empty.');
  assertCondition(new Set(archive.equivalence_classes.map((item) => item.operational_behavior_profile_id)).size === archive.equivalence_classes.length, 'A reviewed operational profile occupies multiple policy classes.');

  await atomicWriteJson(policy.output_path, archive);
  const report = {
    schema_version: '1.0.0',
    classification: 'PASS',
    status: 'PASS',
    assurance_profile: 'CONTEXT_POLICY_SEPARATION_AND_OPERATIONAL_PROFILE_RATCHET_V1',
    policy_id: policy.policy_id,
    policy_epoch: policy.policy_epoch,
    policy_sha256: policy.policy_sha256,
    archive_path: policy.output_path,
    archive_root_sha256: archive.archive_root_sha256,
    candidate_count: summary.candidate_count,
    unique_context_signatures: summary.unique_context_signatures,
    policy_equivalence_classes: summary.policy_equivalence_classes,
    policy_novelty_ratio_bps: summary.policy_novelty_ratio_bps,
    operational_behavior_profiles: observedProfiles,
    context_only_variant_count: summary.context_only_variant_count,
    truth_boundaries: archive.truth_boundaries,
  };
  await atomicWriteJson('reports/scenario-behavioral-equivalence-generation.json', report);
  console.log(JSON.stringify(report, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exitCode = 1;
});
