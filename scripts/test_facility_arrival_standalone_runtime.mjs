#!/usr/bin/env node
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';

const args = process.argv.slice(2);
const repoIndex = args.indexOf('--repo');
const repo = resolve(repoIndex >= 0 ? args[repoIndex + 1] : '.');
const outputIndex = args.indexOf('--output');
const output = resolve(repo, outputIndex >= 0 ? args[outputIndex + 1] : 'reports/facility-arrival-standalone-runtime.json');
const html = readFileSync(resolve(repo, 'examples/facility-arrival/playable.html'), 'utf8');

function extract(id) {
  const expression = new RegExp(`<script\\b[^>]*\\bid=["']${id}["'][^>]*>([\\s\\S]*?)<\\/script>`, 'i');
  const match = expression.exec(html);
  if (!match) throw new Error(`script tag missing:${id}`);
  return match[1];
}

const baseData = JSON.parse(extract('asklepios-scenario-data').replaceAll('<\\/script>', '</script>'));
const engineSource = extract('asklepios-engine');
const sandbox = { console, JSON, Math, Number, String, Object, Array, Set, Map, Error };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(engineSource, sandbox, { filename: 'asklepios-standalone-engine.js' });
const engine = sandbox.AsklepiosStandaloneEngine;
const errors = [];
const checks = [];

function check(id, condition, detail = '') {
  const pass = Boolean(condition);
  checks.push({ id, pass, detail: pass ? '' : String(detail) });
  if (!pass) errors.push(`${id}${detail ? `:${detail}` : ''}`);
}

const PROFILE_IDS = [
  'DIRECT_HANDOFF_BASELINE',
  'COMMUNICATION_RELAY_REQUIRED',
  'RESOURCE_COORDINATION_REQUIRED',
  'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
];
const EXPECTED_ACTIONS = {
  DIRECT_HANDOFF_BASELINE: [],
  COMMUNICATION_RELAY_REQUIRED: ['establish_communications_relay'],
  RESOURCE_COORDINATION_REQUIRED: ['coordinate_constrained_resource'],
  DUAL_CONSTRAINT_RELAY_AND_COORDINATION: ['establish_communications_relay', 'coordinate_constrained_resource'],
};
const EXPECTED_ELAPSED = {
  DIRECT_HANDOFF_BASELINE: 645,
  COMMUNICATION_RELAY_REQUIRED: 690,
  RESOURCE_COORDINATION_REQUIRED: 690,
  DUAL_CONSTRAINT_RELAY_AND_COORDINATION: 735,
};

check('engine_exported', Boolean(engine && typeof engine.createSession === 'function'));
check('profile_api_exported', typeof engine.roleModelProfiles === 'function' && typeof engine.createProfiledData === 'function');
const advertised = engine.roleModelProfiles(baseData);
check('four_role_model_profiles_advertised', advertised.length === 4, String(advertised.length));
check('role_model_profile_order', JSON.stringify(advertised.map((item) => item.profile_id)) === JSON.stringify(PROFILE_IDS));
check('default_role_model_profile', baseData.default_role_model_profile_id === 'DIRECT_HANDOFF_BASELINE');

