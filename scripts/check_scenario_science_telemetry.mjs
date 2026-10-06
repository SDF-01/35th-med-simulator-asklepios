#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync, renameSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const COMPILED = Object.freeze({
  policyId: 'asklepios-scenario-science-policy-v1',
  policyEpoch: 1,
  telemetryProfile: 'HASH_CHAINED_PRIVACY_BOUNDED_SIMULATION_TELEMETRY_V1',
  hashProfile: 'SHA256_PREVIOUS_HASH_PLUS_CANONICAL_EVENT_V1',
  evidenceStates: ['DISCOVERED','IDENTITY_VERIFIED','SPAN_BOUND','APPLICABILITY_REVIEWED','CONTRADICTION_CLEARED','SUPERSESSION_CLEARED','INDEPENDENTLY_ATTESTED','ADMITTED'],
  calibrationStates: ['EXERCISE_ASSUMPTION','DATASET_BOUND','MODEL_FIT','SIMULATION_BASED_CALIBRATION_PASSED','TEMPORAL_HOLDOUT_PASSED','SITE_HOLDOUT_PASSED','UNCERTAINTY_BOUND','DRIFT_RULE_DEFINED','CALIBRATED_FOR_DECLARED_SCOPE'],
  scoringStates: ['SOURCE_CONFORMANCE_ONLY','EVIDENCE_MODEL_DEFINED','PILOT_RELIABILITY_ESTIMATED','HELD_OUT_CALIBRATED','MULTISITE_VALIDATED'],
  requiredFields: ['sequence','event_id','event_kind','logical_time_seconds','actor_role','state_before_sha256','state_after_sha256','calibration_use','scoring_effect','previous_event_sha256','event_sha256'],
  allowedKinds: ['RUN_STARTED','COMMAND_ADMITTED','WORLD_EVENT_FIRED','RESOURCE_STATE_CHANGED','INFORMATION_RELEASED','FACILITATOR_INTERVENTION','RUN_TERMINATED'],
  forbiddenTokens: ['patient_name','full_name','date_of_birth','dob','medical_record_number','mrn','street_address','email_address','phone_number','free_text_patient_identifier'],
});

function fail(message) { throw new Error(message); }
function requireCondition(condition, message) { if (!condition) fail(message); }
function canonical(value, path = '$') {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    requireCondition(Number.isSafeInteger(value), `noninteger number forbidden:${path}`);
    return value;
  }
  if (Array.isArray(value)) return value.map((item, index) => canonical(item, `${path}[${index}]`));
  requireCondition(typeof value === 'object', `unsupported canonical value:${path}`);
  const result = {};
  for (const key of Object.keys(value).sort()) {
    requireCondition(key.length > 0, `empty object key:${path}`);
    result[key] = canonical(value[key], `${path}.${key}`);
  }
  return result;
}
function canonicalJson(value) { return JSON.stringify(canonical(value)); }
function sha256Text(value) { return createHash('sha256').update(value, 'utf8').digest('hex'); }
function sha256Bytes(value) { return createHash('sha256').update(value).digest('hex'); }
function policyHash(policy) { const body = {...policy}; delete body.policy_sha256; return sha256Text(canonicalJson(body)); }
function eventHash(event) { const body = {...event}; delete body.event_sha256; const prefix = body.previous_event_sha256 ?? ''; return sha256Text(`${prefix}\n${canonicalJson(body)}`); }
function chainRoot(events) { return sha256Text(canonicalJson(events.map((event) => event.event_sha256))); }
function isSha(value) { return typeof value === 'string' && /^[0-9a-f]{64}$/.test(value); }
function readJson(path) { const value = JSON.parse(readFileSync(path, 'utf8')); requireCondition(value && typeof value === 'object' && !Array.isArray(value), `JSON object required:${path}`); return value; }
function same(left, right) { return canonicalJson(left) === canonicalJson(right); }
function collectKeys(value, path = '$', out = []) {
  if (Array.isArray(value)) value.forEach((item, index) => collectKeys(item, `${path}[${index}]`, out));
  else if (value && typeof value === 'object') for (const [key, item] of Object.entries(value)) { out.push([key.toLowerCase(), `${path}.${key}`]); collectKeys(item, `${path}.${key}`, out); }
  return out;
}
function writeJsonAtomic(path, value) { mkdirSync(dirname(path), {recursive:true}); const temp = `${path}.tmp`; writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, 'utf8'); renameSync(temp, path); }

