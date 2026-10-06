import type { AARReport, Scenario, SimulationSession } from '@/types';
import { getMissedCritical, getPassThreshold } from '@/engines/simulationEngine';

export function generateAAR(session: SimulationSession, scenario: Scenario): AARReport {
  const threshold = getPassThreshold(scenario.difficulty);
  const missed = getMissedCritical(scenario, session.completed_action_ids);

  const categoryScores = [
    {
      category: 'Lifesaving priorities',
      points: session.scoring_traces
        .filter((t) =>
          scenario.expected_actions.critical.some((a) => a.id === t.actionId),
        )
        .reduce((s, t) => s + Math.max(t.points, 0), 0),
      max_points: 35,
    },
    {
      category: 'Assessment quality',
      points: session.scoring_traces
        .filter((t) => ['airway_assessment', 'breathing_assessment', 'circulation_check'].includes(t.actionId))
        .reduce((s, t) => s + Math.max(t.points, 0), 0),
      max_points: 15,
    },
    {
      category: 'Treatment decisions',
      points: session.scoring_traces
        .filter((t) => t.actionId === 'hemorrhage_control')
        .reduce((s, t) => s + Math.max(t.points, 0), 0),
      max_points: 15,
    },
    {
      category: 'Communication / handoff',
      points: session.scoring_traces
        .filter((t) => t.actionId === 'evacuation_request')
        .reduce((s, t) => s + Math.max(t.points, 0), 0),
      max_points: 10,
    },
    {
      category: 'Documentation',
      points: session.scoring_traces
        .filter((t) => t.actionId === 'documentation')
        .reduce((s, t) => s + Math.max(t.points, 0), 0),
      max_points: 10,
    },
    {
      category: 'Resource management',
      points: session.scoring_traces
        .filter((t) => t.actionId === 'scene_safety')
        .reduce((s, t) => s + Math.max(t.points, 0), 0),
      max_points: 10,
    },
    {
      category: 'Professionalism / safety',
      points: session.unsafe_action_ids.length === 0 ? 5 : 0,
      max_points: 5,
    },
  ];

  const strengths: string[] = [];
  const improvements: string[] = [];

  if (session.completed_action_ids.includes('hemorrhage_control')) {
    strengths.push('Recognized and addressed massive hemorrhage priority.');
  } else {
    improvements.push('Missed critical hemorrhage control. Review MARCH prioritization.');
  }

  if (session.completed_action_ids.includes('scene_safety')) {
    strengths.push('Conducted scene safety / threat assessment.');
  } else {
    improvements.push('Scene safety assessment not documented. Maintain continuous threat awareness.');
  }

  if (session.completed_action_ids.includes('evacuation_request')) {
    strengths.push('Requested evacuation under degraded comms.');
  } else {
    improvements.push('Evacuation not requested. Initiate early under resource constraints.');
  }

  for (const unsafe of session.unsafe_action_ids) {
    const action = scenario.expected_actions.unsafe.find((a) => a.id === unsafe);
    if (action) {
      improvements.push(`Unsafe action: ${action.label}`);
    }
  }

  const timeline = session.actions.map((a) => ({
    time: formatElapsed(a.timestamp - session.start_time),
    event: a.recognized_actions.length
      ? a.recognized_actions.map((r) => r.label).join('; ')
      : a.raw_text,
  }));

  return {
    session_id: session.id,
    bluf:
      session.status === 'completed'
        ? `Training evolution complete. Score ${session.score}/100. ${session.outcome ?? ''}`
        : `Training evolution ended with deficiencies. Score ${session.score}/100.`,
    score: session.score,
    pass_threshold: threshold,
    passed: session.score >= threshold && session.status !== 'failed',
    patient_outcome: session.outcome ?? 'Unknown',
    score_breakdown: categoryScores,
    strengths,
    improvements,
    missed_critical: missed,
    unsafe_actions: session.unsafe_action_ids.map(
      (id) => scenario.expected_actions.unsafe.find((a) => a.id === id)?.label ?? id,
    ),
    timeline,
    teaching_points: scenario.aar_teaching_points,
    recommendations: improvements.slice(0, 3).map((i) => `Review: ${i}`),
  };
}

function formatElapsed(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}
