#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, resolve, sep } from 'node:path';

function parseArgs(argv) {
  const result = { repo: '.', jsonOutput: 'reports/operational-scenario-pack-node.json' };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (item === '--repo') result.repo = argv[++index];
    else if (item === '--json-output') result.jsonOutput = argv[++index];
    else throw new Error(`unknown argument:${item}`);
  }
  return result;
}

function canonical(value) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new Error('non-integer number in canonical artifact');
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  }
  throw new Error(`unsupported canonical value:${typeof value}`);
}

function sha(value) {
  return createHash('sha256').update(canonical(value), 'utf8').digest('hex');
}

function safeRepoPath(root, value, label) {
  if (typeof value !== 'string' || !value || value.includes('\0') || value.includes('\\') || isAbsolute(value)) throw new Error(`unsafe repository path:${label}`);
  const parts = value.split('/');
  if (parts.some((part) => !part || part === '.' || part === '..' || part.includes(':') || part.endsWith(' ') || part.endsWith('.'))) throw new Error(`unsafe repository path:${label}`);
  const candidate = resolve(root, ...parts);
  const prefix = root.endsWith(sep) ? root : `${root}${sep}`;
  if (candidate !== root && !candidate.startsWith(prefix)) throw new Error(`repository path escapes root:${label}`);
  return candidate;
}

