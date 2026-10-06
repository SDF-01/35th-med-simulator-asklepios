import type { FactorConstraint, FactorValues } from './coverage';
import type { ScenarioBlueprint } from './types';

export const FIELD_VARIANT_BLUEPRINT: ScenarioBlueprint = {
  blueprint_id: 'ASK-BP-FIELD-001',
  blueprint_version: '1.1.0',
  mode: 'template_locked',
  source_scenario_id: 'ASK-A-001',
  allowed_topics: [
    'massive_hemorrhage',
    'airway',
    'respiration_chest',
    'evacuation_transport',
    'documentation_aar',
  ],
  mutable_paths: [
    'scenario.scenario_id',
    'scenario.title',
    'scenario.version',
    'scenario.fictionalization_notice',
    'scenario.operational_context.location_type',
    'scenario.operational_context.weather',
    'scenario.operational_context.visibility',
    'scenario.operational_context.comms_status',
    'scenario.operational_context.resource_status',
    'scenario.operational_context.narrative',
  ],
  location_options: [
    'flightline maintenance lane',
    'aircraft shelter access road',
    'logistics staging apron',
    'damaged operations perimeter',
  ],
  weather_options: [
    'clear with cold crosswind',
    'light rain with standing water',
    'cold wind with intermittent smoke',
    'dry conditions with reduced visibility',
  ],
  visibility_options: ['Good', 'Variable', 'Reduced'],
  communications_options: ['degraded', 'intermittent', 'unavailable'],
  resource_options: ['constrained', 'overwhelmed'],
  resource_event_options: [
    'transport route changes while the team prepares handoff',
    'communications become intermittent during casualty movement',
    'a second response task temporarily reduces available personnel',
    'equipment access is delayed by a relocation order',
  ],
  route_template_id: 'ASK-ROUTE-FIELD-001',
};

export const SCENARIO_BLUEPRINTS: readonly ScenarioBlueprint[] = [FIELD_VARIANT_BLUEPRINT];

export function getScenarioBlueprint(blueprintId: string): ScenarioBlueprint | undefined {
  return SCENARIO_BLUEPRINTS.find((item) => item.blueprint_id === blueprintId);
}


/** Finite operational space used by the deterministic variant selector. */
export const FIELD_VARIANT_OPERATIONAL_FACTORS: FactorValues = {
  location: FIELD_VARIANT_BLUEPRINT.location_options,
  weather: FIELD_VARIANT_BLUEPRINT.weather_options,
  visibility: FIELD_VARIANT_BLUEPRINT.visibility_options,
  communications: FIELD_VARIANT_BLUEPRINT.communications_options,
  resources: FIELD_VARIANT_BLUEPRINT.resource_options,
  resource_event: FIELD_VARIANT_BLUEPRINT.resource_event_options,
};

/**
 * Only reviewed nonclinical feasibility rules belong here. The current finite
 * pools have no impossible combinations, so the honest constraint set is empty.
 */
export const FIELD_VARIANT_OPERATIONAL_CONSTRAINTS: readonly FactorConstraint[] = [];
export const FIELD_VARIANT_OPERATIONAL_COVERAGE_STRENGTH = 3 as const;
