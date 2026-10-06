export interface LobbySummary {
  code: string;
  createdAt: number;
  deviceCount: number;
  activeExercise: {
    exerciseId: string;
    title: string;
    status: string;
    participantCount: number;
  } | null;
}

export interface CreateLobbyResponse {
  ok: boolean;
  code?: string;
  createdAt?: number;
  controllerCapability?: string;
  error?: string;
}
