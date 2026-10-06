import type { PatientState, Scenario, ScoringTrace, UserActionRecord } from '@/types';
import type { ExpectedAction } from '@/types';
import { resolveInitialVisibleInjuries, updateBodyZonesAfterIntervention } from '@/engines/injuryBodyMapper';
import { applyVitalsFromActions } from '@/engines/vitalsEngine';

const PASS_THRESHOLDS: Record<string, number> = {
  beginner: 70,
  intermediate: 78,
  advanced: 85,
  expert: 90,
};

export function getPassThreshold(difficulty: string): number {
  return PASS_THRESHOLDS[difficulty] ?? 78;
}

function findAction(scenario: Scenario, actionId: string): ExpectedAction | undefined {
  const groups = [
    scenario.expected_actions.critical,
    scenario.expected_actions.important,
    scenario.expected_actions.optional,
    scenario.expected_actions.unsafe,
  ];
  for (const group of groups) {
    const found = group.find((a) => a.id === actionId);
    if (found) return found;
  }
  return undefined;
}

export function scoreActions(
  scenario: Scenario,
  recognizedIds: string[],
  alreadyCompleted: string[],
  timestamp: number,
): { scoreDelta: number; traces: ScoringTrace[]; newCompleted: string[]; unsafe: string[] } {
  let scoreDelta = 0;
  const traces: ScoringTrace[] = [];
  const newCompleted: string[] = [];
  const unsafe: string[] = [];

  for (const id of recognizedIds) {
    if (alreadyCompleted.includes(id)) continue;

    const action = findAction(scenario, id);
    if (!action) continue;

    newCompleted.push(id);
    scoreDelta += action.points;

    if (action.priority === 'unsafe') {
      unsafe.push(id);
    }

    traces.push({
      actionId: id,
      label: action.label,
      points: action.points,
      reason:
        action.priority === 'unsafe'
          ? 'Unsafe action detected'
          : `Recognized: ${action.label}`,
      timestamp,
    });
  }

  return { scoreDelta, traces, newCompleted, unsafe };
}

export function buildUserActionRecord(
  turnId: number,
  rawText: string,
  recognized: UserActionRecord['recognized_actions'],
  scoreDelta: number,
  traces: ScoringTrace[],
  timestamp: number,
): UserActionRecord {
  const avgConfidence =
    recognized.length > 0
      ? recognized.reduce((sum, r) => sum + r.confidence, 0) / recognized.length
      : 0;

  return {
    turn_id: turnId,
    raw_text: rawText,
    recognized_actions: recognized,
    confidence: Math.round(avgConfidence * 100) / 100,
    score_delta: scoreDelta,
    scoring_traces: traces,
    timestamp,
  };
}

export function getMissedCritical(scenario: Scenario, completed: string[]): string[] {
  return scenario.expected_actions.critical
    .filter((a) => !completed.includes(a.id))
    .map((a) => a.label);
}

export function checkEndConditions(
  scenario: Scenario,
  completed: string[],
  score: number,
  hasCriticalUnsafe: boolean,
  _currentTurn: number,
  canFail: boolean,
): { ended: boolean; outcome: string; status: 'completed' | 'failed' } {
  if (hasCriticalUnsafe && score < 60 && canFail) {
    return {
      ended: true,
      outcome: 'Patient outcome compromised due to critical unsafe actions.',
      status: 'failed',
    };
  }

  const criticalIds = scenario.expected_actions.critical.map((a) => a.id);
  const allCriticalDone = criticalIds.every((id) => completed.includes(id));

  const completionActions = scenario.expected_actions.important.filter((a) =>
    ['evacuation_request', 'escalation'].includes(a.id),
  );
  const completionDone =
    completionActions.length === 0 ||
    completionActions.some((a) => completed.includes(a.id));

  if (allCriticalDone && completionDone) {
    const outcome =
      scenario.target_section === 'D_clinical'
        ? 'Workup initiated and disposition escalated. Patient prepared for next level of care.'
        : 'Patient stabilized and evacuation requested. Ready for handoff.';
    return {
      ended: true,
      outcome,
      status: 'completed',
    };
  }

  return { ended: false, outcome: '', status: 'completed' };
}

export function initialMarchState(): PatientState['march'] {
  return [
    { step: 'massive_hemorrhage', label: 'Massive Hemorrhage', status: 'critical' },
    { step: 'airway', label: 'Airway', status: 'pending' },
    { step: 'respiration', label: 'Respiration', status: 'pending' },
    { step: 'circulation', label: 'Circulation', status: 'pending' },
    { step: 'hypothermia_head', label: 'Hypothermia / Head', status: 'pending' },
    { step: 'pain', label: 'Pain', status: 'pending' },
    { step: 'antibiotics', label: 'Antibiotics', status: 'pending' },
    { step: 'wounds', label: 'Wounds', status: 'pending' },
    { step: 'splinting', label: 'Splinting', status: 'pending' },
  ];
}