const profileSummaries = [];
for (const profileId of PROFILE_IDS) {
  const data = engine.createProfiledData(baseData, profileId);
  const expectedActions = EXPECTED_ACTIONS[profileId];
  const profile = data.active_role_model_profile;
  check(`${profileId}:active_profile`, profile?.profile_id === profileId, profile?.profile_id || 'missing');
  check(`${profileId}:role_model_identity`, typeof profile?.role_model_id === 'string' && profile.role_model_id.startsWith('ASK-OFFLINE-RM-'));
  check(`${profileId}:required_action_inventory`, JSON.stringify(profile.required_operational_actions) === JSON.stringify(expectedActions));
  check(`${profileId}:source_boundary`, profile.clinical_authority === 'NOT_GRANTED' && profile.scoring_effect === 'ZERO_CLINICAL_POINTS');
  check(`${profileId}:calibration_boundary`, profile.human_behavior_calibration === 'STRUCTURAL_ONLY_NOT_CALIBRATED');

  const initial = engine.createSession(data);
  check(`${profileId}:initial_active`, initial.terminal_status === 'active', initial.terminal_status);
  check(`${profileId}:initial_hidden_findings`, Array.isArray(initial.visible_findings) && initial.visible_findings.length === 0);
  check(`${profileId}:initial_profile_bound`, initial.operational_profile_id === profileId, initial.operational_profile_id);
  check(`${profileId}:initial_role_model_bound`, initial.role_model_id === profile.role_model_id, initial.role_model_id);
  check(`${profileId}:initial_teamwork_alert`, initial.alerts.some((item) => item.includes('Teamwork challenge:')));
  check(`${profileId}:initial_score_zero`, initial.normalized_score_bps === 0, String(initial.normalized_score_bps));
  const initialActions = engine.availableActions(initial, data).map((item) => item.action_id).sort();
  check(`${profileId}:initial_receive_enabled`, initialActions.includes('receive_handoff'));
  check(`${profileId}:initial_primary_blocked`, !initialActions.includes('primary_assessment'));

  const injected = data.spec.actions.filter((item) => ['establish_communications_relay', 'coordinate_constrained_resource'].includes(item.action_id));
  check(`${profileId}:injected_action_count`, injected.length === expectedActions.length, `${injected.length}`);
  check(`${profileId}:injected_actions_exact`, JSON.stringify(injected.map((item) => item.action_id)) === JSON.stringify(expectedActions));
  for (const action of injected) {
    check(`${profileId}:${action.action_id}:operational_origin`, action.origin === 'operational_workflow', action.origin);
    check(`${profileId}:${action.action_id}:no_source_action`, action.source_action_id === null, String(action.source_action_id));
    check(`${profileId}:${action.action_id}:fixed_45_seconds`, action.duration_seconds === 45, String(action.duration_seconds));
  }

  const completeIndex = data.spec.canonical_command_sequence.indexOf('complete_handoff');
  check(`${profileId}:canonical_complete_present`, completeIndex >= 0, String(completeIndex));
  check(`${profileId}:required_actions_before_handoff`, expectedActions.every((actionId) => data.spec.canonical_command_sequence.indexOf(actionId) >= 0 && data.spec.canonical_command_sequence.indexOf(actionId) < completeIndex));
  check(`${profileId}:handoff_prerequisites_bound`, expectedActions.every((actionId) => data.spec.actions.find((item) => item.action_id === 'complete_handoff')?.prerequisites.includes(actionId)));

  // Prove that the final handoff cannot bypass the profile-specific teamwork route.
  let beforeTeamwork = engine.createSession(data);
  for (const actionId of data.spec.canonical_command_sequence) {
    if (actionId === 'complete_handoff' || expectedActions.includes(actionId)) continue;
    const result = engine.applyAction(beforeTeamwork, actionId, data);
    check(`${profileId}:prefix_accepts:${actionId}`, result.accepted, result.reasons?.join(',') || '');
    if (!result.accepted) break;
    beforeTeamwork = result.state;
  }
  const bypass = engine.applyAction(beforeTeamwork, 'complete_handoff', data);
  check(`${profileId}:handoff_bypass_${expectedActions.length ? 'rejected' : 'accepted'}`, expectedActions.length ? !bypass.accepted : bypass.accepted, bypass.reasons?.join(',') || '');
  if (expectedActions.length) {
    check(`${profileId}:handoff_bypass_reason`, expectedActions.every((actionId) => bypass.reasons.includes(`missing_prerequisite:${actionId}`)), bypass.reasons.join(','));
  }

  if (profileId === 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION') {
    const resourceFirst = engine.applyAction(beforeTeamwork, 'coordinate_constrained_resource', data);
    check('dual_profile_relay_must_precede_resource', !resourceFirst.accepted && resourceFirst.reasons.includes('missing_prerequisite:establish_communications_relay'), resourceFirst.reasons.join(','));
  }

  const canonical = engine.runCanonical(data);
  const aar = engine.buildAar(canonical, data);
  check(`${profileId}:canonical_completed`, canonical.terminal_status === 'completed', canonical.terminal_status);
  check(`${profileId}:canonical_elapsed`, canonical.elapsed_seconds === EXPECTED_ELAPSED[profileId], String(canonical.elapsed_seconds));
  check(`${profileId}:canonical_score`, canonical.normalized_score_bps === 10000, String(canonical.normalized_score_bps));
  check(`${profileId}:canonical_diagnostics_event`, canonical.events.includes('diagnostics_ready'));
  check(`${profileId}:canonical_clock_event`, canonical.events.includes('second_casualty_inbound'));
  check(`${profileId}:canonical_hidden_findings_released`, JSON.stringify(canonical.visible_findings) === JSON.stringify(data.source_snapshot.patient.hidden_findings));
  check(`${profileId}:canonical_all_commands`, canonical.completed_actions.length === data.spec.canonical_command_sequence.length);
  check(`${profileId}:canonical_required_teamwork_completed`, expectedActions.every((actionId) => canonical.completed_actions.includes(actionId)));
  check(`${profileId}:canonical_operational_score_isolated`, canonical.timeline.filter((item) => expectedActions.includes(item.id)).every((item) => item.origin === 'operational_workflow' && item.clinical_points === 0 && item.source_action_id === null));
  check(`${profileId}:aar_profile_bound`, aar.operational_profile_id === profileId && aar.role_model_id === profile.role_model_id);
  check(`${profileId}:aar_teamwork_pass`, aar.teamwork_status === 'PASS', aar.teamwork_status);
  check(`${profileId}:aar_no_missed_teamwork`, aar.missed_teamwork_actions.length === 0, aar.missed_teamwork_actions.join(','));
  check(`${profileId}:aar_scoring_boundary`, aar.scoring_boundary === 'SOURCE_CONFORMANCE_ONLY' && aar.teamwork_actions_award_clinical_points === false);

  profileSummaries.push({
    profile_id: profileId,
    role_model_id: profile.role_model_id,
    terminal_status: canonical.terminal_status,
    elapsed_seconds: canonical.elapsed_seconds,
    score_bps: canonical.normalized_score_bps,
    required_teamwork_actions: expectedActions,
    teamwork_status: aar.teamwork_status,
  });
}

