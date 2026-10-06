import { create } from 'zustand';
import type {
  AARReport,
  FeedEntry,
  Scenario,
  ScoringTrace,
  SimulationSession,
  UserActionRecord,
  UserRole,
} from '@/types';
import type { ScenarioConfiguration } from '@/types/witConfig';
import { DEFAULT_SCENARIO_CONFIG } from '@/types/witConfig';
import { generateAAR } from '@/engines/aarEngine';
import {
  detectAssessmentRequests,
  revealAssessments,
  summarizeAssessmentReveal,
} from '@/engines/assessmentRevealEngine';
import { expandScenarioPatients } from '@/engines/casualtyGenerator';
import { processDynamicTriageTurn } from '@/engines/casualtyTriageEngine';
import { buildProviderSessionBriefing } from '@/engines/providerScenarioBriefing';
import { applyScenarioConfiguration } from '@/engines/scenarioConfigurator';
import { evaluateFreeText } from '@/engines/freeTextEvaluator';
import {
  getClarificationNarrative,
  getImmediateNarrativeFeedback,
  getSupplyDepletedNarrative,
  getUnrecognizedNarrative,
} from '@/engines/providerFeedbackEngine';
import {
  applyPatientUpdates,
  buildUserActionRecord,
  checkEndConditions,
  getPatientResponse,
  scoreActions,
} from '@/engines/simulationEngine';
import { processTimePressureTurn } from '@/engines/timePressureEngine';
import {
  applyTurnDeterioration,
  applyTreatmentTimePressure,
} from '@/engines/vitalsEngine';
import {
  canPatientDie,
  canScenarioEnd,
  processTurnEvents,
} from '@/engines/witEventEngine';
import {
  buildSupplyInventory,
  consumeSupplyItem,
  getSupplyLimitsSummary,
  mapActionToSupplyItem,
} from '@/engines/supplyEngine';
import { scenariosById } from '@/content/scenarios';
import { setProviderStatus, syncSession } from '@/services/networkHub';
import type { ExerciseDeploymentMeta, PatientHandoffSnapshot } from '@/types/exercise';
import { buildHandoffSnapshot } from '@/types/exercise';

export type CasualtyViewMode = 'focused' | 'all';

interface SimulationStore {
  role: UserRole | null;
  deviceId: string | null;
  scenario: Scenario | null;
  scenarioConfig: ScenarioConfiguration;
  session: SimulationSession | null;
  aar: AARReport | null;
  casualtyViewMode: CasualtyViewMode;
  endexWarning: string | null;
  exerciseMeta: ExerciseDeploymentMeta | null;
  pendingHandoff: PatientHandoffSnapshot | null;
  setRole: (role: UserRole) => void;
  setDeviceId: (id: string) => void;
  setCasualtyViewMode: (mode: CasualtyViewMode) => void;
  setActivePatientId: (patientId: string) => void;
  loadDeployment: (
    scenario: Scenario,
    config: ScenarioConfiguration,
    exerciseMeta?: ExerciseDeploymentMeta,
  ) => void;
  deployConfiguredScenario: (config: ScenarioConfiguration) => void;
  startSession: () => void;
  submitAction: (rawText: string, targetPatientId?: string) => void;
  endSession: (reason?: string) => void;
  forceEndFromWit: () => void;
  dismissEndexWarning: () => void;
  clearPendingHandoff: () => void;
  clearForStandby: () => void;
  reset: () => void;
}

