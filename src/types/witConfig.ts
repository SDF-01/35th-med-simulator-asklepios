import type { CommsStatus, ResourceStatus } from '@/types';
import type { ScenarioSelection } from '@/content/scenarioTaxonomy';
import { DEFAULT_SCENARIO_SELECTION } from '@/content/scenarioTaxonomy';

export type TriageCategory = 'immediate' | 'delayed' | 'minimal';

export type DynamicTriageMode =
  | 'static'
  | 'deterioration'
  | 're_triage'
  | 'surge_escalation';

export type SupplyLevel = 'full' | 'limited' | 'critical_shortage';

export type WitEventType =
  | 'block_patient_death'
  | 'block_scenario_end'
  | 'inject_narrative'
  | 'inject_complication'
  | 'unlock_deterioration';

export type AiFeatureId =
  | 'dynamic_vitals'
  | 'progressive_diagnostics'
  | 'adaptive_complications'
  | 'synonym_expansion'
  | 'narrative_variation';

export interface CasualtyConfiguration {
  total: number;
  triage: Record<TriageCategory, number>;
  dynamicTriage: DynamicTriageMode;
}

export interface WitSimulatorEvent {
  id: string;
  trigger_turn: number;
  type: WitEventType;
  label: string;
  description: string;
  params?: Record<string, number | string>;
}

export interface ScenarioConfiguration {
  baseScenarioId: string;
  scenarioSelection: ScenarioSelection;
  aiEnhanced: boolean;
  aiFeatures: AiFeatureId[];
  casualties: CasualtyConfiguration;
  constraints: {
    comms_status: CommsStatus;
    resource_status: ResourceStatus;
    environmental_notes: string;
    /** Minutes available for active treatment before surge/complications escalate */
    treatment_time_minutes: number;
    /** Turn interval for ambient deterioration when treatment is delayed */
    deterioration_interval_turns: number;
  };
  supply: SupplyLevel;
  timeLimitMinutes: number;
  dispositionRequirements: string;
  witEvents: WitSimulatorEvent[];
}

export const AI_FEATURE_OPTIONS: { id: AiFeatureId; label: string }[] = [
  { id: 'dynamic_vitals', label: 'Dynamic vitals trending' },
  { id: 'progressive_diagnostics', label: 'Progressive diagnostic reveal' },
  { id: 'adaptive_complications', label: 'Adaptive complications' },
  { id: 'synonym_expansion', label: 'Expanded intent recognition' },
  { id: 'narrative_variation', label: 'AI narrative variation' },
];

export const SUPPLY_OPTIONS: { id: SupplyLevel; label: string; description: string }[] = [
  { id: 'full', label: 'Full supply', description: 'All standard medical supplies available' },
  { id: 'limited', label: 'Limited supply', description: 'Reduced stock; prioritization required' },
  {
    id: 'critical_shortage',
    label: 'Critical shortage',
    description: 'Severe constraints; alternate protocols required',
  },
];

export const DEFAULT_SCENARIO_CONFIG: ScenarioConfiguration = {
  baseScenarioId: 'ASK-D-001',
  scenarioSelection: { ...DEFAULT_SCENARIO_SELECTION },
  aiEnhanced: true,
  aiFeatures: ['dynamic_vitals', 'progressive_diagnostics', 'adaptive_complications'],
  casualties: {
    total: 1,
    triage: { immediate: 1, delayed: 0, minimal: 0 },
    dynamicTriage: 'static',
  },
  constraints: {
    comms_status: 'degraded',
    resource_status: 'constrained',
    environmental_notes: '',
    treatment_time_minutes: 15,
    deterioration_interval_turns: 3,
  },
  supply: 'limited',
  timeLimitMinutes: 20,
  dispositionRequirements: '',
  witEvents: [
    {
      id: 'evt-no-death-until-5',
      trigger_turn: 0,
      type: 'block_patient_death',
      label: 'Casualty survival floor',
      description: 'Patient cannot die or fail until turn 5',
      params: { min_turn: 5 },
    },
  ],
};
