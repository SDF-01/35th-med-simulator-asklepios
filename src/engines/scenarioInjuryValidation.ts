import type { Scenario } from '@/types';
import type { BodyZone } from '@/types/bodyInjury';
import { INJURY_PROFILES } from '@/content/injuryProfiles';
import { scenarioList } from '@/content/scenarios';

const VALID_ZONES = new Set<string>([
  'head',
  'neck',
  'chest',
  'abdomen',
  'pelvis',
  'left_upper_arm',
  'right_upper_arm',
  'left_forearm',
  'right_forearm',
  'left_thigh',
  'right_thigh',
  'left_lower_leg',
  'right_lower_leg',
]);

export interface ScenarioInjuryValidationIssue {
  scenarioId: string;
  patientId: string;
  message: string;
}

/** Ensures every scenario patient can drive the provider casualty injury map. */
export function validateScenarioInjuryCoverage(scenario: Scenario): ScenarioInjuryValidationIssue[] {
  const issues: ScenarioInjuryValidationIssue[] = [];

  for (const patient of scenario.patients) {
    const hasExplicitZones = (patient.visible_body_zones?.length ?? 0) > 0;
    const refs = patient.injury_profile_refs ?? [];

    if (!hasExplicitZones && refs.length === 0) {
      issues.push({
        scenarioId: scenario.scenario_id,
        patientId: patient.patient_id,
        message:
          'Patient has no visible_body_zones and no injury_profile_refs — injury map will be empty.',
      });
    }

    for (const ref of refs) {
      if (!INJURY_PROFILES[ref]) {
        issues.push({
          scenarioId: scenario.scenario_id,
          patientId: patient.patient_id,
          message: `Unknown injury_profile_ref "${ref}" — register it in src/content/injuryProfiles.ts.`,
        });
      }
    }

    for (const zoneEntry of patient.visible_body_zones ?? []) {
      if (!VALID_ZONES.has(zoneEntry.zone)) {
        issues.push({
          scenarioId: scenario.scenario_id,
          patientId: patient.patient_id,
          message: `Invalid body zone "${zoneEntry.zone}" in visible_body_zones.`,
        });
      }
    }
  }

  return issues;
}

export function validateAllScenarios(scenarios: Scenario[] = scenarioList): ScenarioInjuryValidationIssue[] {
  return scenarios.flatMap(validateScenarioInjuryCoverage);
}

export function assertScenarioInjuryCoverage(scenarios: Scenario[] = scenarioList): void {
  const issues = validateAllScenarios(scenarios);
  if (issues.length === 0) return;

  const detail = issues
    .map((i) => `[${i.scenarioId} / ${i.patientId}] ${i.message}`)
    .join('\n');

  throw new Error(`Scenario injury map validation failed:\n${detail}`);
}

export type { BodyZone };
