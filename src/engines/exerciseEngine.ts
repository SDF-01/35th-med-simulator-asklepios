import { scenariosById } from '@/content/scenarios';
import {
  getEntrySegment,
  getExerciseTemplate,
  getNextSegmentForDepartment,
  getSegmentById,
} from '@/content/exercises';
import { applyScenarioConfiguration } from '@/engines/scenarioConfigurator';
import type { Scenario } from '@/types';
import type {
  ExerciseDeploymentMeta,
  ExerciseSegmentDefinition,
  ExerciseTemplate,
  PatientHandoffSnapshot,
  StartExercisePayload,
} from '@/types/exercise';
import type { HospitalDepartmentId } from '@/types/providerProfile';
import { getDepartmentLabel } from '@/types/providerProfile';
import type { ScenarioConfiguration } from '@/types/witConfig';
import { DEFAULT_SCENARIO_CONFIG } from '@/types/witConfig';

const DEPARTMENT_ACTIONS: Partial<
  Record<HospitalDepartmentId, Pick<Scenario['expected_actions'], 'critical' | 'important'>>
> = {
  radiology: {
    critical: [
      {
        id: 'accept_handoff',
        label: 'Accept imaging handoff',
        priority: 'critical',
        synonyms: ['accept handoff', 'receive patient', 'handoff received', 'incoming patient'],
        points: 10,
      },
      {
        id: 'prioritize_study',
        label: 'Prioritize urgent imaging study',
        priority: 'critical',
        synonyms: ['prioritize', 'stat imaging', 'urgent x-ray', 'rush study', 'priority read'],
        points: 15,
      },
      {
        id: 'communicate_findings',
        label: 'Communicate critical imaging findings',
        priority: 'critical',
        synonyms: [
          'call clinical',
          'report findings',
          'critical result',
          'notify provider',
          'read complete',
          'pneumothorax',
        ],
        points: 20,
      },
    ],
    important: [
      {
        id: 'document_study',
        label: 'Document imaging report',
        priority: 'important',
        synonyms: ['document', 'report', 'finalize read', 'dictate'],
        points: 8,
      },
    ],
  },
  lab: {
    critical: [
      {
        id: 'accept_handoff',
        label: 'Accept lab handoff',
        priority: 'critical',
        synonyms: ['accept handoff', 'receive order', 'incoming specimen'],
        points: 10,
      },
      {
        id: 'prioritize_specimens',
        label: 'Prioritize stat specimens',
        priority: 'critical',
        synonyms: ['stat labs', 'prioritize specimen', 'rush labs', 'critical draw'],
        points: 15,
      },
      {
        id: 'communicate_critical_value',
        label: 'Communicate critical lab value',
        priority: 'critical',
        synonyms: ['critical value', 'call provider', 'notify clinical', 'panic value', 'result called'],
        points: 20,
      },
    ],
    important: [
      {
        id: 'document_results',
        label: 'Document and release results',
        priority: 'important',
        synonyms: ['release results', 'document', 'verify results'],
        points: 8,
      },
    ],
  },
  surgery: {
    critical: [
      {
        id: 'accept_handoff',
        label: 'Accept surgical handoff',
        priority: 'critical',
        synonyms: ['accept handoff', 'surgical consult', 'receive patient'],
        points: 10,
      },
      {
        id: 'operative_triage',
        label: 'Perform operative triage',
        priority: 'critical',
        synonyms: ['or triage', 'operative priority', 'surgical assessment', 'or queue'],
        points: 15,
      },
      {
        id: 'preop_plan',
        label: 'Establish pre-operative plan',
        priority: 'critical',
        synonyms: ['preop', 'pre-op plan', 'or prep', 'surgical plan', 'book or'],
        points: 20,
      },
    ],
    important: [
      {
        id: 'resource_allocation',
        label: 'Allocate OR resources',
        priority: 'important',
        synonyms: ['allocate resources', 'or availability', 'staffing', 'equipment'],
        points: 10,
      },
    ],
  },
  pharm: {
    critical: [
      {
        id: 'accept_handoff',
        label: 'Accept pharmacy handoff',
        priority: 'critical',
        synonyms: ['accept handoff', 'receive order', 'incoming order'],
        points: 10,
      },
      {
        id: 'allergy_check',
        label: 'Verify allergies and contraindications',
        priority: 'critical',
        synonyms: ['allergy check', 'contraindication', 'medication safety', 'verify allergies'],
        points: 15,
      },
      {
        id: 'dispense_priority',
        label: 'Prioritize medication dispensing',
        priority: 'critical',
        synonyms: ['dispense', 'fill order', 'priority med', 'stat medication'],
        points: 20,
      },
    ],
    important: [
      {
        id: 'document_pharmacy',
        label: 'Document pharmacy verification',
        priority: 'important',
        synonyms: ['document', 'verify order', 'pharmacy note'],
        points: 8,
      },
    ],
  },
  transport: {
    critical: [
      {
        id: 'accept_handoff',
        label: 'Accept field handoff for transport',
        priority: 'critical',
        synonyms: ['accept handoff', 'receive casualty', 'load patient'],
        points: 10,
      },
      {
        id: 'enroute_monitoring',
        label: 'Maintain en-route monitoring',
        priority: 'critical',
        synonyms: ['monitor en route', 'reassess vitals', 'transport care', 'en route assessment'],
        points: 15,
      },
      {
        id: 'destination_handoff',
        label: 'Coordinate destination handoff',
        priority: 'critical',
        synonyms: [
          'handoff to clinic',
          'notify receiving',
          'casevac complete',
          'medevac arrival',
          'transfer care',
        ],
        points: 20,
      },
    ],
    important: [
      {
        id: 'route_decision',
        label: 'Confirm route and destination',
        priority: 'important',
        synonyms: ['route', 'destination', 'evac route', 'clinic destination'],
        points: 8,
      },
    ],
  },
  triage: {
    critical: [
      {
        id: 'scene_safety',
        label: 'Establish triage sector safety',
        priority: 'critical',
        synonyms: ['scene safe', 'triage sector', 'security', 'sector established'],
        points: 10,
      },
      {
        id: 'triage_sort',
        label: 'Sort and tag casualties',
        priority: 'critical',
        synonyms: ['triage', 'sort', 'tag', 'salvageable', 'expectant', 'immediate delayed minimal'],
        points: 20,
      },
      {
        id: 'patient_handoff',
        label: 'Direct casualty to treatment lane',
        priority: 'critical',
        synonyms: ['send to clinical', 'handoff to treatment', 'route casualty', 'assign lane'],
        points: 15,
      },
    ],
    important: [
      {
        id: 'resource_report',
        label: 'Report triage status to command',
        priority: 'important',
        synonyms: ['sitrep', 'triage report', 'casualty count', 'update command'],
        points: 8,
      },
    ],
  },
};

