import type { ScenarioConfiguration } from '@/types/witConfig';

export function processTimePressureTurn(
  turn: number,
  elapsedMinutes: number,
  config: ScenarioConfiguration,
): { narratives: string[]; alerts: string[] } {
  const narratives: string[] = [];
  const alerts: string[] = [];
  const { treatment_time_minutes, deterioration_interval_turns } = config.constraints;

  if (treatment_time_minutes > 0 && elapsedMinutes >= treatment_time_minutes && turn > 1) {
    if (turn === Math.ceil(treatment_time_minutes) || turn % deterioration_interval_turns === 0) {
      alerts.push(
        'TIME PRESSURE: Treatment window exceeded. Casualty may deteriorate without definitive care.',
      );
    }
  }

  if (
    deterioration_interval_turns > 0 &&
    turn > 0 &&
    turn % deterioration_interval_turns === 0
  ) {
    const complicationRoll = (turn / deterioration_interval_turns) % 3;
    switch (complicationRoll) {
      case 1:
        alerts.push('COMPLICATION: Patient becoming more tachycardic. Reassess circulation.');
        break;
      case 2:
        narratives.push('Ambient noise increases. Secondary triage update requested.');
        break;
      default:
        alerts.push('COMPLICATION: Work of breathing increasing. Reassess airway and breathing.');
        break;
    }
  }

  if (config.constraints.environmental_notes.trim() && turn === 2) {
    narratives.push(config.constraints.environmental_notes.trim());
  }

  return { narratives, alerts };
}
