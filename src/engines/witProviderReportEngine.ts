import type { AARReport, Scenario, SimulationSession } from '@/types';
import type { ScenarioConfiguration } from '@/types/witConfig';
import { generateAAR } from '@/engines/aarEngine';

export interface WitProviderReport {
  generated_at: string;
  provider_name: string;
  device_id: string;
  scenario_title: string;
  scenario_id: string;
  session_status: string;
  duration_seconds: number;
  total_turns: number;
  aar: AARReport;
  provider_inputs: {
    turn: number;
    time: string;
    raw_text: string;
    recognized: string[];
    score_delta: number;
  }[];
  assessments_confirmed: string[];
  learning_summary: string;
  remediation_plan: string[];
}

function formatElapsed(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function buildRemediation(aar: AARReport, session: SimulationSession): string[] {
  const plan: string[] = [];

  for (const item of aar.improvements) {
    plan.push(item);
  }

  for (const missed of aar.missed_critical) {
    if (!plan.some((p) => p.includes(missed))) {
      plan.push(`Drill critical action: ${missed}`);
    }
  }

  const unrecognizedTurns = session.actions.filter((a) => a.recognized_actions.length === 0);
  if (unrecognizedTurns.length > 0) {
    plan.push(
      `Review ${unrecognizedTurns.length} turn(s) where input was not mapped to doctrine. Use clearer clinical/command language.`,
    );
  }

  for (const tp of aar.teaching_points.slice(0, 2)) {
    plan.push(`Study point: ${tp}`);
  }

  return plan.slice(0, 6);
}

export function generateWitProviderReport(
  session: SimulationSession,
  scenario: Scenario,
  providerName: string,
  deviceId: string,
  _config?: ScenarioConfiguration,
): WitProviderReport {
  const aar = generateAAR(session, scenario);
  const patient = session.patients[0];

  const provider_inputs = session.actions.map((action) => ({
    turn: action.turn_id,
    time: formatElapsed(action.timestamp - session.start_time),
    raw_text: action.raw_text,
    recognized: action.recognized_actions.map((r) => r.label),
    score_delta: action.score_delta,
  }));

  const userOnlyTurns = session.feed
    .filter((e) => e.type === 'user')
    .map((entry, index) => {
      const matched = session.actions.find((a) => a.raw_text === entry.content);
      return {
        turn: matched?.turn_id ?? index + 1,
        time: formatElapsed(entry.timestamp - session.start_time),
        raw_text: entry.content,
        recognized: matched?.recognized_actions.map((r) => r.label) ?? [],
        score_delta: matched?.score_delta ?? 0,
      };
    });

  const inputs = provider_inputs.length > 0 ? provider_inputs : userOnlyTurns;

  const assessments_confirmed = patient?.revealed_assessments ?? [];

  const learning_summary = [
    aar.bluf,
    aar.passed
      ? 'Provider met the training threshold. Reinforce sustain items during next evolution.'
      : 'Provider did not meet threshold. Focus remediation on missed critical actions and decision timing.',
    `Completed ${session.current_turn} turn(s) over ${formatElapsed(session.elapsed_seconds * 1000)}.`,
  ].join(' ');

  return {
    generated_at: new Date().toISOString(),
    provider_name: providerName,
    device_id: deviceId,
    scenario_title: scenario.title,
    scenario_id: scenario.scenario_id,
    session_status: session.status,
    duration_seconds: session.elapsed_seconds,
    total_turns: session.current_turn,
    aar,
    provider_inputs: inputs,
    assessments_confirmed,
    learning_summary,
    remediation_plan: buildRemediation(aar, session),
  };
}

export function reportToPlainText(report: WitProviderReport): string {
  const lines: string[] = [
    'PROJECT ASKLEPIOS: PROVIDER LEARNING REPORT',
    '==========================================',
    '',
    `Generated: ${new Date(report.generated_at).toLocaleString()}`,
    `Provider: ${report.provider_name}`,
    `Device: ${report.device_id}`,
    `Scenario: ${report.scenario_title} (${report.scenario_id})`,
    `Status: ${report.session_status}`,
    `Duration: ${formatElapsed(report.duration_seconds * 1000)} | Turns: ${report.total_turns}`,
    '',
    'EXECUTIVE SUMMARY',
    report.learning_summary,
    '',
    `Score: ${report.aar.score}/100 (Pass threshold: ${report.aar.pass_threshold})`,
    `Result: ${report.aar.passed ? 'PASS' : 'NEEDS IMPROVEMENT'}`,
    `Patient Outcome: ${report.aar.patient_outcome}`,
    '',
    'SUSTAIN',
    ...report.aar.strengths.map((s) => `- ${s}`),
    '',
    'IMPROVE',
    ...report.aar.improvements.map((i) => `- ${i}`),
    '',
    'PROVIDER INPUTS (FULL)',
    ...report.provider_inputs.map(
      (input) =>
        `Turn ${input.turn} [${input.time}]: "${input.raw_text}"${
          input.recognized.length ? ` => ${input.recognized.join('; ')}` : ' => (not recognized)'
        }`,
    ),
    '',
    'REMEDIATION PLAN',
    ...report.remediation_plan.map((r) => `- ${r}`),
  ];

  return lines.join('\n');
}
