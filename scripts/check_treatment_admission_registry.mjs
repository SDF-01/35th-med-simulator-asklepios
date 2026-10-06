#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { existsSync, lstatSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, resolve, sep } from 'node:path';

const STATE_ORDER = [
  'DISCOVERED', 'SOURCE_BYTES_VERIFIED', 'EVIDENCE_SPAN_BOUND', 'APPLICABILITY_REVIEWED',
  'CONTRAINDICATION_MODEL_REVIEWED', 'ROLE_SCOPE_BOUND', 'SIMULATED_EFFECT_ADJUDICATED',
  'INDEPENDENTLY_ATTESTED', 'SIMULATION_ADMITTED',
];
const BOUNDARIES = {
  healthcare_simulation: 'PERMITTED_WITHIN_VALIDATED_SCOPE', direct_patient_care: 'PROHIBITED',
  clinical_decision_support: 'PROHIBITED', patient_care_authority: 'NONE',
  automatic_treatment_activation: false, unadjudicated_treatment_visible_as_active_choice: false,
};
function canonical(value) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number') { if (!Number.isSafeInteger(value)) throw new Error('non-integer canonical number'); return JSON.stringify(value); }
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (typeof value === 'object') return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  throw new Error(`unsupported canonical value:${typeof value}`);
}
const sha = (value) => createHash('sha256').update(canonical(value), 'utf8').digest('hex');
function parseArgs(argv) {
  const result = { repo: '.', jsonOutput: 'reports/treatment-admission-registry-node.json' };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--repo') result.repo = argv[++index];
    else if (argv[index] === '--json-output') result.jsonOutput = argv[++index];
    else throw new Error(`unknown option:${argv[index]}`);
  }
  return result;
}
function safePath(root, value, label, required = false) {
  if (typeof value !== 'string' || !value || value.includes('\0') || value.includes('\\') || isAbsolute(value)) throw new Error(`unsafe repository path:${label}`);
  const parts = value.split('/');
  if (parts.some((part) => !part || part === '.' || part === '..' || part.includes(':') || part.endsWith(' ') || part.endsWith('.'))) throw new Error(`unsafe repository path:${label}`);
  let current = root;
  for (const part of parts.slice(0, -1)) { current = resolve(current, part); if (existsSync(current) && lstatSync(current).isSymbolicLink()) throw new Error(`symlinked repository parent:${label}`); }
  const candidate = resolve(root, ...parts); const prefix = root.endsWith(sep) ? root : `${root}${sep}`;
  if (candidate !== root && !candidate.startsWith(prefix)) throw new Error(`repository path escapes root:${label}`);
  if (existsSync(candidate) && lstatSync(candidate).isSymbolicLink()) throw new Error(`symlinked repository file:${label}`);
  if (required && !existsSync(candidate)) throw new Error(`required repository file missing:${label}`);
  return candidate;
}
function readJson(path) { return JSON.parse(readFileSync(path, 'utf8')); }
function writeJson(path, value) { mkdirSync(dirname(path), { recursive: true }); const temp = `${path}.tmp-${process.pid}`; writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, 'utf8'); renameSync(temp, path); }
function buildProjection(registry, profile) {
  const policies = new Map((profile.treatment_policies ?? []).map((item) => [item.treatment_id, item]));
  const entries = registry.entries.map((entry) => {
    const source = policies.get(entry.treatment_id) ?? {};
    const admitted = entry.current_state === 'SIMULATION_ADMITTED' && entry.simulation_admitted === true;
    return {
      treatment_id: entry.treatment_id, display_name: entry.display_name, facility_action_id: entry.facility_action_id,
      admission_state: entry.current_state, simulation_admitted: admitted,
      learner_choice_status: admitted ? 'AVAILABLE' : 'BLOCKED_PENDING_ADJUDICATION',
      governing_rule_status: entry.governing_rule_status, effect_model_status: entry.effect_model_status,
      missing_requirements: [...entry.missing_requirements], source_profile_activation_state: source.activation_state ?? 'MISSING',
      plain_language_limitation: admitted
        ? 'This treatment is admitted only for the declared healthcare-simulation scope and does not authorize real-patient care.'
        : 'This treatment is not yet an active learner choice because its governing evidence, applicability, scope, contraindications, simulated effect, and independent clinical review have not all been admitted.',
    };
  }).sort((a, b) => a.treatment_id.localeCompare(b.treatment_id));
  const body = {
    schema_version: '1.0.0', classification: 'PASS', status: 'PASS', registry_id: registry.registry_id,
    registry_epoch: registry.registry_epoch, registry_sha256: registry.registry_sha256, admission_profile: registry.admission_profile,
    state_order: [...registry.state_order], entry_count: entries.length,
    simulation_admitted_count: entries.filter((entry) => entry.simulation_admitted).length,
    active_learner_choice_count: entries.filter((entry) => entry.learner_choice_status === 'AVAILABLE').length,
    entries, boundaries: { ...registry.boundaries },
    truth_boundary: 'A discovered or source-mentioned treatment is not an active simulation choice. Activation requires exact source bytes, a bound evidence span, applicability and contraindication review, role/scope binding, an adjudicated simulated effect, and independent attestation. Direct patient care and clinical decision support remain prohibited.',
  };
  return { ...body, projection_sha256: sha(body) };
}