function createSessionId(): string {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function createFeedEntry(
  type: FeedEntry['type'],
  content: string,
  meta?: Partial<
    Pick<
      FeedEntry,
      'audience' | 'turn' | 'patient_id' | 'trigger_prompt' | 'heading' | 'bullets'
    >
  >,
): FeedEntry {
  return {
    id: `feed-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    timestamp: Date.now(),
    type,
    content,
    ...meta,
  };
}

function pushSessionUpdate(
  deviceId: string | null,
  scenario: Scenario | null,
  session: SimulationSession,
) {
  if (deviceId && scenario) {
    syncSession({ deviceId, session, scenario });
  }
}

function appendTurnAction(
  session: SimulationSession,
  turnId: number,
  rawText: string,
  recognized: UserActionRecord['recognized_actions'],
  scoreDelta: number,
  traces: ScoringTrace[],
  timestamp: number,
  updates: Partial<SimulationSession>,
): SimulationSession {
  const actionRecord = buildUserActionRecord(
    turnId,
    rawText,
    recognized,
    scoreDelta,
    traces,
    timestamp,
  );

  return {
    ...session,
    ...updates,
    actions: [...session.actions, actionRecord],
  };
}

function applyAssessmentToPatient(
  rawText: string,
  patientIndex: number,
  patients: SimulationSession['patients'],
  feed: SimulationSession['feed'],
  turn: number,
  triggerPrompt: string,
): {
  patients: SimulationSession['patients'];
  feed: SimulationSession['feed'];
  hadReveal: boolean;
} {
  const patient = patients[patientIndex];
  if (!patient) {
    return { patients, feed, hadReveal: false };
  }

  const keys = detectAssessmentRequests(rawText);
  if (keys.length === 0) {
    return { patients, feed, hadReveal: false };
  }

  const { patient: updated, messages, keys: revealedKeys } = revealAssessments(patient, keys);
  if (messages.length === 0) {
    return { patients, feed, hadReveal: false };
  }

  const nextPatients = [...patients];
  nextPatients[patientIndex] = updated;

  const nextFeed = [
    ...feed,
    createFeedEntry('response', summarizeAssessmentReveal(revealedKeys), {
      turn,
      patient_id: patient.patient_id,
      trigger_prompt: triggerPrompt,
    }),
  ];

  return { patients: nextPatients, feed: nextFeed, hadReveal: true };
}

function resolveTargetPatientIds(
  session: SimulationSession,
  mode: CasualtyViewMode,
  explicitId?: string,
): string[] {
  if (explicitId) return [explicitId];
  if (mode === 'all') return session.patients.map((p) => p.patient_id);
  return [session.active_patient_id];
}

export const useSimulationStore = create<SimulationStore>((set, get) => ({
  role: 'provider',
  deviceId: null,
  scenario: null,
  scenarioConfig: { ...DEFAULT_SCENARIO_CONFIG },
  session: null,
  aar: null,
  casualtyViewMode: 'focused',
  endexWarning: null,
  exerciseMeta: null,
  pendingHandoff: null,

  setRole: (role) => set({ role }),

  setDeviceId: (id) => set({ deviceId: id }),

  setCasualtyViewMode: (mode) => set({ casualtyViewMode: mode }),

  setActivePatientId: (patientId) => {
    const { session } = get();
    if (!session) return;
    set({ session: { ...session, active_patient_id: patientId } });
  },

  loadDeployment: (scenario, config, exerciseMeta) => {
    set({
      scenario,
      scenarioConfig: config,
      exerciseMeta: exerciseMeta ?? null,
      session: null,
      aar: null,
      pendingHandoff: null,
      role: 'provider',
    });
  },

  deployConfiguredScenario: (config) => {
    const base = scenariosById[config.baseScenarioId];
    if (!base) return;
    const scenario = applyScenarioConfiguration(base, config);
    set({
      scenarioConfig: config,
      scenario,
      session: null,
      aar: null,
      pendingHandoff: null,
      exerciseMeta: null,
      role: 'provider',
      endexWarning: null,
    });
  },

  startSession: () => {
    const { scenario, role, scenarioConfig, deviceId, exerciseMeta } = get();
    if (!scenario || !role) return;

    const expanded = expandScenarioPatients(scenario, scenarioConfig.casualties);
    const activeScenario = expanded.scenario;
    const patients = expanded.patients;
    const primary = activeScenario.patients[0];
    const inventory = buildSupplyInventory(
      scenarioConfig.supply,
      scenarioConfig.casualties.total,
    );
    const supplyNote = getSupplyLimitsSummary(scenarioConfig.supply, inventory);
    const briefingEntries = buildProviderSessionBriefing(
      activeScenario,
      scenarioConfig,
      supplyNote,
      {
        providerName: exerciseMeta?.providerName,
        hospitalDepartment: exerciseMeta?.segmentDepartment,
      },
      primary,
    );

    const session: SimulationSession = {
      id: createSessionId(),
      scenario_id: activeScenario.scenario_id,
      role,
      training_mode: 'trainee',
      status: 'active',
      score: 0,
      start_time: Date.now(),
      elapsed_seconds: 0,
      current_turn: 0,
      phase_of_care: 'Provider Clinical Response',
      active_patient_id: patients[0]?.patient_id ?? 'P1',
      feed: briefingEntries.map((entry) =>
        createFeedEntry(entry.type, entry.content, {
          heading: entry.heading,
          bullets: entry.bullets,
          audience: entry.audience,
          patient_id: entry.patient_id,
        }),
      ),
      actions: [],
      patients,
      completed_action_ids: [],
      missed_critical_ids: [],
      unsafe_action_ids: [],
      scoring_traces: [],
      supply_inventory: inventory,
      supply_status_note: supplyNote,
    };

    if (deviceId) {
      setProviderStatus(deviceId, 'in_simulation');
    }

    set({ scenario: activeScenario, session, aar: null });
    pushSessionUpdate(deviceId, activeScenario, session);
  },

  submitAction: (rawText, targetPatientId) => {
    const { scenario, session, scenarioConfig, deviceId, casualtyViewMode } = get();
    if (!scenario || !session || session.status !== 'active') return;

    const timestamp = Date.now();
    const nextTurn = session.current_turn + 1;
    const turnId = nextTurn;
    const elapsed_seconds = Math.floor((timestamp - session.start_time) / 1000);
    const elapsedMinutes = Math.floor(elapsed_seconds / 60);
    const targetIds = resolveTargetPatientIds(session, casualtyViewMode, targetPatientId);

    let feed = [
      ...session.feed,
      createFeedEntry('user', rawText, {
        turn: nextTurn,
        patient_id: targetIds.length === 1 ? targetIds[0] : undefined,
      }),
    ];

    const turnEvents = processTurnEvents(nextTurn, scenarioConfig);
    for (const narrative of turnEvents.narratives) {
      feed.push(
        createFeedEntry('system', narrative, {
          turn: nextTurn,
          trigger_prompt: rawText,
          audience: 'all',
        }),
      );
    }
    for (const alert of turnEvents.alerts) {
      feed.push(
        createFeedEntry('alert', alert, { turn: nextTurn, trigger_prompt: rawText }),
      );
    }

    const timePressure = processTimePressureTurn(nextTurn, elapsedMinutes, scenarioConfig);
    for (const narrative of timePressure.narratives) {
      feed.push(createFeedEntry('system', narrative, { turn: nextTurn, trigger_prompt: rawText }));
    }
    for (const alert of timePressure.alerts) {
      feed.push(createFeedEntry('alert', alert, { turn: nextTurn, trigger_prompt: rawText }));
    }

    const triageEvents = processDynamicTriageTurn(nextTurn, scenarioConfig.casualties);
    for (const narrative of triageEvents.narratives) {
      feed.push(createFeedEntry('system', narrative, { turn: nextTurn, trigger_prompt: rawText }));
    }
    for (const alert of triageEvents.alerts) {
      feed.push(createFeedEntry('alert', alert, { turn: nextTurn, trigger_prompt: rawText }));
    }

    let patients = [...session.patients];
    let hadReveal = false;

    for (const pid of targetIds) {
      const index = patients.findIndex((p) => p.patient_id === pid);
      if (index < 0) continue;
      const result = applyAssessmentToPatient(rawText, index, patients, feed, nextTurn, rawText);
      patients = result.patients;
      feed = result.feed;
      if (result.hadReveal) hadReveal = true;
    }

    const { recognized, ambiguous } = evaluateFreeText(rawText, scenario);

    if (ambiguous && recognized.length === 0 && !hadReveal) {
      feed.push(
        createFeedEntry('response', getClarificationNarrative(rawText), {
          turn: nextTurn,
          trigger_prompt: rawText,
        }),
      );
      const updated = appendTurnAction(session, turnId, rawText, [], 0, [], timestamp, {
        feed,
        patients,
        current_turn: nextTurn,
        elapsed_seconds,
      });
      set({ session: updated });
      pushSessionUpdate(deviceId, scenario, updated);
      return;
    }

    if (recognized.length === 0 && !hadReveal) {
      feed.push(
        createFeedEntry('response', getUnrecognizedNarrative(), {
          turn: nextTurn,
          trigger_prompt: rawText,
        }),
      );
      const updated = appendTurnAction(session, turnId, rawText, [], 0, [], timestamp, {
        feed,
        patients,
        current_turn: nextTurn,
        elapsed_seconds,
      });
      set({ session: updated });
      pushSessionUpdate(deviceId, scenario, updated);
      return;
    }

    const recognizedIds = recognized.map((r) => r.actionId);
    const { scoreDelta, traces, newCompleted, unsafe } = scoreActions(
      scenario,
      recognizedIds,
      session.completed_action_ids,
      timestamp,
    );

    let supply_inventory = [...session.supply_inventory];
    for (const actionId of newCompleted) {
      const supplyId = mapActionToSupplyItem(actionId);
      if (!supplyId) continue;
      const item = supply_inventory.find((i) => i.id === supplyId);
      const { inventory, consumed } = consumeSupplyItem(supply_inventory, supplyId);
      supply_inventory = inventory;
      if (!consumed && item) {
        feed.push(
          createFeedEntry('alert', getSupplyDepletedNarrative(item.label), {
            turn: nextTurn,
            trigger_prompt: rawText,
          }),
        );
      }
    }

    for (const pid of targetIds) {
      const index = patients.findIndex((p) => p.patient_id === pid);
      if (index < 0) continue;
      patients[index] = applyTurnDeterioration(
        patients[index],
        nextTurn,
        scenarioConfig.constraints.deterioration_interval_turns,
      );
      const pressure = applyTreatmentTimePressure(
        patients[index],
        elapsedMinutes,
        scenarioConfig.constraints.treatment_time_minutes,
      );
      patients[index] = pressure.patient;
      if (pressure.alert) {
        feed.push(
          createFeedEntry('alert', pressure.alert, {
            turn: nextTurn,
            patient_id: pid,
            trigger_prompt: rawText,
          }),
        );
      }
    }

    patients = patients.map((patient) => {
      if (!targetIds.includes(patient.patient_id)) return patient;
      return applyPatientUpdates([patient], newCompleted, scenario)[0];
    });

    const narrativeFeedback = getImmediateNarrativeFeedback(recognized, hadReveal);
    if (narrativeFeedback) {
      feed.push(
        createFeedEntry('response', narrativeFeedback, {
          turn: nextTurn,
          trigger_prompt: rawText,
          patient_id: targetIds[0],
        }),
      );
    }

    const patientResponse = getPatientResponse(newCompleted);
    if (patientResponse) {
      feed.push(
        createFeedEntry('patient', patientResponse, {
          turn: nextTurn,
          trigger_prompt: rawText,
          patient_id: targetIds[0],
        }),
      );
    }

    for (const trace of traces) {
      feed.push(
        createFeedEntry('evaluation', `${trace.points >= 0 ? '+' : ''}${trace.points}: ${trace.reason}`, {
          turn: nextTurn,
          audience: 'wit',
          trigger_prompt: rawText,
        }),
      );
    }

    const completed_action_ids = [...session.completed_action_ids, ...newCompleted];
    const unsafe_action_ids = [...new Set([...session.unsafe_action_ids, ...unsafe])];
    const score = Math.max(0, Math.min(100, session.score + scoreDelta));
    const scoring_traces = [...session.scoring_traces, ...traces];

    const hasCriticalUnsafe = unsafe.some((id) =>
      scenario.expected_actions.unsafe.some((a) => a.id === id),
    );
    const failAllowed = canPatientDie(nextTurn, scenarioConfig);
    const endCheck = checkEndConditions(
      scenario,
      completed_action_ids,
      score,
      hasCriticalUnsafe,
      nextTurn,
      failAllowed,
    );

    let updatedSession = appendTurnAction(
      session,
      turnId,
      rawText,
      recognized,
      scoreDelta,
      traces,
      timestamp,
      {
        feed,
        patients,
        completed_action_ids,
        unsafe_action_ids,
        score,
        scoring_traces,
        supply_inventory,
        current_turn: nextTurn,
        elapsed_seconds,
      },
    );

    const canEnd =
      endCheck.ended &&
      (endCheck.status === 'completed'
        ? canScenarioEnd(nextTurn, scenarioConfig, 'success')
        : canScenarioEnd(nextTurn, scenarioConfig, 'failure'));

    if (canEnd) {
      updatedSession = {
        ...updatedSession,
        status: endCheck.status,
        outcome: endCheck.outcome,
      };

      const { exerciseMeta } = get();

      if (
        endCheck.status === 'completed' &&
        exerciseMeta &&
        !exerciseMeta.isTerminal &&
        exerciseMeta.handoffTargets.length > 0
      ) {
        const snapshot = buildHandoffSnapshot(
          updatedSession,
          scenario,
          exerciseMeta.segmentDepartment,
          exerciseMeta.providerName ?? 'Provider',
          exerciseMeta.segmentLabel,
        );
        if (deviceId) setProviderStatus(deviceId, 'handoff_ready');
        set({ session: updatedSession, pendingHandoff: snapshot });
        pushSessionUpdate(deviceId, scenario, updatedSession);
        return;
      }

      const aar = generateAAR(updatedSession, scenario);
      if (deviceId) setProviderStatus(deviceId, 'completed');
      set({ session: updatedSession, aar, pendingHandoff: null });
      pushSessionUpdate(deviceId, scenario, updatedSession);
      return;
    }

    set({ session: updatedSession });
    pushSessionUpdate(deviceId, scenario, updatedSession);
  },

  endSession: (reason) => {
    const { scenario, session, deviceId } = get();
    if (!scenario || !session) return;

    const updatedSession: SimulationSession = {
      ...session,
      status: session.score >= 60 ? 'completed' : 'failed',
      outcome:
        reason ??
        session.outcome ??
        'Session ended by WIT evaluator. Review incomplete critical actions in AAR.',
      elapsed_seconds: Math.floor((Date.now() - session.start_time) / 1000),
    };

    const aar = generateAAR(updatedSession, scenario);
    if (deviceId) setProviderStatus(deviceId, 'completed');
    set({ session: updatedSession, aar, endexWarning: null });
    pushSessionUpdate(deviceId, scenario, updatedSession);
  },

  forceEndFromWit: () => {
    set({
      endexWarning:
        'WIT ENDEX: The evaluator has ended this exercise. You will be redirected to after-action review.',
    });
    get().endSession('Exercise ended by WIT evaluator (ENDEX).');
  },

  dismissEndexWarning: () => set({ endexWarning: null }),

  clearPendingHandoff: () => set({ pendingHandoff: null }),

  clearForStandby: () =>
    set({
      scenario: null,
      session: null,
      exerciseMeta: null,
      pendingHandoff: null,
      aar: null,
      scenarioConfig: { ...DEFAULT_SCENARIO_CONFIG },
    }),

  reset: () =>
    set({
      role: 'provider',
      deviceId: null,
      scenario: null,
      scenarioConfig: { ...DEFAULT_SCENARIO_CONFIG },
      session: null,
      aar: null,
      casualtyViewMode: 'focused',
      endexWarning: null,
      exerciseMeta: null,
      pendingHandoff: null,
    }),
}));
