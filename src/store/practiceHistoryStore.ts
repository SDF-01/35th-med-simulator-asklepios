import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/** Max completed sessions kept in local browser storage. */
export const PRACTICE_HISTORY_LIMIT = 20;

export type PracticeMode = 'solo' | 'exercise';

export interface PracticeHistoryEntry {
  id: string;
  sessionId: string;
  completedAt: number;
  scenarioId: string;
  scenarioTitle: string;
  score: number;
  passed: boolean;
  patientOutcome: string;
  mode: PracticeMode;
  bluf: string;
}

export interface PracticeHistoryInput {
  sessionId: string;
  scenarioId: string;
  scenarioTitle: string;
  score: number;
  passed: boolean;
  patientOutcome: string;
  mode: PracticeMode;
  bluf: string;
  completedAt?: number;
}

interface PracticeHistoryState {
  entries: PracticeHistoryEntry[];
  recordPractice: (input: PracticeHistoryInput) => void;
  clearHistory: () => void;
}

function buildEntryId(sessionId: string, completedAt: number): string {
  return `${sessionId}-${completedAt}`;
}

export const usePracticeHistoryStore = create<PracticeHistoryState>()(
  persist(
    (set, get) => ({
      entries: [],

      recordPractice: (input) => {
        const completedAt = input.completedAt ?? Date.now();
        const existing = get().entries;
        if (existing.some((entry) => entry.sessionId === input.sessionId)) {
          return;
        }

        const next: PracticeHistoryEntry = {
          id: buildEntryId(input.sessionId, completedAt),
          sessionId: input.sessionId,
          completedAt,
          scenarioId: input.scenarioId,
          scenarioTitle: input.scenarioTitle.trim() || input.scenarioId,
          score: input.score,
          passed: input.passed,
          patientOutcome: input.patientOutcome,
          mode: input.mode,
          bluf: input.bluf,
        };

        set({
          entries: [next, ...existing].slice(0, PRACTICE_HISTORY_LIMIT),
        });
      },

      clearHistory: () => set({ entries: [] }),
    }),
    {
      name: 'asklepios-practice-history',
      version: 1,
      partialize: (state) => ({ entries: state.entries }),
    },
  ),
);