// Preserve the original clock-independence and unsafe-branch controls on the default profile.
const data = engine.createProfiledData(baseData, 'DIRECT_HANDOFF_BASELINE');
function runPrefix(sequence) {
  let state = engine.createSession(data);
  for (const actionId of sequence) {
    const result = engine.applyAction(state, actionId, data);
    check(`clock_prefix_accepts_${actionId}`, result.accepted, result.reasons?.join(',') || '');
    state = result.state;
  }
  return state;
}
const beforeClock = runPrefix(['receive_handoff', 'primary_assessment', 'monitor_vitals', 'differential']);
check('clock_event_absent_before_240', beforeClock.elapsed_seconds === 225 && !beforeClock.events.includes('second_casualty_inbound'), `${beforeClock.elapsed_seconds}:${beforeClock.events.join(',')}`);
const imagingCrossing = engine.applyAction(beforeClock, 'order_imaging', data).state;
const labsCrossing = engine.applyAction(beforeClock, 'order_labs', data).state;
check('clock_event_fires_after_imaging_crosses_240', imagingCrossing.elapsed_seconds === 255 && imagingCrossing.events.includes('second_casualty_inbound'));
check('clock_event_fires_after_labs_crosses_240', labsCrossing.elapsed_seconds === 255 && labsCrossing.events.includes('second_casualty_inbound'));
check('clock_event_is_action_independent', imagingCrossing.timeline.find((item) => item.id === 'second_casualty_inbound')?.elapsed_seconds === 255 && labsCrossing.timeline.find((item) => item.id === 'second_casualty_inbound')?.elapsed_seconds === 255);

const unsafeDischarge = engine.runUnsafe('discharge_without_workup', data);
check('unsafe_discharge_failed', unsafeDischarge.terminal_status === 'failed', unsafeDischarge.terminal_status);
check('unsafe_discharge_score_bounded', unsafeDischarge.normalized_score_bps === 0, String(unsafeDischarge.normalized_score_bps));
const unsafeTourniquet = engine.runUnsafe('remove_tourniquet', data);
check('unsafe_tourniquet_failed', unsafeTourniquet.terminal_status === 'failed', unsafeTourniquet.terminal_status);
const timeout = engine.runTimeout(data);
check('timeout_terminal', timeout.terminal_status === 'timeout', timeout.terminal_status);
check('timeout_exact_boundary', timeout.elapsed_seconds === Number(data.spec.parameters.timeout_seconds.value), String(timeout.elapsed_seconds));
check('timeout_event_present', timeout.events.includes('timeout_reached'));
check('timeout_hidden_findings_still_hidden', timeout.visible_findings.length === 0);

const report = {
  schema_version: '1.1.0',
  status: errors.length === 0 ? 'PASS' : 'FAIL',
  runtime: 'node:vm',
  checks: checks.length,
  playable_role_model_profiles: profileSummaries.length,
  role_model_profiles: profileSummaries,
  alternate_branches: {
    unsafe_discharge: unsafeDischarge.terminal_status,
    unsafe_tourniquet: unsafeTourniquet.terminal_status,
    timeout: timeout.terminal_status,
  },
  results: checks,
  errors,
};
mkdirSync(resolve(output, '..'), { recursive: true });
writeFileSync(output, JSON.stringify(report, null, 2) + '\n', 'utf8');
console.log(JSON.stringify(report, null, 2));
process.exit(errors.length === 0 ? 0 : 3);
