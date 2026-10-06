import type { ScenarioPatient } from '@/types';
import type { BodyInjuryHighlight, BodyZone, InjuryHighlightSeverity } from '@/types/bodyInjury';
import { BODY_ZONE_LABELS } from '@/types/bodyInjury';
import { injuryProfileToHighlights } from '@/content/injuryProfiles';

const GENERIC_ZONE_LABELS: Record<InjuryHighlightSeverity, string> = {
  visible: 'Injury present',
  controlled: 'Injured, treated',
  suspected: 'Possible injury',
};

const SEVERITY_RANK: Record<InjuryHighlightSeverity, number> = {
  visible: 3,
  controlled: 2,
  suspected: 1,
};

function genericLabel(zone: BodyZone, severity: InjuryHighlightSeverity): string {
  return `${BODY_ZONE_LABELS[zone]}: ${GENERIC_ZONE_LABELS[severity]}`;
}

function mergeHighlights(
  existing: BodyInjuryHighlight[],
  next: BodyInjuryHighlight,
): BodyInjuryHighlight[] {
  const found = existing.find((h) => h.zone === next.zone);
  if (!found) return [...existing, next];

  if (SEVERITY_RANK[next.severity] >= SEVERITY_RANK[found.severity]) {
    return existing.map((h) => (h.zone === next.zone ? next : h));
  }
  return existing;
}

/**
 * Scenario injury catalog: explicit zones + registered profiles only.
 * Does not infer zones from free text (training fidelity).
 */
export function resolveScenarioInjuryCatalog(patient: ScenarioPatient): BodyInjuryHighlight[] {
  let highlights: BodyInjuryHighlight[] = [];

  for (const zoneEntry of patient.visible_body_zones ?? []) {
    highlights = mergeHighlights(highlights, {
      zone: zoneEntry.zone,
      severity: zoneEntry.severity,
      label: zoneEntry.label?.trim() || genericLabel(zoneEntry.zone, zoneEntry.severity),
    });
  }

  for (const ref of patient.injury_profile_refs ?? []) {
    for (const h of injuryProfileToHighlights(ref, genericLabel)) {
      const existing = highlights.find((e) => e.zone === h.zone);
      if (!existing) {
        highlights = mergeHighlights(highlights, h);
      }
    }
  }

  return highlights;
}

/** Injuries obvious at bedside before formal survey (visible severity only). */
export function resolveInitialVisibleInjuries(patient: ScenarioPatient): BodyInjuryHighlight[] {
  return resolveScenarioInjuryCatalog(patient).filter((h) => h.severity === 'visible');
}

/**
 * Provider-facing injury map: only scenario-declared zones, gated by assessment state.
 */
export function resolveDisplayedInjuryHighlights(
  scenarioPatient: ScenarioPatient,
  patientState: {
    body_zones: BodyInjuryHighlight[];
    revealed_assessments: string[];
  },
): BodyInjuryHighlight[] {
  const catalog = resolveScenarioInjuryCatalog(scenarioPatient);
  const injuriesRevealed = patientState.revealed_assessments.includes('injuries');
  const bleedingRevealed = patientState.revealed_assessments.includes('bleeding');

  let displayed = catalog.filter((h) => {
    if (h.severity === 'visible') return true;
    if (h.severity === 'controlled') return true;
    if (h.severity === 'suspected' && (injuriesRevealed || bleedingRevealed)) return true;
    return false;
  });

  displayed = displayed.map((h) => {
    const intervention = patientState.body_zones.find((b) => b.zone === h.zone);
    if (intervention && SEVERITY_RANK[intervention.severity] >= SEVERITY_RANK[h.severity]) {
      return intervention;
    }
    return h;
  });

  return displayed;
}

/** @deprecated Use resolveScenarioInjuryCatalog */
export function resolveScenarioBodyZones(patient: ScenarioPatient): BodyInjuryHighlight[] {
  return resolveScenarioInjuryCatalog(patient);
}

/** @deprecated Use resolveDisplayedInjuryHighlights */
export function resolveBodyInjuries(patient: ScenarioPatient): BodyInjuryHighlight[] {
  return resolveScenarioInjuryCatalog(patient);
}

export function resolveBodyInjuriesFromState(
  patient: ScenarioPatient,
  patientState: { body_zones: BodyInjuryHighlight[]; known_injuries: string[]; revealed_assessments: string[] },
): BodyInjuryHighlight[] {
  return resolveDisplayedInjuryHighlights(patient, patientState);
}

export function updateBodyZonesAfterIntervention(
  zones: BodyInjuryHighlight[],
  actionId: string,
): BodyInjuryHighlight[] {
  if (actionId !== 'hemorrhage_control') return zones;

  return zones.map((z) =>
    z.severity === 'visible' &&
    (z.zone.includes('thigh') || z.zone.includes('arm') || z.zone.includes('leg'))
      ? { ...z, severity: 'controlled' as const, label: genericLabel(z.zone, 'controlled') }
      : z,
  );
}
