import type { BodyZone } from '@/types/bodyInjury';

export interface TcccFigureAnchor {
  cx: number;
  cy: number;
  pct?: string;
}

export const TCCC_FRONT_ORIGIN = { x: 108, y: 8 };
export const TCCC_BACK_ORIGIN = { x: 328, y: 8 };

const FRONT_LOCAL: Record<BodyZone, TcccFigureAnchor> = {
  head: { cx: 50, cy: 14, pct: '4.5' },
  neck: { cx: 50, cy: 26 },
  chest: { cx: 50, cy: 44, pct: '18' },
  abdomen: { cx: 50, cy: 56 },
  pelvis: { cx: 50, cy: 68, pct: '1' },
  left_upper_arm: { cx: 22, cy: 34, pct: '4.5' },
  right_upper_arm: { cx: 78, cy: 34, pct: '4.5' },
  left_forearm: { cx: 8, cy: 34 },
  right_forearm: { cx: 92, cy: 34 },
  left_thigh: { cx: 44, cy: 96, pct: '9' },
  right_thigh: { cx: 56, cy: 96, pct: '9' },
  left_lower_leg: { cx: 44, cy: 114 },
  right_lower_leg: { cx: 56, cy: 114 },
};

const BACK_LOCAL: Record<BodyZone, TcccFigureAnchor> = { ...FRONT_LOCAL };

export function tcccGlobalAnchor(view: 'front' | 'back', zone: BodyZone): TcccFigureAnchor {
  const origin = view === 'front' ? TCCC_FRONT_ORIGIN : TCCC_BACK_ORIGIN;
  const local = view === 'front' ? FRONT_LOCAL[zone] : BACK_LOCAL[zone];
  return {
    cx: origin.x + local.cx,
    cy: origin.y + local.cy,
    pct: local.pct,
  };
}

export const TCCC_TQ_PANELS: {
  id: 'l_arm' | 'r_arm' | 'l_leg' | 'r_leg';
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
}[] = [
  { id: 'r_arm', label: 'TQ: R Arm', x: 8, y: 30, w: 58, h: 34 },
  { id: 'l_arm', label: 'TQ: L Arm', x: 494, y: 30, w: 58, h: 34 },
  { id: 'r_leg', label: 'TQ: R Leg', x: 8, y: 132, w: 58, h: 34 },
  { id: 'l_leg', label: 'TQ: L Leg', x: 494, y: 132, w: 58, h: 34 },
];

export const TCCC_MOI_ROW_A = ['Artillery', 'Burn', 'Fall', 'Grenade', 'GSW', 'IED'] as const;
export const TCCC_MOI_ROW_B = ['Landmine', 'MVC', 'RPG', 'Other'] as const;

/** Primary diagram view for each zone (avoids duplicate X marks on both figures). */
export const TCCC_ZONE_VIEW: Record<BodyZone, 'front' | 'back'> = {
  head: 'front',
  neck: 'front',
  chest: 'front',
  abdomen: 'front',
  pelvis: 'front',
  left_upper_arm: 'front',
  right_upper_arm: 'front',
  left_forearm: 'front',
  right_forearm: 'front',
  left_thigh: 'front',
  right_thigh: 'front',
  left_lower_leg: 'front',
  right_lower_leg: 'front',
};
