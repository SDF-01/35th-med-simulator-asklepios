export interface HubHealthResponse {
  ok: boolean;
  service: string;
  version: string;
  uptimeSeconds: number;
  devices: number;
  lobbies?: number;
  activeExercises?: number;
  intendedUse?: string;
  clinicalDecisionSupport?: boolean;
  directPatientCare?: boolean;
  activeExercise: {
    exerciseId: string;
    title: string;
    status: string;
    participantCount: number;
  } | null;
}
