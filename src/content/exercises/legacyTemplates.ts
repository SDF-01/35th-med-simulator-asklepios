import type { ExerciseTemplate } from '@/types/exercise';

/** Legacy hand-authored templates kept for regression references. */
export const EXERCISE_TEMPLATES: ExerciseTemplate[] = [
  {
    catalogId: 'BLAST1',
    id: 'EX-BLAST-001',
    title: 'Blast Casualty: Field to Definitive Care',
    description:
      'Flightline fragmentation through clinic stabilization, imaging, and operative handoff. Exercises chain-of-care across response offices.',
    eventSummary:
      'Missile warning on base; single blast casualty with extremity hemorrhage and occult chest injury.',
    scenarioSelection: {
      categoryId: 'home_station',
      eventTypeId: 'inbound_missile',
      specificId: 'flightline_impact',
    },
    chainArchetype: 'FIELD_TO_OR',
    difficulty: 'intermediate',
    estimatedMinutes: 35,
    minProviders: 4,
    segments: [
      {
        id: 'blast-field',
        department: 'field_response_team',
        label: 'Point of injury: MARCH',
        briefingLead: 'Respond to flightline casualty under degraded comms and secondary threat.',
        baseScenarioId: 'ASK-A-001',
        handoffTargets: ['transport', 'clinical_immediate'],
        isEntryPoint: true,
      },
      {
        id: 'blast-transport',
        department: 'transport',
        label: 'CASEVAC en route',
        briefingLead: 'Receive field handoff and maintain care during movement to clinic.',
        baseScenarioId: 'ASK-A-001',
        handoffTargets: ['clinical_immediate'],
      },
      {
        id: 'blast-clinical',
        department: 'clinical_immediate',
        label: 'Clinic immediate bay',
        briefingLead: 'Stabilize blast casualty, order diagnostics, and prepare disposition.',
        baseScenarioId: 'ASK-D-001',
        handoffTargets: ['radiology', 'lab', 'surgery'],
      },
      {
        id: 'blast-radiology',
        department: 'radiology',
        label: 'Urgent chest imaging',
        briefingLead: 'Prioritize imaging for incoming blast casualty with chest pain.',
        baseScenarioId: 'ASK-D-001',
        handoffTargets: ['surgery', 'clinical_immediate'],
      },
      {
        id: 'blast-surgery',
        department: 'surgery',
        label: 'Operative triage & pre-op',
        briefingLead: 'Accept surgical consult handoff and prioritize OR queue.',
        baseScenarioId: 'ASK-D-001',
        handoffTargets: [],
        isTerminal: true,
      },
    ],
  },
];

export const exercisesById: Record<string, ExerciseTemplate> = Object.fromEntries(
  EXERCISE_TEMPLATES.map((t) => [t.id, t]),
);

export function getExerciseTemplate(id: string): ExerciseTemplate | undefined {
  return exercisesById[id];
}

export function getEntrySegment(template: ExerciseTemplate) {
  return template.segments.find((s) => s.isEntryPoint) ?? template.segments[0];
}

export function getSegmentById(template: ExerciseTemplate, segmentId: string) {
  return template.segments.find((s) => s.id === segmentId);
}

export function getNextSegmentForDepartment(
  template: ExerciseTemplate,
  segmentId: string,
  targetDepartment: string,
) {
  const current = getSegmentById(template, segmentId);
  if (!current?.handoffTargets.includes(targetDepartment as never)) return undefined;
  return template.segments.find((s) => s.department === targetDepartment);
}