let errors = [];
let projection = null;
try {
  const args = parseArgs(process.argv.slice(2)); const root = resolve(args.repo);
  const registry = readJson(safePath(root, 'config/scenario-science/TREATMENT_ADMISSION_REGISTRY.json', 'registry', true));
  const body = { ...registry }; delete body.registry_sha256;
  if (registry.registry_sha256 !== sha(body)) errors.push('treatment registry self hash differs');
  if (canonical(registry.state_order) !== canonical(STATE_ORDER)) errors.push('treatment admission state order differs');
  if (canonical(registry.boundaries) !== canonical(BOUNDARIES)) errors.push('treatment admission authority boundaries differ');
  const profile = readJson(safePath(root, registry.source_profile_path, 'source_profile', true));
  const source = new Map((profile.treatment_policies ?? []).map((item) => [item.treatment_id, item]));
  const ids = new Set(); const actions = new Set();
  for (const entry of registry.entries ?? []) {
    if (ids.has(entry.treatment_id)) errors.push(`treatment registry ID duplicated:${entry.treatment_id}`); ids.add(entry.treatment_id);
    if (actions.has(entry.facility_action_id)) errors.push(`facility action ID duplicated:${entry.facility_action_id}`); actions.add(entry.facility_action_id);
    if (!STATE_ORDER.includes(entry.current_state)) errors.push(`unrecognized treatment admission state:${entry.treatment_id}`);
    const sourceEntry = source.get(entry.treatment_id);
    if (!sourceEntry) errors.push(`source treatment policy missing:${entry.treatment_id}`);
    else if (sourceEntry.facility_action_id !== entry.facility_action_id) errors.push(`source facility action differs:${entry.treatment_id}`);
    const admitted = entry.current_state === 'SIMULATION_ADMITTED';
    if (Boolean(entry.simulation_admitted) !== admitted) errors.push(`treatment admitted flag differs from state:${entry.treatment_id}`);
    if (Boolean(entry.concrete_treatment_allowed) !== admitted) errors.push(`concrete treatment permission differs from state:${entry.treatment_id}`);
    if (!Array.isArray(entry.missing_requirements) || new Set(entry.missing_requirements).size !== entry.missing_requirements.length) errors.push(`treatment missing-requirements inventory invalid:${entry.treatment_id}`);
    if (admitted) {
      if (entry.missing_requirements.length) errors.push(`admitted treatment retains missing requirements:${entry.treatment_id}`);
      if (entry.governing_rule_status !== 'ADJUDICATED') errors.push(`admitted treatment lacks adjudicated governing rule:${entry.treatment_id}`);
      if (entry.effect_model_status !== 'ADJUDICATED_FOR_SIMULATION') errors.push(`admitted treatment lacks adjudicated simulation effect:${entry.treatment_id}`);
      if (sourceEntry?.concrete_treatment_allowed !== true) errors.push(`source profile does not admit concrete treatment:${entry.treatment_id}`);
    } else {
      if (!entry.missing_requirements.length) errors.push(`blocked treatment has no explicit missing requirement:${entry.treatment_id}`);
      if (entry.effect_model_status !== 'BLOCKED') errors.push(`blocked treatment effect model is not blocked:${entry.treatment_id}`);
      if (sourceEntry?.concrete_treatment_allowed !== false) errors.push(`source profile unexpectedly admits concrete treatment:${entry.treatment_id}`);
    }
  }
  if (source.size !== ids.size || [...source.keys()].some((key) => !ids.has(key))) errors.push('treatment registry and source-profile inventories differ');
  projection = buildProjection(registry, profile);
  const observed = readJson(safePath(root, registry.public_projection_path, 'projection', true));
  if (canonical(observed) !== canonical(projection)) errors.push('treatment admission public projection differs');
  const result = { schema_version: '1.0.0', classification: errors.length ? 'FAIL' : 'PASS', status: errors.length ? 'FAIL' : 'PASS', checker: 'INDEPENDENT_NODE_STDLIB_RECONSTRUCTION_V1', registry_id: registry.registry_id, entry_count: projection.entry_count, simulation_admitted_count: projection.simulation_admitted_count, active_learner_choice_count: projection.active_learner_choice_count, projection_sha256: projection.projection_sha256, errors };
  writeJson(safePath(root, args.jsonOutput, 'json_output'), result); console.log(JSON.stringify(result, null, 2));
} catch (error) { errors.push(error instanceof Error ? error.message : String(error)); console.log(JSON.stringify({ schema_version: '1.0.0', classification: 'FAIL', status: 'FAIL', checker: 'INDEPENDENT_NODE_STDLIB_RECONSTRUCTION_V1', errors }, null, 2)); }
process.exit(errors.length ? 3 : 0);
