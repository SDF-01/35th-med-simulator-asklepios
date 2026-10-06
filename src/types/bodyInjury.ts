export type BodyZone =
  | 'head'
  | 'neck'
  | 'chest'
  | 'abdomen'
  | 'pelvis'
  | 'left_upper_arm'
  | 'right_upper_arm'
  | 'left_forearm'
  | 'right_forearm'
  | 'left_thigh'
  | 'right_thigh'
  | 'left_lower_leg'
  | 'right_lower_leg';

export type InjuryHighlightSeverity = 'visible' | 'controlled' | 'suspected';

export interface BodyInjuryHighlight {
  zone: BodyZone;
  label: string;
  severity: InjuryHighlightSeverity;
}

export const BODY_ZONE_LABELS: Record<BodyZone, string> = {
  head: 'Head',
  neck: 'Neck',
  chest: 'Chest',
  abdomen: 'Abdomen',
  pelvis: 'Pelvis',
  left_upper_arm: 'L Upper Arm',
  right_upper_arm: 'R Upper Arm',
  left_forearm: 'L Forearm',
  right_forearm: 'R Forearm',
  left_thigh: 'L Thigh',
  right_thigh: 'R Thigh',
  left_lower_leg: 'L Lower Leg',
  right_lower_leg: 'R Lower Leg',
};