function mergeActions(
  base: Scenario['expected_actions'],
  overrides?: Pick<Scenario['expected_actions'], 'critical' | 'important'>,
): Scenario['expected_actions'] {
  if (!overrides) return base;
  return {
    critical: overrides.critical ?? base.critical,
    important: overrides.important ?? base.important,
    optional: base.optional,
    unsafe: base.unsafe,
  };
}

function handoffNarrative(snapshot?: PatientHandoffSnapshot): string {
  if (!snapshot) return '';
  return [
    `HANDOFF from ${getDepartmentLabel(snapshot.fromDepartment)} (${snapshot.fromProviderName}):`,
    snapshot.presentationSummary,
    `Vitals: ${snapshot.vitalsSummary}.`,
    `Injuries: ${snapshot.injuriesSummary}.`,
    snapshot.completedCareSummary.length > 0
      ? `Care completed: ${snapshot.completedCareSummary.join('; ')}.`
      : undefined,
  ]
    .filter(Boolean)
    .join(' ');
}

export function buildSegmentScenario(
  segment: ExerciseSegmentDefinition,
  config: ScenarioConfiguration,
  context: {
    providerName?: string;
    hospitalDepartment: HospitalDepartmentId;
    handoffSnapshot?: PatientHandoffSnapshot;
  },
): Scenario {
  const base = scenariosById[segment.baseScenarioId];
  if (!base) {
    throw new Error(`Base scenario ${segment.baseScenarioId} not found`);
  }

  let scenario = applyScenarioConfiguration(base, config, {
    providerName: context.providerName,
    hospitalDepartment: context.hospitalDepartment,
  });

  const deptActions = DEPARTMENT_ACTIONS[segment.department];
  if (deptActions) {
    scenario = {
      ...scenario,
      scenario_id: `${scenario.scenario_id}-${segment.id}`,
      title: `${segment.label}: ${scenario.title}`,
      target_section:
        context.hospitalDepartment === 'radiology'
          ? 'E_radiology'
          : context.hospitalDepartment === 'lab'
            ? 'F_lab'
            : context.hospitalDepartment === 'pharm'
              ? 'G_pharmacy'
              : context.hospitalDepartment === 'surgery'
                ? 'H_surgery'
                : context.hospitalDepartment === 'transport'
                  ? 'B_transport'
                  : scenario.target_section,
      training_objectives: [
        segment.briefingLead,
        ...scenario.training_objectives.slice(0, 2),
      ],
      expected_actions: mergeActions(scenario.expected_actions, deptActions),
      operational_context: {
        ...scenario.operational_context,
        narrative: [handoffNarrative(context.handoffSnapshot), segment.briefingLead, scenario.operational_context.narrative]
          .filter(Boolean)
          .join(' '),
      },
      end_conditions: {
        ...scenario.end_conditions,
        success: segment.isTerminal
          ? ['Segment complete. Exercise chain finished.']
          : ['Segment objectives met. Ready for handoff.'],
      },
    };
  } else if (context.handoffSnapshot) {
    scenario = {
      ...scenario,
      operational_context: {
        ...scenario.operational_context,
        narrative: `${handoffNarrative(context.handoffSnapshot)} ${scenario.operational_context.narrative}`,
      },
    };
  }

  return scenario;
}

