import type { CasualtyConfiguration, DynamicTriageMode, TriageCategory } from '@/types/witConfig';

export const TRIAGE_LABELS: Record<TriageCategory, string> = {
  immediate: 'Immediate',
  delayed: 'Delayed',
  minimal: 'Minimal',
};

export const DYNAMIC_TRIAGE_OPTIONS: {
  id: DynamicTriageMode;
  label: string;
  description: string;
}[] = [
  {
    id: 'static',
    label: 'Static triage',
    description: 'Categories remain fixed for the entire evolution.',
  },
  {
    id: 'deterioration',
    label: 'Clinical deterioration',
    description: 'Delayed/minimal casualties may upgrade to immediate if untreated.',
  },
  {
    id: 're_triage',
    label: 'Periodic re-triage',
    description: 'Scene re-triage shifts categories every few turns based on evolving conditions.',
  },
  {
    id: 'surge_escalation',
    label: 'Surge escalation',
    description: 'Additional casualties arrive; triage mix intensifies over the evolution.',
  },
];

export function triageSum(triage: CasualtyConfiguration['triage']): number {
  return triage.immediate + triage.delayed + triage.minimal;
}

export function isCasualtyConfigValid(casualties: CasualtyConfiguration): boolean {
  if (casualties.total < 1 || casualties.total > 20) return false;
  return triageSum(casualties.triage) === casualties.total;
}

export function defaultTriageForTotal(total: number): CasualtyConfiguration['triage'] {
  if (total <= 1) {
    return { immediate: 1, delayed: 0, minimal: 0 };
  }
  const immediate = Math.max(1, Math.floor(total * 0.2));
  const delayed = Math.max(0, Math.floor(total * 0.35));
  const minimal = Math.max(0, total - immediate - delayed);
  return { immediate, delayed, minimal };
}

export function adjustCasualtyTotal(
  casualties: CasualtyConfiguration,
  nextTotal: number,
): CasualtyConfiguration {
  const total = Math.max(1, Math.min(20, nextTotal));
  if (total === casualties.total) return casualties;

  if (total > casualties.total) {
    const delta = total - casualties.total;
    return {
      ...casualties,
      total,
      triage: {
        ...casualties.triage,
        minimal: casualties.triage.minimal + delta,
      },
    };
  }

  let remaining = casualties.total - total;
  const triage = { ...casualties.triage };

  for (const key of ['minimal', 'delayed', 'immediate'] as TriageCategory[]) {
    if (remaining <= 0) break;
    const reduce = Math.min(triage[key], remaining);
    triage[key] -= reduce;
    remaining -= reduce;
  }

  return { ...casualties, total, triage };
}

export function adjustTriageCategory(
  casualties: CasualtyConfiguration,
  category: TriageCategory,
  delta: number,
): CasualtyConfiguration {
  const nextValue = casualties.triage[category] + delta;
  if (nextValue < 0) return casualties;

  const nextSum = triageSum(casualties.triage) + delta;
  if (nextSum > casualties.total) return casualties;

  return {
    ...casualties,
    triage: {
      ...casualties.triage,
      [category]: nextValue,
    },
  };
}

export function formatTriageSummary(casualties: CasualtyConfiguration): string {
  const { triage, total, dynamicTriage } = casualties;
  const mode =
    DYNAMIC_TRIAGE_OPTIONS.find((o) => o.id === dynamicTriage)?.label ?? dynamicTriage;
  return (
    `${total} casualties. Immediate: ${triage.immediate}, Delayed: ${triage.delayed}, ` +
    `Minimal: ${triage.minimal}. Dynamic triage: ${mode}.`
  );
}

export function getCasualtyBriefingLines(casualties: CasualtyConfiguration): string[] {
  const lines = [
    `Casualty load: ${casualties.total} total.`,
    `Triage distribution. Immediate: ${casualties.triage.immediate}, Delayed: ${casualties.triage.delayed}, Minimal: ${casualties.triage.minimal}.`,
  ];

  if (casualties.dynamicTriage !== 'static') {
    const option = DYNAMIC_TRIAGE_OPTIONS.find((o) => o.id === casualties.dynamicTriage);
    lines.push(`Dynamic triage active: ${option?.description ?? casualties.dynamicTriage}`);
  }

  return lines;
}

export function processDynamicTriageTurn(
  turn: number,
  casualties: CasualtyConfiguration,
): { narratives: string[]; alerts: string[] } {
  if (casualties.dynamicTriage === 'static' || turn < 2) {
    return { narratives: [], alerts: [] };
  }

  const narratives: string[] = [];
  const alerts: string[] = [];

  switch (casualties.dynamicTriage) {
    case 'deterioration':
      if (turn === 3 && casualties.triage.delayed > 0) {
        alerts.push(
          'TRIAGE UPDATE: One delayed casualty is deteriorating. Consider upgrading to immediate.',
        );
      }
      if (turn === 5 && casualties.triage.minimal > 0) {
        alerts.push(
          'TRIAGE UPDATE: A minimal casualty now presents with worsening symptoms. Re-triage required.',
        );
      }
      if (turn === 7 && casualties.triage.delayed + casualties.triage.minimal > 0) {
        alerts.push(
          'TRIAGE UPDATE: Untreated casualties are upgrading priority. Reassess all patients.',
        );
      }
      break;

    case 're_triage':
      if (turn % 4 === 0) {
        narratives.push(
          `Re-triage at turn ${turn}: Scene commander requests updated triage tags for all ${casualties.total} casualties.`,
        );
        if (casualties.triage.delayed > 0) {
          alerts.push('One delayed casualty re-triaged to immediate based on new vitals.');
        }
      }
      break;

    case 'surge_escalation':
      if (turn === 4) {
        alerts.push(
          'SURGE: Additional casualties inbound. Expect triage category mix to intensify.',
        );
      }
      if (turn === 6) {
        narratives.push(
          'Second wave arrived. Immediate category workload increasing. Prioritize life threats.',
        );
      }
      if (turn === 8 && casualties.total >= 3) {
        alerts.push('MCI triage board updated: immediate count effectively increased by surge.');
      }
      break;

    default:
      break;
  }

  return { narratives, alerts };
}
