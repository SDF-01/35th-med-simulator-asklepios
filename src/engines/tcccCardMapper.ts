import type { ScenarioPatient, PatientState, Vitals } from '@/types';
import type { BodyInjuryHighlight, BodyZone } from '@/types/bodyInjury';

export const TCCC_MOI_OPTIONS = [
  'Artillery',
  'Burn',
  'Fall',
  'Grenade',
  'GSW',
  'IED',
  'Landmine',
  'MVC',
  'RPG',
  'Other',
] as const;

export type TcccMoiOption = (typeof TCCC_MOI_OPTIONS)[number];
export type TcccTqLimb = 'r_arm' | 'l_arm' | 'r_leg' | 'l_leg';

export interface TcccTqEntry {
  type: string;
  time: string;
}

const ZONE_TO_TQ: Partial<Record<BodyZone, TcccTqLimb>> = {
  right_upper_arm: 'r_arm',
  right_forearm: 'r_arm',
  left_upper_arm: 'l_arm',
  left_forearm: 'l_arm',
  right_thigh: 'r_leg',
  right_lower_leg: 'r_leg',
  left_thigh: 'l_leg',
  left_lower_leg: 'l_leg',
};

const MOI_KEYWORDS: Record<TcccMoiOption, string[]> = {
  Artillery: ['artillery', 'indirect fire', 'mortar', 'rocket attack', 'missile'],
  Burn: ['burn', 'thermal'],
  Fall: ['fall', 'crush'],
  Grenade: ['grenade', 'fragmentation', 'frag'],
  GSW: ['gsw', 'gunshot', 'bullet'],
  IED: ['ied', 'improvised explosive'],
  Landmine: ['landmine', 'mine'],
  MVC: ['mvc', 'motor vehicle', 'vehicle accident', 'rollover'],
  RPG: ['rpg'],
  Other: [],
};

export function resolveMechanismChecks(mechanism: string): Record<TcccMoiOption, boolean> {
  const normalized = mechanism.toLowerCase();
  const checks = {} as Record<TcccMoiOption, boolean>;

  for (const option of TCCC_MOI_OPTIONS) {
    if (option === 'Other') continue;
    checks[option] = MOI_KEYWORDS[option].some((keyword) => normalized.includes(keyword));
  }

  checks.Other = !TCCC_MOI_OPTIONS.some((option) => option !== 'Other' && checks[option]);
  return checks;
}

export function resolveEvacCategory(
  triage?: PatientState['triage_category'],
): string {
  switch (triage) {
    case 'immediate':
      return 'URGENT';
    case 'delayed':
      return 'PRIORITY';
    case 'minimal':
      return 'ROUTINE';
    default:
      return '';
  }
}

export function formatTcccDate(timestamp: number): string {
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: '2-digit',
  })
    .format(new Date(timestamp))
    .replace(',', '')
    .toUpperCase();
}

export function formatTcccTime(timestamp: number): string {
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(timestamp));
}

export function resolveAvpu(gcs: number): string {
  if (gcs >= 15) return 'A';
  if (gcs >= 13) return 'V';
  if (gcs >= 9) return 'P';
  return 'U';
}

export function resolveTourniquetEntries(
  highlights: BodyInjuryHighlight[],
  interventions: string[],
  sessionStartTime?: number,
): Partial<Record<TcccTqLimb, TcccTqEntry>> {
  const applied =
    interventions.some((entry) => {
      const lower = entry.toLowerCase();
      return lower.includes('tourniquet') || lower.includes('hemorrhage control');
    }) ||
    highlights.some((h) => h.severity === 'controlled' && ZONE_TO_TQ[h.zone]);

  if (!applied) return {};

  const time = sessionStartTime ? formatTcccTime(sessionStartTime) : '';
  const entries: Partial<Record<TcccTqLimb, TcccTqEntry>> = {};

  for (const highlight of highlights) {
    if (highlight.severity !== 'controlled') continue;
    const limb = ZONE_TO_TQ[highlight.zone];
    if (!limb) continue;
    entries[limb] = { type: 'CAT', time };
  }

  return entries;
}

export function buildPatientDisplayName(patient: ScenarioPatient): string {
  const role = patient.role_context?.trim() || 'Unknown';
  const sex = patient.sex?.trim() || 'U';
  const age = patient.age_band?.trim() || '';
  return `${role}, ${sex}${age ? ` ${age}` : ''}`.trim();
}

export function buildTcccVitalsRow(
  vitals: Vitals,
  vitalsRevealed: boolean,
  timeLabel: string,
): {
  time: string;
  pulse: string;
  bp: string;
  rr: string;
  spo2: string;
  avpu: string;
  pain: string;
} {
  if (!vitalsRevealed) {
    return {
      time: timeLabel,
      pulse: '',
      bp: '',
      rr: '',
      spo2: '',
      avpu: '',
      pain: '',
    };
  }

  return {
    time: timeLabel,
    pulse: `${vitals.hr} / Radial`,
    bp: `${vitals.bp_systolic}/${vitals.bp_diastolic}`,
    rr: String(vitals.rr),
    spo2: `${vitals.spo2}%`,
    avpu: resolveAvpu(vitals.gcs),
    pain: vitals.gcs >= 14 ? '7' : '9',
  };
}

export function resolveMechanismOtherText(
  mechanism: string,
  checks: Record<TcccMoiOption, boolean>,
): string {
  if (!checks.Other) return '';
  return mechanism.trim();
}
