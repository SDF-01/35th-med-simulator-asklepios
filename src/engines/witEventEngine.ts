import type { ScenarioConfiguration, WitSimulatorEvent } from '@/types/witConfig';

export function getMinDeathTurn(events: WitSimulatorEvent[]): number | null {
  const block = events.find((e) => e.type === 'block_patient_death');
  if (!block?.params?.min_turn) return null;
  return Number(block.params.min_turn);
}

export function canPatientDie(currentTurn: number, config: ScenarioConfiguration): boolean {
  const minTurn = getMinDeathTurn(config.witEvents);
  if (minTurn === null) return true;
  return currentTurn >= minTurn;
}

export function canScenarioEnd(
  currentTurn: number,
  config: ScenarioConfiguration,
  endType: 'success' | 'failure',
): boolean {
  if (endType === 'success') return true;

  const blockEnd = config.witEvents.find((e) => e.type === 'block_scenario_end');
  if (blockEnd?.params?.min_turn && currentTurn < Number(blockEnd.params.min_turn)) {
    return false;
  }

  if (endType === 'failure' && !canPatientDie(currentTurn, config)) {
    return false;
  }

  return true;
}

export function processTurnEvents(
  turn: number,
  config: ScenarioConfiguration,
): { narratives: string[]; alerts: string[] } {
  const narratives: string[] = [];
  const alerts: string[] = [];

  for (const event of config.witEvents) {
    if (event.trigger_turn !== turn) continue;

    switch (event.type) {
      case 'inject_narrative':
        narratives.push(event.description);
        break;
      case 'inject_complication':
        alerts.push(event.description);
        break;
      case 'unlock_deterioration':
        alerts.push(`WIT event: ${event.label}. ${event.description}`);
        break;
      default:
        break;
    }
  }

  return { narratives, alerts };
}

export function getActiveWitRules(config: ScenarioConfiguration): string[] {
  return config.witEvents
    .filter((e) => e.trigger_turn === 0 || e.type === 'block_patient_death')
    .map((e) => `${e.label}: ${e.description}`);
}
