import type { RecognizedAction } from '@/types';

export function getImmediateNarrativeFeedback(
  recognized: RecognizedAction[],
  hadAssessmentReveal: boolean,
): string | null {
  if (hadAssessmentReveal) {
    return null;
  }

  if (recognized.length === 0) {
    return 'Continue assessment. Describe what you observe or what intervention you are taking.';
  }

  const labels = recognized.map((r) => r.label.toLowerCase());
  if (labels.some((l) => l.includes('hemorrhage') || l.includes('tourniquet'))) {
    return 'Intervention acknowledged. Reassess the casualty and monitor response.';
  }
  if (labels.some((l) => l.includes('airway') || l.includes('breathing'))) {
    return 'Airway/breathing assessment noted. Observe work of breathing and patient response.';
  }
  if (labels.some((l) => l.includes('evac') || l.includes('casevac'))) {
    return 'Evacuation request logged. Await transport coordination and continue stabilizing.';
  }
  if (labels.some((l) => l.includes('imaging') || l.includes('labs'))) {
    return 'Orders placed. Continue bedside monitoring while awaiting results.';
  }
  if (labels.some((l) => l.includes('escalat') || l.includes('disposition'))) {
    return 'Disposition update noted. Continue monitoring until handoff.';
  }

  return 'Action noted. Continue primary survey and reassessment.';
}

export function getAssessmentRevealMessage(assessmentKey: string): string {
  switch (assessmentKey) {
    case 'vitals':
      return 'Vitals updated on the monitor strip.';
    case 'mental_status':
      return 'Mental status noted. See Observations in Monitor tab.';
    case 'bleeding':
      return 'Bleeding assessment noted. Inspect dressings and extremities.';
    case 'injuries':
      return 'Injury survey updated. See body map in Monitor tab.';
    case 'breath_sounds':
      return 'Airway and breathing assessed. Note work of breathing.';
    case 'circulation':
      return 'Perfusion assessed. Check pulses and skin signs.';
    default:
      return 'Assessment recorded.';
  }
}

export function getClarificationNarrative(rawText: string): string {
  return `Unclear intent: "${rawText}". State a specific assessment, treatment, order, or handoff.`;
}

export function getUnrecognizedNarrative(): string {
  return 'No clinical action recognized. Examine the patient, request vitals, or state a treatment.';
}

export function getSupplyDepletedNarrative(itemLabel: string): string {
  return `Supply exhausted: ${itemLabel}. Adapt with available resources or request resupply.`;
}
