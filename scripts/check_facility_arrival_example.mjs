#!/usr/bin/env node
/** Independent Node verifier. It does not import the TypeScript runtime. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import process from 'node:process';

const ACTORS = ['receiving_provider', 'clinic_nurse', 'diagnostics_tech', 'wit_observer'];
const DEMONSTRATED = new Set([
  'source_scenario_block_binding',
  'source_action_only_clinical_scoring',
  'deterministic_event_sourced_replay',
  'per_transition_state_binding',
  'explicit_actor_knowledge_updates',
  'hidden_findings_withheld_until_diagnostics',
  'timeout_as_authenticated_system_event',
  'duplicate_action_and_command_rejection',
  'score_clamped_to_closed_basis_point_range',
  'wit_process_observation_separated_from_clinical_scoring',
  'exercise_assumptions_disclosed_as_uncalibrated',
]);
const FACILITY_SOURCE_PROJECTION_SHA256 = 'b5562e64b4847d7bc47afc9fcc1e917aeee3268dddee3134bd2c3129266d5636';
const FACILITY_SOURCE_HASH_MODE = 'canonical_utf8_lf_v1';

const OPEN = new Set([
  'claim_level_clinical_entailment',
  'real_world_frequency_calibration',
  'human_team_policy_calibration',
  'facility_specific_workflow_calibration',
  'continuous_physiology_model',
  'concurrent_multi_casualty_resource_contention',
  'causal_identification_for_counterfactual_aar',
  'executable_to_lean_refinement',
  'independent_proof_kernel_acceptance',
  'formal_vva_for_specific_wing_intended_use',
]);

const FORBIDDEN_PUBLIC_KEYS = new Set([
  'licensed_text', 'full_text', 'article_text', 'raw_xml', 'api_key',
  'institutional_token', 'credential', 'secret',
]);
function scanForbidden(value, at = '$') {
  const findings = [];
  if (Array.isArray(value)) {
    value.forEach((child, index) => findings.push(...scanForbidden(child, `${at}[${index}]`)));
  } else if (value && typeof value === 'object') {
    for (const [key, child] of Object.entries(value)) {
      const normalized = key.toLowerCase().replaceAll('-', '_');
      if (FORBIDDEN_PUBLIC_KEYS.has(normalized)) findings.push(`forbidden public field:${at}.${key}`);
      findings.push(...scanForbidden(child, `${at}.${key}`));
    }
  }
  return findings;
}

function canonical(value) {
  if (value === null) return 'null';
  if (typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('non-finite number');
    if (Object.is(value, -0)) return '0';
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (typeof value !== 'object') throw new Error(`unsupported value:${typeof value}`);
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
}
function shaText(value) { return crypto.createHash('sha256').update(value, 'utf8').digest('hex'); }
function sha(value) { return shaText(canonical(value)); }
function fileSha(file) { return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'); }
function canonicalTextFileSha(file) {
  const raw = fs.readFileSync(file);
  if (raw.length >= 3 && raw[0] === 0xef && raw[1] === 0xbb && raw[2] === 0xbf) throw new Error(`UTF-8 BOM forbidden:${file}`);
  const text = raw.toString('utf8').replaceAll('\r\n', '\n').replaceAll('\r', '\n');
  return shaText(text);
}
function merkle(hashes) {
  let level = [...hashes].sort();
  if (level.length === 0) return shaText('');
  while (level.length > 1) {
    const next = [];
    for (let index = 0; index < level.length; index += 2) {
      const left = level[index]; const right = level[index + 1] ?? left;
      next.push(shaText(`${left}:${right}`));
    }
    level = next;
  }
  return level[0];
}
function unique(values) { return [...new Set(values)].sort(); }
function normalize(state) {
  const copy = structuredClone(state);
  for (const key of ['completed_action_ids','completed_source_action_ids','unsafe_source_action_ids','fired_system_events','revealed_hidden_findings','alerts']) {
    copy[key] = unique(copy[key] ?? []);
  }
  copy.actor_knowledge = Object.fromEntries(ACTORS.map((actor) => [actor, unique(copy.actor_knowledge?.[actor] ?? [])]));
  copy.source_action_completed_at = Object.fromEntries(Object.entries(copy.source_action_completed_at ?? {}).sort(([a],[b]) => a.localeCompare(b)));
  copy.action_completed_at = Object.fromEntries(Object.entries(copy.action_completed_at ?? {}).sort(([a],[b]) => a.localeCompare(b)));
  return copy;
}
function stateSha(state) { return sha(normalize(state)); }
function json(file) { return JSON.parse(fs.readFileSync(file, 'utf8')); }
function balanced(text, start, opening = '{', closing = '}') {
  let depth = 0; let quote = null; let escaped = false;
  if (text[start] !== opening) throw new Error('invalid balanced start');
  for (let index = start; index < text.length; index += 1) {
    const char = text[index];
    if (quote !== null) {
      if (escaped) escaped = false;
      else if (char === '\\') escaped = true;
      else if (char === quote) quote = null;
      continue;
    }
    if (["'", '"', '`'].includes(char)) { quote = char; continue; }
    if (char === opening) depth += 1;
    else if (char === closing && --depth === 0) return text.slice(start, index + 1);
  }
  throw new Error('unterminated source block');
}
function propString(text, name) {
  const match = text.match(new RegExp(`\\b${name}\\s*:\\s*'([^']*)'`, 's'));
  if (!match) throw new Error(`missing source property:${name}`); return match[1];
}
function propNumber(text, name) {
  const match = text.match(new RegExp(`\\b${name}\\s*:\\s*(-?\\d+(?:\\.\\d+)?)`));
  if (!match) throw new Error(`missing source number:${name}`); return Number(match[1]);
}
function propArrayStrings(text, name) {
  const match = new RegExp(`\\b${name}\\s*:\\s*\\[`).exec(text);
  if (!match) throw new Error(`missing source array:${name}`);
  const start = text.indexOf('[', match.index); return [...balanced(text, start, '[', ']').matchAll(/'([^']*)'/g)].map((item) => item[1]);
}
function propObject(text, name) {
  const match = new RegExp(`\\b${name}\\s*:\\s*\\{`).exec(text);
  if (!match) throw new Error(`missing source object:${name}`); return balanced(text, text.indexOf('{', match.index));
}
function objectEntries(arrayBlock) {
  const values = []; let index = 0;
  while (true) { const start = arrayBlock.indexOf('{', index); if (start < 0) return values; const block = balanced(arrayBlock, start); values.push(block); index = start + block.length; }
}
function reconstructSource(root) {
  const sourcePath = path.join(root, 'src/content/scenarios.ts'); const text = fs.readFileSync(sourcePath, 'utf8');
  const marker = text.indexOf('const askD001: Scenario ='); if (marker < 0) throw new Error('ASK-D-001 declaration missing');
  const block = balanced(text, text.indexOf('{', marker));
  const patientsMatch = /\bpatients\s*:\s*\[/.exec(block); if (!patientsMatch) throw new Error('patient array missing');
  const patients = objectEntries(balanced(block, block.indexOf('[', patientsMatch.index), '[', ']')); if (patients.length !== 1) throw new Error('patient count mismatch');
  const patient = patients[0]; const vitals = propObject(patient, 'initial_vitals'); const expected = propObject(block, 'expected_actions');
  const actions = [];
  for (const priority of ['critical','important','optional','unsafe']) {
    const match = new RegExp(`\\b${priority}\\s*:\\s*\\[`).exec(expected); if (!match) throw new Error(`action group missing:${priority}`);
    for (const action of objectEntries(balanced(expected, expected.indexOf('[', match.index), '[', ']'))) actions.push({id:propString(action,'id'),label:propString(action,'label'),priority,points:propNumber(action,'points')});
  }
  const end = propObject(block, 'end_conditions');
  return {
    scenario_id: propString(block,'scenario_id'),
    patient: {initial_presentation:propString(patient,'initial_presentation'),initial_vitals:{hr:propNumber(vitals,'hr'),bp_systolic:propNumber(vitals,'bp_systolic'),bp_diastolic:propNumber(vitals,'bp_diastolic'),rr:propNumber(vitals,'rr'),spo2:propNumber(vitals,'spo2'),temp_c:propNumber(vitals,'temp_c'),gcs:propNumber(vitals,'gcs')},hidden_findings:propArrayStrings(patient,'hidden_findings')},
    source_actions: actions.sort((a,b)=>a.id.localeCompare(b.id)),
    end_conditions: {success:propArrayStrings(end,'success'),failure:propArrayStrings(end,'failure'),timeout_minutes:propNumber(end,'timeout_minutes')},
    source_file_sha256: canonicalTextFileSha(sourcePath),
  };
}
function setEq(a, b) { return a.size === b.size && [...a].every((value) => b.has(value)); }

function initialState(spec, source) {
  const actors = new Map(spec.actors.map((actor) => [actor.actor_id, actor]));
  const maxPoints = source.source_actions.reduce((sum, record) => sum + Math.max(0, record.points), 0);
  return normalize({
    revision: 0, elapsed_seconds: 0, phase: 'pre_arrival', terminal_status: 'active', outcome: null,
    completed_action_ids: [], completed_source_action_ids: [], unsafe_source_action_ids: [], fired_system_events: [],
    source_action_completed_at: {}, action_completed_at: {}, revealed_hidden_findings: [],
    actor_knowledge: Object.fromEntries(ACTORS.map((id) => [id, [...(actors.get(id)?.initial_knowledge ?? [])]])),
    alerts: [], score_points: 0, max_positive_points: maxPoints,
  });
}
function grant(state, grants) { for (const actor of ACTORS) state.actor_knowledge[actor].push(...(grants?.[actor] ?? [])); }
function diagnosticsDue(state, spec) {
  const imaging = state.action_completed_at.order_imaging; const labs = state.action_completed_at.order_labs;
  return imaging === undefined || labs === undefined ? null : Math.max(imaging, labs) + spec.parameters.diagnostic_delay_seconds.value;
}
function duration(state, action, spec) {
  if (action.duration_mode === 'fixed') return action.duration_seconds;
  const due = diagnosticsDue(state, spec); if (due === null) throw new Error('diagnostic wait before orders');
  return Math.max(0, due - state.elapsed_seconds);
}
function requiredSource(spec, source) {
  const priorities = new Set(spec.completion.required_source_action_priorities);
  return source.source_actions.filter((a) => priorities.has(a.priority)).map((a) => a.id).sort();
}
function completionReady(state, spec, source) {
  return requiredSource(spec, source).every((id) => state.completed_source_action_ids.includes(id))
    && spec.completion.required_operational_actions.filter((id) => id !== 'complete_handoff').every((id) => state.completed_action_ids.includes(id))
    && spec.completion.required_event_ids.every((id) => state.fired_system_events.includes(id))
    && state.unsafe_source_action_ids.length === 0;
}
function transitionId(transition) {
  const core = Object.fromEntries(Object.entries(transition).filter(([key]) => key !== 'transition_id'));
  return `FAT-${String(transition.sequence).padStart(3,'0')}-${sha(core).slice(0,12)}`;
}
function scoreBps(state) {
  if (state.max_positive_points <= 0) return 0;
  return Math.min(10000, Math.max(0, Math.round(state.score_points * 10000 / state.max_positive_points)));
}

function applyAction(state, transition, action, spec, source, errors, pass) {
  const before = normalize(state); const id = action.action_id;
  pass(before.terminal_status === 'active', `action after terminal:${transition.sequence}`);
  pass(action.repeatable || !before.completed_action_ids.includes(id), `duplicate nonrepeatable action:${id}`);
  for (const prerequisite of action.prerequisites) pass(before.completed_action_ids.includes(prerequisite), `missing prerequisite:${id}:${prerequisite}`);
  for (const eventId of action.required_event_ids ?? []) pass(before.fired_system_events.includes(eventId), `missing event:${id}:${eventId}`);
  if (id === 'complete_handoff') pass(completionReady(before, spec, source), 'completion before requirements');
  const expectedDuration = duration(before, action, spec);
  pass(transition.started_at_seconds === before.elapsed_seconds, `action start mismatch:${id}`);
  pass(transition.completed_at_seconds === before.elapsed_seconds + expectedDuration, `action duration mismatch:${id}`);
  pass(transition.completed_at_seconds <= spec.parameters.timeout_seconds.value, `action exceeds timeout:${id}`);
  const after = structuredClone(before); after.revision += 1; after.elapsed_seconds += expectedDuration;
  after.completed_action_ids.push(id); after.action_completed_at[id] = after.elapsed_seconds;
  if (action.phase_after !== null) after.phase = action.phase_after; grant(after, action.knowledge_grants);
  let delta = 0;
  const sourceMap = new Map(source.source_actions.map((record) => [record.id, record]));
  if (action.origin === 'operational_workflow') pass(action.source_action_id === null, `operational source binding:${id}`);
  else {
    const record = sourceMap.get(action.source_action_id); pass(Boolean(record), `unknown source action:${id}`);
    if (record) {
      delta = record.points; after.score_points += delta; after.completed_source_action_ids.push(record.id);
      after.source_action_completed_at[record.id] = after.elapsed_seconds;
      if (record.priority === 'unsafe') after.unsafe_source_action_ids.push(record.id);
    }
  }
  pass(transition.score_delta === delta, `score delta mismatch:${id}`);
  if (id === 'review_diagnostics') after.alerts.push('Diagnostic results reviewed and casualty reassessed.');
  if (id === 'pain_management') {
    after.alerts.push('Source-defined pain-management objective addressed without generating a drug, dose, or route.');
    pass(action.clinical_detail_policy === 'NO_GENERATED_DRUG_DOSE_OR_ROUTE', 'pain detail policy missing');
  }
  if (action.terminal_effect) {
    after.terminal_status = action.terminal_effect; after.phase = 'complete';
    after.outcome = action.terminal_effect === 'completed' ? 'Closed-loop receiving handoff completed.' : `Unsafe source action selected: ${action.label}`;
  }
  return normalize(after);
}
function eventValid(state, transition, event, previous, spec) {
  const trigger = event.trigger;
  if (trigger.kind === 'initial') return transition.sequence === 1 && state.revision === 0;
  if (trigger.kind === 'after_action') return previous?.action_id === trigger.action_id;
  if (trigger.kind === 'elapsed_time_due') return state.elapsed_seconds >= trigger.at_elapsed_seconds && transition.completed_at_seconds >= trigger.at_elapsed_seconds;
  if (trigger.kind === 'diagnostics_due') { const due = diagnosticsDue(state, spec); return due !== null && transition.completed_at_seconds >= due; }
  if (trigger.kind === 'timeout_due') return transition.completed_at_seconds === spec.parameters.timeout_seconds.value;
  return false;
}
function applyEvent(state, transition, event, previous, spec, source, errors, pass) {
  const before = normalize(state); const id = event.event_id;
  pass(!before.fired_system_events.includes(id), `duplicate event:${id}`);
  pass(eventValid(before, transition, event, previous, spec), `event trigger mismatch:${id}`);
  pass(transition.started_at_seconds === before.elapsed_seconds, `event start mismatch:${id}`);
  pass(transition.completed_at_seconds >= before.elapsed_seconds, `event time regression:${id}`);
  const after = structuredClone(before); after.elapsed_seconds = transition.completed_at_seconds; after.revision += 1;
  after.fired_system_events.push(id); grant(after, event.knowledge_grants);
  if (event.reveal_source_hidden_findings) after.revealed_hidden_findings.push(...source.patient.hidden_findings);
  const alerts = {
    prearrival_notice: 'Pre-arrival notification received. Prepare for post-field-care reception.',
    second_casualty_inbound: 'Second casualty inbound. Preserve continuity while resources remain constrained.',
    diagnostics_ready: 'Ordered imaging and laboratory results are available for review.',
  };
  if (alerts[id]) after.alerts.push(alerts[id]);
  if (event.terminal_effect) {
    after.terminal_status = event.terminal_effect; after.phase = 'complete';
    after.outcome = event.terminal_effect === 'timeout' ? 'Exercise ended at the source-bound timeout before closed-loop receiving handoff.' : `Exercise ended: ${event.terminal_effect}`;
  }
  return normalize(after);
}


function sortDeep(value) {
  if (Array.isArray(value)) return value.map(sortDeep);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sortDeep(value[key])]));
  }
  return value;
}

function expectedGeneratedSpecText(spec) {
  const pretty = JSON.stringify(sortDeep(spec), null, 2);
  const text = `/* AUTO-GENERATED by scripts/compile_facility_arrival_spec.py. DO NOT EDIT. */\nimport type { FacilityArrivalSpec } from './types';\n\nexport const FACILITY_ARRIVAL_SPEC_SHA256 = '${sha(spec)}' as const;\nexport const FACILITY_ARRIVAL_SPEC = ${pretty} as FacilityArrivalSpec;\n`;
  return `${text.split('\n').map((line) => line.replace(/[ \t]+$/u, '')).join('\n').replace(/\n*$/u, '')}\n`;
}

function verifySpecContract(root, spec, pass) {
  const authority = {
    deployment_scope: 'production_training_reference',
    patient_care_use: 'PROHIBITED',
    clinical_content_mode: 'INHERITED_REPOSITORY_TEMPLATE',
    operational_content_mode: 'DETERMINISTIC_EXERCISE_ORCHESTRATION',
    evidence_mode: 'IDENTITY_AND_SCOPE_ONLY',
    automatic_clinical_rule_generation: false,
  };
  pass(canonical(spec.authority) === canonical(authority), 'spec authority boundary mismatch');
  pass(spec.parameters?.diagnostic_delay_seconds?.calibration_status === 'NOT_CALIBRATED', 'diagnostic delay calibration promoted');
  pass(spec.parameters?.pass_threshold_bps?.calibration_status === 'NOT_CALIBRATED', 'pass threshold calibration promoted');
  pass(spec.parameters?.timeout_seconds?.calibration_status === 'SOURCE_BOUND', 'timeout source binding weakened');
  pass(spec.parameters?.pass_threshold_bps?.value >= 0 && spec.parameters?.pass_threshold_bps?.value <= 10000, 'pass threshold outside range');
  const actionIds = new Set();
  for (const action of spec.actions ?? []) {
    pass(typeof action.action_id === 'string' && !actionIds.has(action.action_id), `duplicate or invalid action:${action.action_id}`);
    actionIds.add(action.action_id);
    pass(action.origin !== 'operational_workflow' || action.source_action_id === null, `operational action source binding:${action.action_id}`);
    pass(action.origin !== 'source_template' || typeof action.source_action_id === 'string', `source action missing binding:${action.action_id}`);
    if (action.action_id === 'pain_management') pass(action.clinical_detail_policy === 'NO_GENERATED_DRUG_DOSE_OR_ROUTE', 'pain-management detail policy weakened');
  }
  const eventIds = new Set((spec.events ?? []).map((item) => item.event_id));
  pass(setEq(eventIds, new Set(['prearrival_notice','second_casualty_inbound','diagnostics_ready','timeout_reached'])), 'event inventory mismatch');
  const timeout = (spec.events ?? []).find((item) => item.event_id === 'timeout_reached');
  pass(Boolean(timeout), 'timeout event missing');
  if (timeout) {
    pass(canonical(timeout.trigger) === canonical({kind:'timeout_due'}) && timeout.terminal_effect === 'timeout', 'timeout event contract mismatch');
  }
  pass(canonical((spec.events ?? []).filter((item) => item.reveal_source_hidden_findings).map((item) => item.event_id)) === canonical(['diagnostics_ready']), 'hidden-finding release event mismatch');
  const generatedPath = path.join(root, 'src/facility-arrival/specification.generated.ts');
  pass(fs.existsSync(generatedPath) && fs.readFileSync(generatedPath, 'utf8') === expectedGeneratedSpecText(spec), 'generated TypeScript specification diverges');
}


function verifyGeneratedBindings(root, pass) {
  const registryPath = path.join(root, 'public/data/content_registry/content_registry.json');
  const scenarioPath = path.join(root, 'src/content/scenarios.ts');
  const bindingTsPath = path.join(root, 'src/facility-arrival/bindings.generated.ts');
  const bindingJsonPath = path.join(root, 'config/facility-arrival/source-binding.generated.json');
  const registry = json(registryPath);
  const matches = (registry.assets ?? []).filter((asset) => asset?.asset_id === 'template:ASK-D-001');
  pass(matches.length === 1, 'binding template asset count mismatch');
  if (matches.length !== 1) return;
  const asset = matches[0];
  const sourceDigest = canonicalTextFileSha(scenarioPath);
  pass(asset.kind === 'protected_template', 'binding template asset kind differs');
  pass(asset.source?.path === 'src/content/scenarios.ts', 'binding scenario source path differs');
  pass(asset.source?.file_sha256 === sourceDigest, 'binding scenario source hash differs');
  pass(typeof registry.roots?.registry_merkle_root === 'string', 'binding registry root missing');
  pass(typeof asset.record_sha256 === 'string' && /^[0-9a-f]{64}$/u.test(asset.record_sha256), 'binding template record hash missing');
  if (typeof registry.roots?.registry_merkle_root !== 'string' || typeof asset.record_sha256 !== 'string') return;

  const expectedTs =
    '/* AUTO-GENERATED by scripts/build_facility_arrival_bindings.py. DO NOT EDIT. */\n' +
    `export const FACILITY_CONTENT_REGISTRY_ROOT = '${registry.roots.registry_merkle_root}' as const;\n` +
    `export const FACILITY_TEMPLATE_RECORD_SHA256 = '${asset.record_sha256}' as const;\n` +
    `export const FACILITY_SCENARIO_SOURCE_SHA256 = '${sourceDigest}' as const;\n` +
    `export const FACILITY_SCENARIO_SOURCE_HASH_MODE = '${FACILITY_SOURCE_HASH_MODE}' as const;\n` +
    `export const FACILITY_SOURCE_SCENARIO_PROJECTION_SHA256 = '${FACILITY_SOURCE_PROJECTION_SHA256}' as const;\n`;
  const expectedJson = `${JSON.stringify({
    content_registry_merkle_root: registry.roots.registry_merkle_root,
    scenario_source_hash_mode: FACILITY_SOURCE_HASH_MODE,
    scenario_source_path: 'src/content/scenarios.ts',
    scenario_source_sha256: sourceDigest,
    schema_version: '1.0.0',
    source_scenario_id: 'ASK-D-001',
    source_scenario_projection_sha256: FACILITY_SOURCE_PROJECTION_SHA256,
    template_asset_id: 'template:ASK-D-001',
    template_record_sha256: asset.record_sha256,
  }, null, 2)}\n`;
  pass(fs.existsSync(bindingTsPath) && fs.readFileSync(bindingTsPath, 'utf8') === expectedTs, 'generated TypeScript bindings diverge');
  pass(fs.existsSync(bindingJsonPath) && fs.readFileSync(bindingJsonPath, 'utf8') === expectedJson, 'generated JSON source binding diverges');
}

function verify(root) {
  const base = path.join(root, 'examples/facility-arrival');
  const spec = json(path.join(root, 'config/facility-arrival/ASK-D-001.json'));
  const session = json(path.join(base, 'interaction.json'));
  const aar = json(path.join(base, 'aar.json'));
  const ledger = json(path.join(base, 'claim-ledger.json'));
  const source = json(path.join(base, 'source-snapshot.json'));
  const sourceTruth = json(path.join(base, 'source-truth.json'));
  const manifest = json(path.join(base, 'manifest.json'));
  const errors = []; let checks = 0;
  const pass = (condition, message) => { checks += 1; if (!condition) errors.push(message); };

  for (const [name, payload] of Object.entries({spec, session, aar, ledger, source, sourceTruth, manifest})) {
    for (const finding of scanForbidden(payload)) errors.push(`${name}:${finding}`);
    checks += 1;
  }

  verifySpecContract(root, spec, pass);
  verifyGeneratedBindings(root, pass);

  const sourceNoHash = Object.fromEntries(Object.entries(source).filter(([key]) => key !== 'snapshot_sha256'));
  pass(source.snapshot_sha256 === sha(sourceNoHash), 'source snapshot hash mismatch');
  const reconstructed = reconstructSource(root);
  pass(reconstructed.scenario_id === source.source_scenario_id, 'source-code scenario ID mismatch');
  pass(canonical(reconstructed.patient) === canonical(source.patient), 'source-code patient mismatch');
  pass(canonical(reconstructed.source_actions) === canonical(source.source_actions), 'source-code action mismatch');
  pass(canonical(reconstructed.end_conditions) === canonical(source.end_conditions), 'source-code end-condition mismatch');
  const registry = json(path.join(root, 'public/data/content_registry/content_registry.json'));
  const templates = registry.assets.filter((asset) => asset.asset_id === 'template:ASK-D-001');
  pass(templates.length === 1, 'registry template count mismatch');
  if (templates.length === 1) {
    const asset = templates[0]; const noHash = Object.fromEntries(Object.entries(asset).filter(([key]) => key !== 'record_sha256'));
    pass(asset.record_sha256 === sha(noHash), 'registry template hash mismatch');
    pass(asset.record_sha256 === source.template_record_sha256, 'registry/source template mismatch');
    pass(asset.source.file_sha256 === reconstructed.source_file_sha256, 'registry source-file hash mismatch');
    pass(registry.roots.registry_merkle_root === source.content_registry_merkle_root, 'registry root mismatch');
  }
  pass(session.spec_sha256 === sha(spec), 'session spec hash mismatch');
  pass(session.source_binding.source_scenario_id === source.source_scenario_id, 'source ID mismatch');
  pass(session.source_binding.source_scenario_sha256 === source.source_scenario_sha256, 'source hash mismatch');
  pass(canonical(session.source_binding.source_action_ids) === canonical(source.source_actions.map((a) => a.id).sort()), 'source action inventory mismatch');
  for (const key of ['source_file_path','template_asset_id','template_record_sha256','content_registry_merkle_root']) pass(session.source_binding[key] === source[key], `source binding:${key}`);
  pass(session.authority.patient_care_use === 'PROHIBITED', 'patient-care boundary escalated');
  pass(session.authority.automatic_clinical_rule_generation === false, 'automatic clinical generation enabled');

  let state = initialState(spec, source); pass(canonical(state) === canonical(session.initial_state), 'initial state mismatch');
  const actions = new Map(spec.actions.map((record) => [record.action_id, record]));
  const events = new Map(spec.events.map((record) => [record.event_id, record]));
  let previous;
  for (let index = 0; index < session.transitions.length; index += 1) {
    const transition = session.transitions[index];
    pass(transition.sequence === index + 1, `sequence mismatch:${index + 1}`);
    pass(transition.before_state_sha256 === stateSha(state), `before hash mismatch:${index + 1}`);
    pass(transition.transition_id === transitionId(transition), `transition ID mismatch:${index + 1}`);
    let expected;
    if (transition.kind === 'learner_action') {
      const action = actions.get(transition.action_id); pass(Boolean(action), `unknown action:${transition.action_id}`);
      expected = action ? applyAction(state, transition, action, spec, source, errors, pass) : state;
      pass(transition.actor_id === 'receiving_provider', `learner actor mismatch:${index + 1}`);
      pass(transition.event_id === null, `learner event field mismatch:${index + 1}`);
    } else if (transition.kind === 'system_event') {
      const event = events.get(transition.event_id); pass(Boolean(event), `unknown event:${transition.event_id}`);
      expected = event ? applyEvent(state, transition, event, previous, spec, source, errors, pass) : state;
      pass(transition.actor_id === 'system', `system actor mismatch:${index + 1}`);
      pass(transition.score_delta === 0, `system event score mismatch:${index + 1}`);
    } else { errors.push(`unknown transition kind:${index + 1}`); expected = state; }
    pass(transition.wit_observation.process_only === true, `WIT process flag:${index + 1}`);
    pass(transition.wit_observation.clinical_directive === null, `WIT directive present:${index + 1}`);
    pass(transition.after_state_sha256 === stateSha(expected), `after hash mismatch:${index + 1}`);
    pass(canonical(normalize(transition.state_after)) === canonical(expected), `state snapshot mismatch:${index + 1}`);
    state = expected; previous = transition;
  }
  pass(canonical(normalize(session.final_state)) === canonical(state), 'final state mismatch');
  pass(session.normalized_score_bps === scoreBps(state), 'score normalization mismatch');
  pass(session.normalized_score_bps >= 0 && session.normalized_score_bps <= 10000, 'score outside range');
  pass(!state.revealed_hidden_findings.length || state.fired_system_events.includes('diagnostics_ready'), 'early hidden findings');
  pass(state.terminal_status !== 'completed' || session.transitions.at(-1)?.action_id === 'complete_handoff', 'completion without handoff');
  pass(state.terminal_status !== 'timeout' || session.transitions.at(-1)?.event_id === 'timeout_reached', 'timeout not event-sourced');

  const cert = session.certificate;
  pass(cert.source_binding_sha256 === sha(session.source_binding), 'certificate source binding');
  pass(cert.spec_sha256 === sha(spec), 'certificate spec');
  pass(cert.initial_state_sha256 === stateSha(session.initial_state), 'certificate initial state');
  pass(cert.final_state_sha256 === stateSha(session.final_state), 'certificate final state');
  pass(cert.transition_root_sha256 === merkle(session.transitions.map((t) => t.after_state_sha256)), 'certificate transition root');
  const replay = { initial_state: session.initial_state, transitions: session.transitions.map((t) => ({transition_id:t.transition_id,before_state_sha256:t.before_state_sha256,after_state_sha256:t.after_state_sha256})), final_state: session.final_state };
  pass(cert.replay_root_sha256 === sha(replay), 'certificate replay root');
  pass(cert.claim_ledger_sha256 === ledger.ledger_sha256, 'certificate ledger');
  const withoutCert = Object.fromEntries(Object.entries(session).filter(([key]) => key !== 'certificate'));
  pass(cert.session_sha256 === sha(withoutCert), 'certificate session hash');
  pass(Object.values(cert.checks).every((value) => value === true), 'certificate reports failed check');

  const allowed = Object.fromEntries(spec.actors.map((a) => [a.actor_id, new Set(a.initial_knowledge)]));
  for (const record of [...spec.actions, ...spec.events]) for (const [actor,tokens] of Object.entries(record.knowledge_grants ?? {})) for (const token of tokens) allowed[actor].add(token);
  for (const actor of ACTORS) pass(state.actor_knowledge[actor].every((token) => allowed[actor].has(token)), `unauthorized knowledge:${actor}`);

  const recordIds = new Set();
  for (const record of ledger.records) {
    pass(!recordIds.has(record.claim_id), `duplicate claim:${record.claim_id}`); recordIds.add(record.claim_id);
    const noHash = Object.fromEntries(Object.entries(record).filter(([key]) => key !== 'record_sha256'));
    pass(record.record_sha256 === sha(noHash), `claim hash:${record.claim_id}`);
    if (record.origin_class === 'exercise_assumption') {
      pass(record.relation === 'ASSUMPTION' && record.evidence_entailment === 'NOT_ADJUDICATED' && record.clinical_authority === 'NOT_GRANTED', `assumption promoted:${record.claim_id}`);
    }
    if (record.origin_class === 'scope_reference') pass(record.clinical_authority === 'NOT_GRANTED', `scope authority:${record.claim_id}`);
  }
  pass(ledger.ledger_sha256 === sha({schema_version:ledger.schema_version,example_id:ledger.example_id,records:ledger.records}), 'ledger root');
  const truthNoRoot = Object.fromEntries(Object.entries(sourceTruth).filter(([key]) => key !== 'source_truth_root_sha256'));
  pass(sourceTruth.source_truth_root_sha256 === sha(truthNoRoot), 'source truth root');
  for (const record of sourceTruth.records) {
    const noHash = Object.fromEntries(Object.entries(record).filter(([key]) => key !== 'source_record_sha256'));
    pass(record.source_record_sha256 === sha(noHash), `source truth record:${record.source_id}`);
    pass(record.relation === 'SCOPE_AND_PROCESS_REFERENCE' && record.clinical_rule_entailment === 'NOT_USED', `source truth escalation:${record.source_id}`);
  }
  const aarNoHash = Object.fromEntries(Object.entries(aar).filter(([key]) => key !== 'aar_sha256'));
  pass(aar.aar_sha256 === sha(aarNoHash), 'AAR hash');
  pass(aar.session_sha256 === cert.session_sha256, 'AAR session binding');
  pass(aar.counterfactual_boundaries.causal_claims_allowed === false, 'AAR causal escalation');
  pass(setEq(new Set(aar.validity_ledger.demonstrated), DEMONSTRATED), 'demonstrated ledger mismatch');
  pass(setEq(new Set(aar.validity_ledger.open), OPEN), 'open ledger mismatch');

  const expectedFileMap = {interaction:'interaction.json',aar:'aar.json',claim_ledger:'claim-ledger.json',source_snapshot:'source-snapshot.json',source_truth:'source-truth.json',documentation:'README.md'};
  pass(canonical(manifest.files) === canonical(expectedFileMap), 'manifest file map');
  for (const value of Object.values(manifest.files)) pass(!path.isAbsolute(value) && !value.includes('..') && path.basename(value) === value, `unsafe manifest path:${value}`);
  const hashMap = {interaction_sha256:'interaction.json',aar_sha256:'aar.json',claim_ledger_sha256:'claim-ledger.json',source_snapshot_sha256:'source-snapshot.json',source_truth_sha256:'source-truth.json',documentation_sha256:'README.md'};
  for (const [field,file] of Object.entries(hashMap)) pass(manifest.hashes[field] === fileSha(path.join(base,file)), `manifest hash:${field}`);
  pass(canonical(manifest.certificate) === canonical(cert), 'manifest certificate');
  pass(canonical(manifest.source_binding) === canonical(session.source_binding), 'manifest source binding');
  pass(manifest.generated_from.spec_sha256 === sha(spec), 'manifest spec binding');
  pass(manifest.generated_from.source_snapshot_sha256 === source.snapshot_sha256, 'manifest source snapshot binding');
  const manifestNoHash = Object.fromEntries(Object.entries(manifest).filter(([key]) => key !== 'manifest_sha256'));
  pass(manifest.manifest_sha256 === sha(manifestNoHash), 'manifest root hash');

  const rootReadme = fs.readFileSync(path.join(root,'README.md'),'utf8'); const exampleReadme = fs.readFileSync(path.join(base,'README.md'),'utf8');
  pass(rootReadme.includes('examples/facility-arrival/README.md'), 'root README example link');
  pass(rootReadme.includes('/examples/facility-arrival'), 'root README browser route');
  pass(exampleReadme.includes(cert.session_sha256), 'example README session hash');
  pass(exampleReadme.includes('NOT_CALIBRATED'), 'example README calibration disclosure');

  const report = { schema_version:'1.1.0', status: errors.length ? 'FAIL':'PASS', internal_error:false, checks, example_id:session.example_id, session_sha256:cert.session_sha256, errors:[...new Set(errors)].sort() };
  return report;
}

const args = process.argv.slice(2);
let root = process.cwd();
let output = null;
let report;
try {
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === '--repo') root = path.resolve(args[++index] ?? '.');
    else if (args[index] === '--output') output = path.resolve(args[++index] ?? '');
    else throw new Error(`unknown argument:${args[index]}`);
  }
  report = verify(root);
} catch (error) {
  report = {
    schema_version: '1.1.0',
    status: 'FAIL',
    internal_error: true,
    checks: 0,
    example_id: null,
    session_sha256: null,
    errors: [`checker internal error:${error instanceof Error ? error.name : 'UnknownError'}`],
  };
}
if (output) {
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, `${JSON.stringify(report, null, 2)}
`, 'utf8');
}
console.log(JSON.stringify(report, null, 2));
if (report.status !== 'PASS') process.exitCode = 1;
