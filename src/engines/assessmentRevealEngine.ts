import type { PatientState } from '@/types';
import { getAssessmentRevealMessage } from '@/engines/providerFeedbackEngine';

export type AssessmentKey =
  | 'vitals'
  | 'mental_status'
  | 'bleeding'
  | 'injuries'
  | 'breath_sounds'
  | 'circulation';

const ASSESSMENT_PATTERNS: Record<AssessmentKey, string[]> = {
  vitals: [
    'vitals',
    'vital signs',
    'check pulse',
    'check hr',
    'heart rate',
    'blood pressure',
    'bp',
    'spo2',
    'pulse ox',
    'oxygen saturation',
    'respiratory rate',
    'temp',
    'temperature',
    'monitor',
    'telemetry',
  ],
  mental_status: [
    'mental status',
    'gcs',
    'glasgow',
    'alert',
    'oriented',
    'aox',
    'level of consciousness',
    'loc',
    'confusion',
  ],
  bleeding: [
    'bleeding',
    'hemorrhage',
    'blood loss',
    'tourniquet',
    'wound',
    'hemostasis',
  ],
  injuries: [
    'injury',
    'injuries',
    'wound',
    'trauma survey',
    'secondary survey',
    'physical exam',
    'examine',
    'inspect',
  ],
  breath_sounds: [
    'breath sounds',
    'lung sounds',
    'auscultate',
    'breathing',
    'respiration',
    'airway',
  ],
  circulation: [
    'circulation',
    'perfusion',
    'cap refill',
    'capillary refill',
    'pulse quality',
    'shock',
  ],
};

function normalize(text: string): string {
  return text.toLowerCase().replace(/[^\w\s]/g, ' ').replace(/\s+/g, ' ').trim();
}

export function detectAssessmentRequests(text: string): AssessmentKey[] {
  const normalized = normalize(text);
  const found: AssessmentKey[] = [];

  for (const [key, patterns] of Object.entries(ASSESSMENT_PATTERNS) as [
    AssessmentKey,
    string[],
  ][]) {
    if (patterns.some((p) => normalized.includes(p))) {
      found.push(key);
    }
  }

  // Broad primary survey only when the provider did not name a specific domain.
  const isBroadSurvey =
    normalized.includes('assess') ||
    normalized.includes('evaluate patient') ||
    normalized.includes('primary survey');

  if (isBroadSurvey && found.length === 0) {
    found.push('vitals', 'mental_status', 'breath_sounds');
  }

  return [...new Set(found)];
}

/** One feed line when multiple assessment domains unlock at once. */
export function summarizeAssessmentReveal(keys: AssessmentKey[]): string {
  if (keys.length === 1) {
    return getAssessmentRevealMessage(keys[0]);
  }
  return 'Primary survey expanded. Check vitals strip and Monitor tab for new findings.';
}

export function formatVitalsReading(patient: PatientState): string {
  const v = patient.vitals;
  return `Measured vitals. HR ${v.hr}, BP ${v.bp_systolic}/${v.bp_diastolic}, RR ${v.rr}, SpO2 ${v.spo2}%, Temp ${v.temp_c}C, GCS ${v.gcs}.`;
}

export function revealAssessments(
  patient: PatientState,
  keys: AssessmentKey[],
): { patient: PatientState; messages: string[]; keys: AssessmentKey[] } {
  const revealed = new Set(patient.revealed_assessments);
  const messages: string[] = [];
  const newlyRevealed: AssessmentKey[] = [];

  for (const key of keys) {
    if (revealed.has(key)) continue;
    revealed.add(key);
    newlyRevealed.push(key);
    messages.push(getAssessmentRevealMessage(key));
  }

  return {
    patient: { ...patient, revealed_assessments: [...revealed] },
    messages,
    keys: newlyRevealed,
  };
}

export function getSubjectiveHints(patient: PatientState): string[] {
  const hints: string[] = [];
  const v = patient.vitals;

  if (!patient.revealed_assessments.includes('vitals')) {
    if (v.hr > 100) hints.push('Pulse appears rapid. Not yet measured.');
    if (v.bp_systolic < 100) hints.push('Skin pale and diaphoretic. Perfusion uncertain.');
    if (v.rr > 20) hints.push('Increased work of breathing. Rate not confirmed.');
    if (v.spo2 < 95) hints.push('Possible hypoxia. SpO2 not on monitor.');
  }

  if (!patient.revealed_assessments.includes('mental_status')) {
    hints.push('Patient appears anxious and confused. Formal neuro exam not done.');
  }

  if (!patient.revealed_assessments.includes('bleeding')) {
    hints.push('Dressings or bandaging present. Extent of bleeding unclear.');
  }

  if (!patient.revealed_assessments.includes('injuries')) {
    hints.push('Trauma noted. Full injury survey not completed.');
  }

  if (!patient.revealed_assessments.includes('breath_sounds')) {
    hints.push('Patient work of breathing appears increased. Auscultation not done.');
  }

  if (hints.length === 0) {
    hints.push('Continue assessment to confirm clinical findings.');
  }

  return hints;
}
