import type { FeedEntry, Scenario, ScenarioPatient } from '@/types';
import type { HospitalDepartmentId } from '@/types/providerProfile';
import type { ScenarioConfiguration } from '@/types/witConfig';
import { SUPPLY_OPTIONS } from '@/types/witConfig';
import { DYNAMIC_TRIAGE_OPTIONS } from '@/engines/casualtyTriageEngine';
import { buildScenarioContextNarrative } from '@/engines/scenarioResolver';

type BriefingFeedDraft = Pick<
  FeedEntry,
  'type' | 'content' | 'heading' | 'bullets' | 'audience' | 'patient_id'
>;

function casualtyCountLabel(total: number): string {
  return total === 1 ? '1 casualty' : `${total} casualties`;
}

function formatCommsStatus(status: string): string {
  switch (status) {
    case 'degraded':
      return 'Degraded (expect delayed CASEVAC coordination)';
    case 'down':
      return 'Down (no reliable comms)';
    case 'normal':
      return 'Normal';
    default:
      return status.replace(/_/g, ' ');
  }
}

function formatResourceStatus(status: string): string {
  switch (status) {
    case 'constrained':
      return 'Constrained';
    case 'critical':
      return 'Critical';
    case 'adequate':
      return 'Adequate';
    default:
      return status.replace(/_/g, ' ');
  }
}

export function buildProviderSessionBriefing(
  scenario: Scenario,
  config: ScenarioConfiguration,
  supplySummary: string,
  options?: {
    providerName?: string;
    hospitalDepartment?: HospitalDepartmentId;
  },
  primaryPatient?: ScenarioPatient,
): BriefingFeedDraft[] {
  const { casualties, constraints } = config;
  const contextLine = buildScenarioContextNarrative(
    config.scenarioSelection,
    options?.hospitalDepartment ?? 'field_response_team',
    options?.providerName,
  );

  const triageBullets = [
    `Total: ${casualtyCountLabel(casualties.total)}`,
    `Immediate: ${casualties.triage.immediate}`,
    `Delayed: ${casualties.triage.delayed}`,
    `Minimal: ${casualties.triage.minimal}`,
  ];

  if (casualties.dynamicTriage !== 'static') {
    const mode =
      DYNAMIC_TRIAGE_OPTIONS.find((o) => o.id === casualties.dynamicTriage)?.label ??
      casualties.dynamicTriage;
    triageBullets.push(`Dynamic triage: ${mode}`);
  }

  const environmentBullets = [
    `Communications: ${formatCommsStatus(constraints.comms_status)}`,
    `Resources: ${formatResourceStatus(constraints.resource_status)}`,
  ];

  if (constraints.environmental_notes.trim()) {
    environmentBullets.push(constraints.environmental_notes.trim());
  }

  const supplyLabel =
    SUPPLY_OPTIONS.find((o) => o.id === config.supply)?.label ?? config.supply;

  const entries: BriefingFeedDraft[] = [
    {
      type: 'system',
      heading: 'Situation',
      content: scenario.operational_context.narrative.trim(),
      bullets: contextLine.trim() ? [contextLine.trim()] : undefined,
    },
    {
      type: 'system',
      heading: 'Casualties and triage',
      content: '',
      bullets: triageBullets,
    },
    {
      type: 'system',
      heading: 'Environment and supply',
      content: '',
      bullets: [
        ...environmentBullets,
        `Medical supply (${supplyLabel}): ${supplySummary.replace(/\.$/, '')}`,
        ...(config.aiEnhanced ? ['AI-enhanced scenario generation active for this evolution.'] : []),
        ...(config.dispositionRequirements.trim()
          ? [`Disposition requirements: ${config.dispositionRequirements.trim()}`]
          : []),
      ],
    },
    {
      type: 'system',
      heading: 'Bedside orientation',
      content:
        'You are at the bedside. No monitors are visible. Assess the patient directly and document findings in the feed.',
    },
  ];

  if (primaryPatient?.initial_presentation) {
    entries.push({
      type: 'patient',
      heading: 'Initial presentation',
      content: primaryPatient.initial_presentation.trim(),
      patient_id: primaryPatient.patient_id,
    });
  }

  return entries;
}

/** Structured blocks for mission brief page (mirrors session feed). */
export function buildProviderBriefSections(
  scenario: Scenario,
  config: ScenarioConfiguration,
  supplySummary: string,
): { heading: string; content?: string; bullets?: string[] }[] {
  return buildProviderSessionBriefing(scenario, config, supplySummary).map(
    ({ heading, content, bullets }) => ({
      heading: heading ?? 'Briefing',
      content: content?.trim() || undefined,
      bullets,
    }),
  );
}
