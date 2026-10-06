import type { HospitalDepartmentId } from '@/types/providerProfile';

export type DeviceStatus =
  | 'waiting'
  | 'standby'
  | 'briefing'
  | 'in_simulation'
  | 'handoff_ready'
  | 'completed'
  | 'offline';

export interface ProviderDevice {
  deviceId: string;
  displayName: string;
  providerName: string;
  hospitalDepartment: HospitalDepartmentId;
  status: DeviceStatus;
  connectedAt: number;
  lastSeen: number;
  exerciseId?: string;
  exerciseStartedAt?: number;
}

export interface DeploymentPayload {
  deviceId: string;
  scenario: import('@/types').Scenario;
  scenarioConfig: import('@/types/witConfig').ScenarioConfiguration;
  exerciseMeta?: import('@/types/exercise').ExerciseDeploymentMeta;
}

export interface SessionSyncPayload {
  deviceId: string;
  session: import('@/types').SimulationSession;
  scenario: import('@/types').Scenario;
}