const argv = process.argv.slice(2);
let repo = '.'; let report = null;
for (let i = 0; i < argv.length; i += 1) {
  if (argv[i] === '--repo') repo = argv[++i];
  else if (argv[i] === '--report' || argv[i] === '--json-output') report = argv[++i];
  else fail(`unknown option:${argv[i]}`);
}
repo = resolve(repo);
const errors = [];
let observedTelemetryProfile = null;
let observedEventChainRoot = null;
let observedEventCount = 0;
let observedPolicyId = null;
try {
  const policyPath = resolve(repo, 'config/scenario-science/SCENARIO_SCIENCE_POLICY.json');
  const telemetryPath = resolve(repo, 'examples/scenario-science/reference-telemetry.json');
  const genomePath = resolve(repo, 'public/data/scenario_core/verified_scenario_genome.json');
  const policy = readJson(policyPath);
  const telemetry = readJson(telemetryPath);
  observedTelemetryProfile = telemetry.telemetry_profile ?? null;
  observedEventChainRoot = telemetry.event_chain_root_sha256 ?? null;
  observedEventCount = Array.isArray(telemetry.events) ? telemetry.events.length : 0;
  observedPolicyId = telemetry.policy_id ?? null;
  const genome = readJson(genomePath);
  const exact = {
    policy_id: COMPILED.policyId,
    policy_epoch: COMPILED.policyEpoch,
    telemetry_profile: COMPILED.telemetryProfile,
    event_hash_profile: COMPILED.hashProfile,
    evidence_state_order: COMPILED.evidenceStates,
    calibration_state_order: COMPILED.calibrationStates,
    scoring_state_order: COMPILED.scoringStates,
    required_event_fields: COMPILED.requiredFields,
    allowed_event_kinds: COMPILED.allowedKinds,
    forbidden_field_tokens: COMPILED.forbiddenTokens,
  };
  for (const [key, expected] of Object.entries(exact)) if (!same(policy[key], expected)) errors.push(`policy compiled floor differs:${key}`);
  if (policy.policy_sha256 !== policyHash(policy)) errors.push('policy self hash differs');
  const boundaries = policy.telemetry_boundaries ?? {};
  const expectedBoundaries = {
    protected_health_information: 'PROHIBITED', direct_patient_care: 'PROHIBITED', clinical_decision_support: 'PROHIBITED', patient_care_authority: 'NONE',
    wall_clock_in_deterministic_event_hash: false, logical_time_must_be_monotonic: true, sequence_must_be_contiguous: true, event_hash_chain_required: true,
  };
  for (const [key, expected] of Object.entries(expectedBoundaries)) if (!same(boundaries[key], expected)) errors.push(`policy authority or telemetry boundary differs:${key}`);
  if (policy.timing_scoring_boundary?.uncalibrated_timing_may_change_learner_score !== false) errors.push('uncalibrated timing may change learner score');
  if (policy.timing_scoring_boundary?.minimum_state_for_timing_score_effect !== 'CALIBRATED_FOR_DECLARED_SCOPE') errors.push('timing scoring promotion floor differs');
  if (policy.scoring_boundary?.critical_safety_failure_overridable_by_statistical_score !== false) errors.push('statistical score may override critical safety failure');
  if (policy.scoring_boundary?.insufficient_evidence_output !== 'INSUFFICIENT_EVIDENCE') errors.push('insufficient evidence output differs');
  for (const key of ['narrative_only_variant_creates_new_behavior','provenance_only_variant_creates_new_behavior','seed_only_variant_creates_new_behavior']) if (policy.behavioral_novelty_boundary?.[key] !== false) errors.push(`cosmetic variant may create new behavior:${key}`);
  if (policy.automatic_clinical_authority_promotion_permitted !== false) errors.push('automatic clinical authority promotion enabled');

  if (telemetry.telemetry_profile !== COMPILED.telemetryProfile) errors.push('telemetry profile differs');
  if (telemetry.event_hash_profile !== COMPILED.hashProfile) errors.push('event hash profile differs');
  if (telemetry.policy_id !== policy.policy_id || telemetry.policy_sha256 !== policy.policy_sha256) errors.push('telemetry policy binding differs');
  if (telemetry.scenario_genome_id !== genome.genome_id) errors.push('telemetry Scenario Genome ID differs');
  if (telemetry.scenario_genome_sha256 !== genome.genome_sha256) errors.push('telemetry Scenario Genome hash differs');
  if (telemetry.scenario_genome_file_sha256 !== sha256Bytes(readFileSync(genomePath))) errors.push('telemetry Scenario Genome file hash differs');

  const forbidden = new Set(COMPILED.forbiddenTokens);
  for (const [key, path] of collectKeys(telemetry)) {
    if (forbidden.has(key)) errors.push(`forbidden privacy field:${path}`);
    if (['wall_clock','wall_clock_ms','timestamp','patient_free_text'].includes(key)) errors.push(`forbidden deterministic telemetry field:${path}`);
  }
  const events = telemetry.events;
  if (!Array.isArray(events) || events.length === 0) errors.push('telemetry events missing');
  else {
    if (events.at(-1)?.event_kind !== 'RUN_TERMINATED') errors.push('terminal telemetry event missing');
    let previousHash = null; let previousTime = -1; const ids = new Set();
    events.forEach((event, index) => {
      const missing = COMPILED.requiredFields.filter((field) => !(field in event));
      if (missing.length) errors.push(`event required fields missing:${index}:${missing.join(',')}`);
      if (event.sequence !== index) errors.push(`event sequence is not contiguous:${index}`);
      if (!Number.isSafeInteger(event.logical_time_seconds) || event.logical_time_seconds < 0) errors.push(`event logical time invalid:${index}`);
      else if (event.logical_time_seconds < previousTime) errors.push(`event logical time regressed:${index}`);
      else previousTime = event.logical_time_seconds;
      if (typeof event.event_id !== 'string' || !event.event_id) errors.push(`event ID invalid:${index}`);
      else if (ids.has(event.event_id)) errors.push(`event ID duplicated:${event.event_id}`);
      else ids.add(event.event_id);
      if (!COMPILED.allowedKinds.includes(event.event_kind)) errors.push(`event kind is not allowed:${index}`);
      if (event.previous_event_sha256 !== previousHash) errors.push(`event previous hash differs:${index}`);
      const expected = eventHash(event); if (event.event_sha256 !== expected) errors.push(`event hash differs:${index}`);
      previousHash = isSha(event.event_sha256) ? event.event_sha256 : null;
      if (String(event.calibration_use ?? '').includes('NOT_CLINICAL_CALIBRATION') && event.scoring_effect !== 'NONE') errors.push(`uncalibrated timing changed score:${index}`);
    });
    if (telemetry.event_chain_root_sha256 !== chainRoot(events)) errors.push('event-chain root differs');
  }
  const truth = telemetry.truth_boundaries ?? {};
  const expectedTruth = {protected_health_information:'PROHIBITED',direct_patient_care:'PROHIBITED',clinical_decision_support:'PROHIBITED',patient_care_authority:'NONE',operational_timing:'NOT_CALIBRATED',human_team_behavior:'STRUCTURAL_ONLY_NOT_CALIBRATED',patient_dynamics:'SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY'};
  for (const [key, expected] of Object.entries(expectedTruth)) if (truth[key] !== expected) errors.push(`telemetry truth boundary differs:${key}`);
} catch (error) { errors.push(`checker exception:${error?.message ?? String(error)}`); }

const result = {schema_version:'1.0.0',classification:errors.length ? 'FAIL':'PASS',status:errors.length ? 'FAIL':'PASS',checker:'INDEPENDENT_NODE_STDLIB_RECONSTRUCTION_V1',telemetry_profile:observedTelemetryProfile,event_chain_root_sha256:observedEventChainRoot,events:observedEventCount,policy_id:observedPolicyId,errors:[...new Set(errors)].sort()};
if (report) writeJsonAtomic(resolve(repo, report), result);
console.log(JSON.stringify(result, null, 2));
process.exit(errors.length ? 3 : 0);
