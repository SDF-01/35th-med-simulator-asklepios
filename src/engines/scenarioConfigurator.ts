import type { Scenario } from '@/types';
import type { HospitalDepartmentId } from '@/types/providerProfile';
import type { ScenarioConfiguration } from '@/types/witConfig';
import { getDepartmentPreferredSections } from '@/engines/scenarioResolver';

export function applyScenarioConfiguration(
  base: Scenario,
  config: ScenarioConfiguration,
  options?: {
    providerName?: string;
    hospitalDepartment?: HospitalDepartmentId;
  },
): Scenario {
  const departmentSections = options?.hospitalDepartment
    ? getDepartmentPreferredSections(options.hospitalDepartment)
    : [];

  const departmentObjectives =
    departmentSections.length > 0
      ? [`Department focus: ${departmentSections.join(', ')}`]
      : [];

  return {
    ...base,
    casualty_count: config.casualties.total,
    operational_context: {
      ...base.operational_context,
      comms_status: config.constraints.comms_status,
      resource_status: config.constraints.resource_status,
      narrative: base.operational_context.narrative.trim(),
    },
    end_conditions: {
      ...base.end_conditions,
      timeout_minutes: config.timeLimitMinutes,
    },
    training_objectives: [
      ...base.training_objectives,
      ...departmentObjectives,
      `Triage targets: ${config.casualties.triage.immediate} immediate, ${config.casualties.triage.delayed} delayed, ${config.casualties.triage.minimal} minimal`,
      ...(config.dispositionRequirements.trim() ? [config.dispositionRequirements.trim()] : []),
    ],
  };
}
