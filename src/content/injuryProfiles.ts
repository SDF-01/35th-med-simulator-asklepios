/**
 * Canonical injury profile → body zone mapping for the provider casualty injury map.
 * Every injury_profile_refs value used in scenarios MUST be registered here.
 */
import type { BodyInjuryHighlight, BodyZone, InjuryHighlightSeverity } from '@/types/bodyInjury';

export interface InjuryProfileZone {
  zone: BodyZone;
  defaultSeverity: InjuryHighlightSeverity;
}

export interface InjuryProfileDefinition {
  id: string;
  description: string;
  zones: InjuryProfileZone[];
}

export const INJURY_PROFILES: Record<string, InjuryProfileDefinition> = {
  extremity_hemorrhage: {
    id: 'extremity_hemorrhage',
    description: 'Life-threatening extremity bleeding, typically lower extremity',
    zones: [{ zone: 'right_thigh', defaultSeverity: 'visible' }],
  },
  extremity_hemorrhage_controlled: {
    id: 'extremity_hemorrhage_controlled',
    description: 'Extremity hemorrhage with field tourniquet or dressing applied',
    zones: [{ zone: 'right_thigh', defaultSeverity: 'controlled' }],
  },
  blast_injury: {
    id: 'blast_injury',
    description: 'Primary or secondary blast injury to torso',
    zones: [
      { zone: 'chest', defaultSeverity: 'suspected' },
      { zone: 'abdomen', defaultSeverity: 'suspected' },
    ],
  },
  possible_tbi: {
    id: 'possible_tbi',
    description: 'Altered mental status or head mechanism. Assess for TBI.',
    zones: [{ zone: 'head', defaultSeverity: 'suspected' }],
  },
  possible_chest_contusion: {
    id: 'possible_chest_contusion',
    description: 'Chest pain, guarding, or respiratory complaint after trauma',
    zones: [{ zone: 'chest', defaultSeverity: 'suspected' }],
  },
  neck_trauma: {
    id: 'neck_trauma',
    description: 'C-spine or neck injury concern',
    zones: [{ zone: 'neck', defaultSeverity: 'suspected' }],
  },
  pelvis_fracture: {
    id: 'pelvis_fracture',
    description: 'Pelvic instability or high-energy pelvic mechanism',
    zones: [{ zone: 'pelvis', defaultSeverity: 'suspected' }],
  },
  left_extremity_hemorrhage: {
    id: 'left_extremity_hemorrhage',
    description: 'Left lower extremity hemorrhage',
    zones: [{ zone: 'left_thigh', defaultSeverity: 'visible' }],
  },

  burn_injury: {
    id: 'burn_injury',
    description: 'Thermal injury affecting an exposed extremity or torso',
    zones: [{ zone: 'right_forearm', defaultSeverity: 'visible' }],
  },
  inhalation_injury: {
    id: 'inhalation_injury',
    description: 'Smoke or thermal inhalation exposure concern',
    zones: [
      { zone: 'neck', defaultSeverity: 'suspected' },
      { zone: 'chest', defaultSeverity: 'suspected' },
    ],
  },
  toxic_exposure: {
    id: 'toxic_exposure',
    description: 'Toxic exposure with altered mental status and respiratory concern',
    zones: [
      { zone: 'head', defaultSeverity: 'suspected' },
      { zone: 'chest', defaultSeverity: 'suspected' },
    ],
  },
  upper_extremity_hemorrhage: {
    id: 'upper_extremity_hemorrhage',
    description: 'Upper extremity hemorrhage',
    zones: [{ zone: 'right_upper_arm', defaultSeverity: 'visible' }],
  },
};

export function injuryProfileToHighlights(
  profileId: string,
  genericLabel: (zone: BodyZone, severity: InjuryHighlightSeverity) => string,
): BodyInjuryHighlight[] {
  const profile = INJURY_PROFILES[profileId];
  if (!profile) return [];

  return profile.zones.map(({ zone, defaultSeverity }) => ({
    zone,
    severity: defaultSeverity,
    label: genericLabel(zone, defaultSeverity),
  }));
}

export function listRegisteredInjuryProfileIds(): string[] {
  return Object.keys(INJURY_PROFILES);
}
