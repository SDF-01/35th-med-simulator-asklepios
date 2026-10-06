import type { Scenario } from '../types';

/** Fields inherited from a reviewed repository template and never changed by this generator. */
export function protectedScenarioProjection(scenario: Scenario): object {
  return {
    training_objectives: scenario.training_objectives,
    target_section: scenario.target_section,
    target_role: scenario.target_role,
    skill_level: scenario.skill_level,
    difficulty: scenario.difficulty,
    threat_type: scenario.threat_type,
    casualty_count: scenario.casualty_count,
    patients: scenario.patients,
    expected_actions: scenario.expected_actions,
    end_conditions: scenario.end_conditions,
    aar_teaching_points: scenario.aar_teaching_points,
  };
}
