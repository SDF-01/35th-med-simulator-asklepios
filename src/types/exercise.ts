import type { ScenarioConfiguration } from '@/types/witConfig';
import type { HospitalDepartmentId } from '@/types/providerProfile';
import type { Scenario, SimulationSession } from '@/types';
import type { ScenarioSelection } from '@/content/scenarioTaxonomy';

export type ExerciseDifficulty = 'intro' | 'intermediate' | 'advanced';
export type ChainArchetypeId = string;

export interface ExerciseSegmentDefinition {
  id: string;
  department: HospitalDepartmentId;
  label: string;
  briefingLead: string;
  baseScenarioId: string;
  handoffTargets: HospitalDepartmentId[];
  isEntryPoint?: boolean;
  isTerminal?: boolean;
}

export interface ExerciseTemplate {
  /** Permanent 6-character trackable catalog code */
  catalogId: string;
  id: string;
  title: string;
  description: string;
  eventSummary: string;
  scenarioSelection: ScenarioSelection;
  chainArchetype: ChainArchetypeId;
  difficulty: ExerciseDifficulty;
  estimatedMinutes: number;
  minProviders: number;
  segments: ExerciseSegmentDefinition[];
}

export interface PatientHandoffSnapshot {
  patientId: string;
  patientLabel: string;
  presentationSummary: string;
  vitalsSummary: string;
  injuriesSummary: string;
  completedCareSummary: string[];
  fromDepartment: HospitalDepartmentId;
  fromProviderName: string;
  fromSegmentLabel: string;
  handedOffAt: number;
}

export interface ExerciseDeploymentMeta {
  exerciseId: string;
  templateId: string;
  templateTitle: string;
  segmentId: string;
  segmentLabel: string;
  segmentDepartment: HospitalDepartmentId;
  segmentIndex: number;
  totalSegments: number;
  handoffTargets: HospitalDepartmentId[];
  isTerminal: boolean;
  exerciseStartedAt: number;
  providerName?: string;
  handoffSnapshot?: PatientHandoffSnapshot;
}

export interface ActiveExerciseState {
  exerciseId: string;
  templateId: string;
  title: string;
  startedAt: number;
  status: 'active' | 'completed';
  currentSegmentId: string;
  segmentIds: string[];
  participantDeviceIds: string[];
}

export interface ExerciseUpdatePayload {
  exercise: ActiveExerciseState | null;
  device?: import('@/types/device').ProviderDevice;
}

export interface SegmentNotificationPayload {
  exerciseId: string;
  templateTitle: string;
  segmentLabel: string;
  fromProviderName: string;
  fromDepartment: HospitalDepartmentId;
  message: string;
}

export interface HandoffRequestPayload {
  fromDeviceId: string;
  exerciseId: string;
  targetDepartment: HospitalDepartmentId;
  patientSnapshot: PatientHandoffSnapshot;
  targetDeployment: {
    scenario: Scenario;
    scenarioConfig: ScenarioConfiguration;
    exerciseMeta: ExerciseDeploymentMeta;
  };
}

export interface StartExercisePayload {
  exerciseId: string;
  templateId: string;
  title: string;
  startedAt: number;
  segments: Pick<
    ExerciseSegmentDefinition,
    'id' | 'department' | 'handoffTargets' | 'isTerminal' | 'label'
  >[];
  entrySegmentId: string;
  entryDeviceId: string;
  firstDeployment: {
    scenario: Scenario;
    scenarioConfig: ScenarioConfiguration;
    exerciseMeta: ExerciseDeploymentMeta;
  };
}

export function buildHandoffSnapshot(
  session: SimulationSession,
  scenario: Scenario,
  fromDepartment: HospitalDepartmentId,
  fromProviderName: string,
  fromSegmentLabel: string,
): PatientHandoffSnapshot {
  const patient = session.patients[0];
  const scenarioPatient = scenario.patients[0];
  const vitals = patient?.vitals;

  const vitalsSummary = vitals
    ? `HR ${vitals.hr}, BP ${vitals.bp_systolic}/${vitals.bp_diastolic}, RR ${vitals.rr}, SpO2 ${vitals.spo2}%, GCS ${vitals.gcs}`
    : 'Vitals unavailable. Reassess on arrival';

  const injuries =
    patient?.body_zones?.map((z) => z.label).join('; ') ||
    scenarioPatient?.initial_presentation ||
    'See handoff narrative';

  const completedLabels = session.completed_action_ids
    .map((id) => {
      const all = [
        ...scenario.expected_actions.critical,
        ...scenario.expected_actions.important,
        ...scenario.expected_actions.optional,
      ];
      return all.find((a) => a.id === id)?.label;
    })
    .filter(Boolean) as string[];

  return {
    patientId: patient?.patient_id ?? scenarioPatient?.patient_id ?? 'P1',
    patientLabel: scenarioPatient?.role_context ?? 'Casualty',
    presentationSummary:
      patient?.symptoms?.join('. ') ||
      scenarioPatient?.initial_presentation ||
      'Patient requires continued care',
    vitalsSummary,
    injuriesSummary: injuries,
    completedCareSummary: completedLabels.length > 0 ? completedLabels : ['Initial segment care documented'],
    fromDepartment,
    fromProviderName,
    fromSegmentLabel,
    handedOffAt: Date.now(),
  };
}
