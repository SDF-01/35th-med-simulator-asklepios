import type { CommsStatus, ResourceStatus } from '../types';

export const SCENARIO_OPERATIONAL_BEHAVIOR_PROFILE = 'REVIEWED_NONCLINICAL_OPERATIONAL_ROUTE_FAMILY_V1' as const;

export type ScenarioOperationalBehaviorProfileId =
  | 'DIRECT_HANDOFF_BASELINE'
  | 'COMMUNICATION_RELAY_REQUIRED'
  | 'RESOURCE_COORDINATION_REQUIRED'
  | 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION';

export interface ScenarioOperationalBehaviorProfile {
  schema_version: '1.0.0';
  profile_family: typeof SCENARIO_OPERATIONAL_BEHAVIOR_PROFILE;
  profile_id: ScenarioOperationalBehaviorProfileId;
  communications_constraint: 'BASELINE' | 'RELAY_REQUIRED';
  resource_constraint: 'BASELINE' | 'COORDINATION_REQUIRED';
  intermediate_handoff_steps: number;
  clinical_authority: 'NOT_GRANTED';
  human_behavior_calibration: 'STRUCTURAL_ONLY_NOT_CALIBRATED';
}

const PROFILES: Record<ScenarioOperationalBehaviorProfileId, ScenarioOperationalBehaviorProfile> = {
  DIRECT_HANDOFF_BASELINE: {
    schema_version: '1.0.0',
    profile_family: SCENARIO_OPERATIONAL_BEHAVIOR_PROFILE,
    profile_id: 'DIRECT_HANDOFF_BASELINE',
    communications_constraint: 'BASELINE',
    resource_constraint: 'BASELINE',
    intermediate_handoff_steps: 0,
    clinical_authority: 'NOT_GRANTED',
    human_behavior_calibration: 'STRUCTURAL_ONLY_NOT_CALIBRATED',
  },
  COMMUNICATION_RELAY_REQUIRED: {
    schema_version: '1.0.0',
    profile_family: SCENARIO_OPERATIONAL_BEHAVIOR_PROFILE,
    profile_id: 'COMMUNICATION_RELAY_REQUIRED',
    communications_constraint: 'RELAY_REQUIRED',
    resource_constraint: 'BASELINE',
    intermediate_handoff_steps: 1,
    clinical_authority: 'NOT_GRANTED',
    human_behavior_calibration: 'STRUCTURAL_ONLY_NOT_CALIBRATED',
  },
  RESOURCE_COORDINATION_REQUIRED: {
    schema_version: '1.0.0',
    profile_family: SCENARIO_OPERATIONAL_BEHAVIOR_PROFILE,
    profile_id: 'RESOURCE_COORDINATION_REQUIRED',
    communications_constraint: 'BASELINE',
    resource_constraint: 'COORDINATION_REQUIRED',
    intermediate_handoff_steps: 1,
    clinical_authority: 'NOT_GRANTED',
    human_behavior_calibration: 'STRUCTURAL_ONLY_NOT_CALIBRATED',
  },
  DUAL_CONSTRAINT_RELAY_AND_COORDINATION: {
    schema_version: '1.0.0',
    profile_family: SCENARIO_OPERATIONAL_BEHAVIOR_PROFILE,
    profile_id: 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
    communications_constraint: 'RELAY_REQUIRED',
    resource_constraint: 'COORDINATION_REQUIRED',
    intermediate_handoff_steps: 2,
    clinical_authority: 'NOT_GRANTED',
    human_behavior_calibration: 'STRUCTURAL_ONLY_NOT_CALIBRATED',
  },
};

export const SCENARIO_OPERATIONAL_BEHAVIOR_PROFILES: readonly ScenarioOperationalBehaviorProfile[] = Object.freeze(
  Object.values(PROFILES).map((profile) => Object.freeze({ ...profile })),
);

export function getScenarioOperationalBehaviorProfile(
  profileId: ScenarioOperationalBehaviorProfileId,
): ScenarioOperationalBehaviorProfile {
  return PROFILES[profileId];
}

export function resolveScenarioOperationalBehaviorProfile(
  communications: CommsStatus,
  resources: ResourceStatus,
): ScenarioOperationalBehaviorProfile {
  const relay = communications === 'intermittent' || communications === 'unavailable';
  const coordination = resources === 'overwhelmed';
  if (relay && coordination) return PROFILES.DUAL_CONSTRAINT_RELAY_AND_COORDINATION;
  if (relay) return PROFILES.COMMUNICATION_RELAY_REQUIRED;
  if (coordination) return PROFILES.RESOURCE_COORDINATION_REQUIRED;
  return PROFILES.DIRECT_HANDOFF_BASELINE;
}
