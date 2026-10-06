import { INJURY_PROFILES } from '../content/injuryProfiles';
import { contentFingerprint } from './canonical';
import type {
  GeneratedResearchScenario,
  ScenarioValidationIssue,
  ScenarioValidationReport,
} from './types';

const HASH_PATTERN = /^[a-f0-9]{64}$/;
const VALID_ZONES = new Set([
  'head', 'neck', 'chest', 'abdomen', 'pelvis',
  'left_upper_arm', 'right_upper_arm', 'left_forearm', 'right_forearm',
  'left_thigh', 'right_thigh', 'left_lower_leg', 'right_lower_leg',
]);

function issue(code: string, path: string, message: string): ScenarioValidationIssue {
  return { code, path, message };
}

function finiteInRange(value: number, min: number, max: number): boolean {
  return Number.isFinite(value) && value >= min && value <= max;
}

export function validateGeneratedResearchScenario(
  generated: GeneratedResearchScenario,
): ScenarioValidationReport {
  const issues: ScenarioValidationIssue[] = [];
  let checked = 0;
  const check = (condition: boolean, nextIssue: ScenarioValidationIssue): void => {
    checked += 1;
    if (!condition) issues.push(nextIssue);
  };

  check(generated.authority.clinical_authority === 'NOT_GRANTED', issue('authority', 'authority.clinical_authority', 'Clinical authority must remain NOT_GRANTED.'));
  check(generated.authority.scoring_enabled === false, issue('scoring', 'authority.scoring_enabled', 'Scoring must remain disabled.'));
  check(generated.authority.deployment_mode === 'research_sandbox_only', issue('deployment', 'authority.deployment_mode', 'Generated research scenarios may only enter the research sandbox.'));

  const groups = generated.scenario.expected_actions;
  check(groups.critical.length === 0, issue('actions', 'scenario.expected_actions.critical', 'Generated research scenarios cannot define critical actions.'));
  check(groups.important.length === 0, issue('actions', 'scenario.expected_actions.important', 'Generated research scenarios cannot define important actions.'));
  check(groups.optional.length === 0, issue('actions', 'scenario.expected_actions.optional', 'Generated research scenarios cannot define optional actions.'));
  check(groups.unsafe.length === 0, issue('actions', 'scenario.expected_actions.unsafe', 'Generated research scenarios cannot define unsafe actions.'));

  check(generated.scenario.casualty_count === generated.scenario.patients.length, issue('patient_count', 'scenario.casualty_count', 'Casualty count must match the patient array.'));
  const patientIds = generated.scenario.patients.map((patient) => patient.patient_id);
  check(new Set(patientIds).size === patientIds.length, issue('patient_id', 'scenario.patients', 'Patient IDs must be unique.'));
  check(generated.scenario.patients.length > 0, issue('patient_count', 'scenario.patients', 'At least one patient is required.'));

  for (const [index, patient] of generated.scenario.patients.entries()) {
    const base = `scenario.patients[${index}]`;
    check(patient.injury_profile_refs.length > 0 || (patient.visible_body_zones?.length ?? 0) > 0, issue('injury_map', base, 'Patient must include an injury reference or visible zone.'));
    for (const ref of patient.injury_profile_refs) {
      check(Boolean(INJURY_PROFILES[ref]), issue('injury_profile', `${base}.injury_profile_refs`, `Unknown injury profile ${ref}.`));
    }
    for (const zone of patient.visible_body_zones ?? []) {
      check(VALID_ZONES.has(zone.zone), issue('body_zone', `${base}.visible_body_zones`, `Unknown body zone ${zone.zone}.`));
    }
    const vitals = patient.initial_vitals;
    check(finiteInRange(vitals.hr, 20, 240), issue('vitals', `${base}.initial_vitals.hr`, 'Heart rate is outside the simulator range.'));
    check(finiteInRange(vitals.bp_systolic, 40, 260), issue('vitals', `${base}.initial_vitals.bp_systolic`, 'Systolic pressure is outside the simulator range.'));
    check(finiteInRange(vitals.bp_diastolic, 20, 180), issue('vitals', `${base}.initial_vitals.bp_diastolic`, 'Diastolic pressure is outside the simulator range.'));
    check(vitals.bp_systolic > vitals.bp_diastolic, issue('vitals', `${base}.initial_vitals`, 'Systolic pressure must exceed diastolic pressure.'));
    check(finiteInRange(vitals.rr, 4, 60), issue('vitals', `${base}.initial_vitals.rr`, 'Respiratory rate is outside the simulator range.'));
    check(finiteInRange(vitals.spo2, 50, 100), issue('vitals', `${base}.initial_vitals.spo2`, 'Oxygen saturation is outside the simulator range.'));
    check(finiteInRange(vitals.temp_c, 28, 43), issue('vitals', `${base}.initial_vitals.temp_c`, 'Temperature is outside the simulator range.'));
    check(Number.isInteger(vitals.gcs) && finiteInRange(vitals.gcs, 3, 15), issue('vitals', `${base}.initial_vitals.gcs`, 'GCS must be an integer from 3 to 15.'));
  }

  check(generated.evidence.length > 0 && generated.evidence.length <= 6, issue('evidence_count', 'evidence', 'One to six evidence citations are required.'));
  const evidenceIds = generated.evidence.map((citation) => citation.evidence_id);
  check(new Set(evidenceIds).size === evidenceIds.length, issue('evidence_id', 'evidence', 'Evidence citations must be unique.'));
  for (const [index, citation] of generated.evidence.entries()) {
    const base = `evidence[${index}]`;
    check(Boolean(citation.doi), issue('citation', `${base}.doi`, 'DOI is required.'));
    check(Boolean(citation.locator), issue('citation', `${base}.locator`, 'Section locator is required.'));
    check(HASH_PATTERN.test(citation.chunk_sha256), issue('hash', `${base}.chunk_sha256`, 'Chunk SHA-256 is malformed.'));
    check(HASH_PATTERN.test(citation.source_file_sha256), issue('hash', `${base}.source_file_sha256`, 'Source SHA-256 is malformed.'));
  }

  const traces = generated.field_provenance;
  check(traces.length >= 3, issue('provenance', 'field_provenance', 'Core generated fields require provenance traces.'));
  const cited = new Set(evidenceIds);
  for (const [index, trace] of traces.entries()) {
    check(trace.evidence_ids.every((id) => cited.has(id)), issue('provenance', `field_provenance[${index}].evidence_ids`, 'Field trace references unknown evidence.'));
  }

  const { content_fingerprint: _fingerprint, ...withoutFingerprint } = generated;
  void _fingerprint;
  check(
    generated.content_fingerprint === contentFingerprint(withoutFingerprint),
    issue('fingerprint', 'content_fingerprint', 'Content fingerprint does not match the generated record.'),
  );

  return { status: issues.length === 0 ? 'PASS' : 'FAIL', issues, checked_invariants: checked };
}

export function assertGeneratedResearchScenario(generated: GeneratedResearchScenario): void {
  const report = validateGeneratedResearchScenario(generated);
  if (report.status === 'FAIL') {
    throw new Error(report.issues.map((item) => `${item.path}: ${item.message}`).join('\n'));
  }
}