function readJson(path) { return JSON.parse(readFileSync(path, 'utf8')); }
function writeJsonAtomic(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.tmp-${process.pid}`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  renameSync(temporary, path);
}

const COMPILED_REQUIRED_PROFILES = Object.freeze([
  'DIRECT_HANDOFF_BASELINE',
  'COMMUNICATION_RELAY_REQUIRED',
  'RESOURCE_COORDINATION_REQUIRED',
  'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
]);

const PROFILE_LABELS = {
  DIRECT_HANDOFF_BASELINE: 'Direct handoff',
  COMMUNICATION_RELAY_REQUIRED: 'Communications relay',
  RESOURCE_COORDINATION_REQUIRED: 'Resource coordination',
  DUAL_CONSTRAINT_RELAY_AND_COORDINATION: 'Relay and resource coordination',
};
const PROFILE_FOCUS = {
  DIRECT_HANDOFF_BASELINE: ['establish the operational picture', 'complete a traceable direct handoff', 'close the evolution without an unsafe branch'],
  COMMUNICATION_RELAY_REQUIRED: ['recognize degraded communications', 'establish an intermediate relay', 'preserve information through the final handoff'],
  RESOURCE_COORDINATION_REQUIRED: ['recognize resource contention', 'coordinate the constrained resource', 'complete handoff after the resource step'],
  DUAL_CONSTRAINT_RELAY_AND_COORDINATION: ['manage simultaneous communications and resource constraints', 'sequence relay before resource coordination', 'preserve a closed-loop final handoff'],
};

function selectionKey(candidate) {
  const context = candidate.context_signature ?? {};
  return [String(candidate.topic_id ?? ''), String(context.location ?? ''), String(candidate.context_signature_sha256 ?? ''), Number(candidate.seed ?? 0), String(candidate.candidate_id ?? '')];
}
function compareArrays(left, right) {
  for (let index = 0; index < Math.max(left.length, right.length); index += 1) {
    if (left[index] === right[index]) continue;
    if (typeof left[index] === 'number' && typeof right[index] === 'number') return left[index] - right[index];
    return String(left[index]).localeCompare(String(right[index]));
  }
  return 0;
}
function chooseCandidates(candidates, count) {
  const remaining = [...candidates].sort((left, right) => compareArrays(selectionKey(left), selectionKey(right)));
  const chosen = [];
  const topics = new Set(); const locations = new Set(); const contexts = new Set();
  while (remaining.length && chosen.length < count) {
    remaining.sort((left, right) => {
      const lc = left.context_signature ?? {}; const rc = right.context_signature ?? {};
      const lr = [topics.has(String(left.topic_id ?? '')) ? 1 : 0, locations.has(String(lc.location ?? '')) ? 1 : 0, contexts.has(String(left.context_signature_sha256 ?? '')) ? 1 : 0, ...selectionKey(left)];
      const rr = [topics.has(String(right.topic_id ?? '')) ? 1 : 0, locations.has(String(rc.location ?? '')) ? 1 : 0, contexts.has(String(right.context_signature_sha256 ?? '')) ? 1 : 0, ...selectionKey(right)];
      return compareArrays(lr, rr);
    });
    const selected = remaining.shift();
    chosen.push(selected);
    topics.add(String(selected.topic_id ?? ''));
    locations.add(String(selected.context_signature?.location ?? ''));
    contexts.add(String(selected.context_signature_sha256 ?? ''));
  }
  if (chosen.length !== count) throw new Error(`insufficient candidates for pack:${chosen.length}:${count}`);
  return chosen;
}

function buildCatalog(policy, archive) {
  const body = { ...policy }; delete body.policy_sha256;
  if (policy.policy_sha256 !== sha(body)) throw new Error('operational pack policy self hash differs');
  if (archive.classification !== 'PASS' || archive.status !== 'PASS') throw new Error('behavioral archive is not passing');
  if (!/^[0-9a-f]{64}$/.test(String(archive.archive_root_sha256 ?? ''))) throw new Error('behavioral archive root is invalid');
  const archiveBody = { ...archive }; delete archiveBody.archive_root_sha256;
  if (archive.archive_root_sha256 !== sha(archiveBody)) throw new Error('behavioral archive root differs');
  if (canonical(policy.required_profiles) !== canonical(COMPILED_REQUIRED_PROFILES)) throw new Error('required operational profile inventory differs');
  const entries = [];
  for (const profile of policy.required_profiles) {
    const group = archive.candidates.filter((item) => item.operational_behavior_profile_id === profile);
    chooseCandidates(group, policy.entries_per_profile).forEach((candidate, offset) => {
      const context = candidate.context_signature;
      const entryBody = {
        schema_version: '1.0.0',
        candidate_id: candidate.candidate_id,
        source_scenario_id: candidate.source_scenario_id,
        topic_id: candidate.topic_id,
        seed: candidate.seed,
        operational_behavior_profile_id: profile,
        profile_label: PROFILE_LABELS[profile],
        title: `${PROFILE_LABELS[profile]} — ${String(context.location).replace(/\b\w/g, (letter) => letter.toUpperCase())}`,
        plain_language_summary: `A fictional healthcare-simulation exercise in ${context.location} with ${context.communications} communications and ${context.resources} resources.`,
        context: {
          location: context.location,
          weather: context.weather,
          visibility: context.visibility,
          communications: context.communications,
          resources: context.resources,
          resource_event: context.resource_event,
        },
        learning_focus: PROFILE_FOCUS[profile],
        reproducibility: {
          package_sha256: candidate.package_sha256,
          context_signature_sha256: candidate.context_signature_sha256,
          policy_signature_sha256: candidate.policy_signature_sha256,
          equivalence_class_id: candidate.equivalence_class_id,
        },
        authority: {
          healthcare_simulation: 'PERMITTED_WITHIN_VALIDATED_SCOPE',
          direct_patient_care: 'PROHIBITED',
          clinical_decision_support: 'PROHIBITED',
          operational_timing: 'NOT_CALIBRATED',
          scoring_state: 'SOURCE_CONFORMANCE_ONLY',
          treatment_state: 'NO_SIMULATION_ADMITTED_CONCRETE_TREATMENT',
        },
        profile_sequence: offset + 1,
      };
      entries.push({ catalog_entry_id: `ASK-OP-${sha(entryBody).slice(0, 16).toUpperCase()}`, ...entryBody });
    });
  }
  entries.sort((left, right) => {
    const profile = policy.required_profiles.indexOf(left.operational_behavior_profile_id) - policy.required_profiles.indexOf(right.operational_behavior_profile_id);
    return profile || left.profile_sequence - right.profile_sequence || left.catalog_entry_id.localeCompare(right.catalog_entry_id);
  });
  const profileCounts = Object.fromEntries(policy.required_profiles.map((profile) => [profile, entries.filter((item) => item.operational_behavior_profile_id === profile).length]));
  if (entries.length !== policy.required_total_entries) throw new Error('operational scenario pack size differs');
  if (new Set(entries.map((item) => item.candidate_id)).size !== entries.length) throw new Error('operational scenario pack contains duplicate candidates');
  const withoutHash = {
    schema_version: '1.0.0', classification: 'PASS', status: 'PASS',
    catalog_id: policy.catalog_id, catalog_profile: policy.catalog_profile, selection_profile: policy.selection_profile,
    policy_id: policy.policy_id, policy_epoch: policy.policy_epoch, policy_sha256: policy.policy_sha256,
    source_archive_path: policy.source_archive_path, source_archive_root_sha256: archive.archive_root_sha256,
    entry_count: entries.length, profile_counts: profileCounts, entries,
    stakeholder_surfaces: policy.stakeholder_surfaces, truth_boundaries: policy.admission_boundaries,
  };
  return { ...withoutHash, catalog_root_sha256: sha(withoutHash) };
}

let errors = [];
try {
  const args = parseArgs(process.argv.slice(2));
  const root = resolve(args.repo);
  const policy = readJson(safeRepoPath(root, 'config/scenario-science/OPERATIONAL_SCENARIO_PACK_POLICY.json', 'policy'));
  const archive = readJson(safeRepoPath(root, policy.source_archive_path, 'source_archive_path'));
  const observed = readJson(safeRepoPath(root, policy.output_path, 'output_path'));
  const expected = buildCatalog(policy, archive);
  if (canonical(observed) !== canonical(expected)) errors.push('operational scenario catalog differs from independent reconstruction');
  const result = { schema_version: '1.0.0', classification: errors.length ? 'FAIL' : 'PASS', status: errors.length ? 'FAIL' : 'PASS', checker: 'INDEPENDENT_NODE_STDLIB_RECONSTRUCTION_V1', catalog_id: expected.catalog_id, entries: expected.entry_count, catalog_root_sha256: expected.catalog_root_sha256, errors };
  writeJsonAtomic(safeRepoPath(root, args.jsonOutput, 'json_output'), result);
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  errors.push(error instanceof Error ? error.message : String(error));
  console.log(JSON.stringify({ schema_version: '1.0.0', classification: 'FAIL', status: 'FAIL', checker: 'INDEPENDENT_NODE_STDLIB_RECONSTRUCTION_V1', errors }, null, 2));
}
process.exit(errors.length ? 3 : 0);