export function buildExerciseMeta(
  template: ExerciseTemplate,
  segment: ExerciseSegmentDefinition,
  exerciseId: string,
  exerciseStartedAt: number,
  providerName?: string,
  handoffSnapshot?: PatientHandoffSnapshot,
): ExerciseDeploymentMeta {
  const segmentIndex = template.segments.findIndex((s) => s.id === segment.id);
  return {
    exerciseId,
    templateId: template.id,
    templateTitle: template.title,
    segmentId: segment.id,
    segmentLabel: segment.label,
    segmentDepartment: segment.department,
    segmentIndex,
    totalSegments: template.segments.length,
    handoffTargets: segment.handoffTargets,
    isTerminal: Boolean(segment.isTerminal),
    exerciseStartedAt,
    providerName,
    handoffSnapshot,
  };
}

export function buildSegmentDeployment(
  templateId: string,
  segmentId: string,
  exerciseId: string,
  exerciseStartedAt: number,
  context: {
    providerName?: string;
    hospitalDepartment: HospitalDepartmentId;
    handoffSnapshot?: PatientHandoffSnapshot;
  },
  config: ScenarioConfiguration = DEFAULT_SCENARIO_CONFIG,
): { scenario: Scenario; scenarioConfig: ScenarioConfiguration; exerciseMeta: ExerciseDeploymentMeta } {
  const template = getExerciseTemplate(templateId);
  if (!template) throw new Error(`Exercise template ${templateId} not found`);

  const segment = getSegmentById(template, segmentId);
  if (!segment) throw new Error(`Segment ${segmentId} not found`);

  const deployConfig: ScenarioConfiguration = {
    ...config,
    baseScenarioId: segment.baseScenarioId,
  };

  const scenario = buildSegmentScenario(segment, deployConfig, context);
  const exerciseMeta = buildExerciseMeta(
    template,
    segment,
    exerciseId,
    exerciseStartedAt,
    context.providerName,
    context.handoffSnapshot,
  );

  return { scenario, scenarioConfig: deployConfig, exerciseMeta };
}

export function buildHandoffDeployment(
  templateId: string,
  currentSegmentId: string,
  targetDepartment: HospitalDepartmentId,
  exerciseId: string,
  exerciseStartedAt: number,
  handoffSnapshot: PatientHandoffSnapshot,
  targetProviderName: string,
  config: ScenarioConfiguration = DEFAULT_SCENARIO_CONFIG,
) {
  const template = getExerciseTemplate(templateId);
  if (!template) throw new Error(`Exercise template ${templateId} not found`);

  const nextSegment = getNextSegmentForDepartment(template, currentSegmentId, targetDepartment);
  if (!nextSegment) {
    throw new Error(`${getDepartmentLabel(targetDepartment)} is not a valid handoff target for this segment`);
  }

  return buildSegmentDeployment(
    templateId,
    nextSegment.id,
    exerciseId,
    exerciseStartedAt,
    {
      providerName: targetProviderName,
      hospitalDepartment: targetDepartment,
      handoffSnapshot,
    },
    config,
  );
}

export function buildExerciseStartPayload(
  templateId: string,
  entryDeviceId: string,
  entryProviderName: string,
  entryDepartment: HospitalDepartmentId,
  config: ScenarioConfiguration = DEFAULT_SCENARIO_CONFIG,
): StartExercisePayload {
  const template = getExerciseTemplate(templateId);
  if (!template) throw new Error(`Exercise template ${templateId} not found`);

  const entrySegment = getEntrySegment(template);
  const exerciseId = `EX-${Date.now().toString(36).toUpperCase()}`;
  const startedAt = Date.now();

  const firstDeployment = buildSegmentDeployment(
    templateId,
    entrySegment.id,
    exerciseId,
    startedAt,
    {
      providerName: entryProviderName,
      hospitalDepartment: entryDepartment,
    },
    config,
  );

  return {
    exerciseId,
    templateId,
    title: template.title,
    startedAt,
    segments: template.segments.map((s) => ({
      id: s.id,
      department: s.department,
      handoffTargets: s.handoffTargets,
      isTerminal: Boolean(s.isTerminal),
      label: s.label,
    })),
    entrySegmentId: entrySegment.id,
    entryDeviceId,
    firstDeployment,
  };
}

export function getDepartmentsInExercise(template: ExerciseTemplate): HospitalDepartmentId[] {
  return [...new Set(template.segments.map((s) => s.department))];
}

export function listHandoffTargetLabels(
  templateId: string,
  segmentId: string,
): { id: HospitalDepartmentId; label: string }[] {
  const template = getExerciseTemplate(templateId);
  const segment = template ? getSegmentById(template, segmentId) : undefined;
  if (!segment) return [];
  return segment.handoffTargets.map((id) => ({ id, label: getDepartmentLabel(id) }));
}