export function createInitialPatientState(scenario: Scenario): PatientState[] {
  const isClinical = scenario.target_section === 'D_clinical';

  return scenario.patients.map((p) => ({
    patient_id: p.patient_id,
    display_label: 'Casualty 1',
    vitals: { ...p.initial_vitals },
    symptoms: isClinical
      ? ['Reports pain', 'Appears distressed']
      : ['Visible trauma', 'Anxiety'],
    known_injuries: isClinical
      ? ['Extremity injury. Assess on exam.']
      : ['Visible trauma. Assess on exam.'],
    revealed_findings: [],
    revealed_assessments: [],
    interventions: isClinical ? ['Prior field care may be present'] : [],
    march: initialMarchState(),
    mental_status: p.initial_vitals.gcs >= 13 ? 'Alert, distressed' : 'Altered',
    bleeding_status: isClinical
      ? 'Status unknown. Assess bleeding.'
      : 'Possible bleeding. Assess.',
    body_zones: resolveInitialVisibleInjuries(p),
  }));
}

export function applyPatientUpdates(
  patients: PatientState[],
  completedActionIds: string[],
  scenario: Scenario,
): PatientState[] {
  return patients.map((patient) => {
    const updated = { ...patient, vitals: { ...patient.vitals }, march: [...patient.march] };

    if (completedActionIds.includes('hemorrhage_control')) {
      updated.bleeding_status = 'Bleeding controlled after intervention';
      updated.interventions = [...updated.interventions, 'Hemorrhage control intervention applied'];
      updated.body_zones = updateBodyZonesAfterIntervention(updated.body_zones, 'hemorrhage_control');
      updated.march = updated.march.map((m) =>
        m.step === 'massive_hemorrhage' ? { ...m, status: 'addressed' as const } : m,
      );
    }

    if (completedActionIds.includes('airway_assessment')) {
      updated.march = updated.march.map((m) =>
        m.step === 'airway' ? { ...m, status: 'addressed' as const } : m,
      );
    }

    if (completedActionIds.includes('breathing_assessment')) {
      updated.march = updated.march.map((m) =>
        m.step === 'respiration' ? { ...m, status: 'addressed' as const } : m,
      );
    }

    if (completedActionIds.includes('circulation_check')) {
      updated.march = updated.march.map((m) =>
        m.step === 'circulation' ? { ...m, status: 'addressed' as const } : m,
      );
    }

    if (completedActionIds.includes('hypothermia_prevention')) {
      updated.march = updated.march.map((m) =>
        m.step === 'hypothermia_head' ? { ...m, status: 'addressed' as const } : m,
      );
    }

    if (completedActionIds.includes('evacuation_request')) {
      updated.interventions = [...updated.interventions, 'CASEVAC requested. Awaiting pickup.'];
    }

    const patientDef = scenario.patients.find((p) => p.patient_id === patient.patient_id);
    if (
      patientDef &&
      completedActionIds.includes('breathing_assessment') &&
      !updated.revealed_findings.includes(patientDef.hidden_findings[0] ?? '')
    ) {
      const finding = patientDef.hidden_findings[0];
      if (finding) {
        updated.revealed_findings = [...updated.revealed_findings, finding];
      }
    }

    return applyVitalsFromActions(updated, completedActionIds);
  });
}

export function getPatientResponse(completedActionIds: string[]): string | null {
  if (completedActionIds.includes('order_imaging')) {
    return 'Imaging order placed. Chest radiograph pending. Estimated 8 minute turnaround.';
  }
  if (completedActionIds.includes('order_labs')) {
    return 'Lab orders placed. Results pending.';
  }
  if (completedActionIds.includes('escalation')) {
    return 'Disposition updated. Surgery consult notified.';
  }
  if (completedActionIds.includes('hemorrhage_control')) {
    return 'Bleeding slows significantly after intervention. Patient remains alert but still in pain.';
  }
  if (completedActionIds.includes('airway_assessment')) {
    return 'Airway patent. Patient speaking in short sentences.';
  }
  if (completedActionIds.includes('evacuation_request')) {
    return 'Evacuation channel acknowledged. ETA pending due to degraded comms.';
  }
  if (completedActionIds.includes('primary_assessment')) {
    return 'Patient remains tachycardic with diminished breath sounds on the left.';
  }
  return null;
}
