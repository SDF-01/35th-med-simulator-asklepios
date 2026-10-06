import type { PatientState, Scenario, ScenarioPatient } from '@/types';
import type { CasualtyConfiguration, TriageCategory } from '@/types/witConfig';
import { resolveInitialVisibleInjuries } from '@/engines/injuryBodyMapper';
import { initialMarchState } from '@/engines/simulationEngine';

const TRIAGE_ORDER: TriageCategory[] = ['immediate', 'delayed', 'minimal'];

const TRIAGE_LABELS: Record<TriageCategory, string> = {
  immediate: 'Immediate',
  delayed: 'Delayed',
  minimal: 'Minimal',
};

function buildPatientFromTemplate(
  template: ScenarioPatient,
  index: number,
  triage: TriageCategory,
  scenario: Scenario,
): { scenarioPatient: ScenarioPatient; patientState: PatientState } {
  const patientId = `P${index + 1}`;
  const isClinical = scenario.target_section === 'D_clinical';

  const scenarioPatient: ScenarioPatient = {
    ...template,
    patient_id: patientId,
    visible_body_zones: template.visible_body_zones?.map((z) => ({ ...z })),
  };

  const body_zones = resolveInitialVisibleInjuries(scenarioPatient);

  const patientState: PatientState = {
    patient_id: patientId,
    display_label: `Casualty ${index + 1} (${TRIAGE_LABELS[triage]})`,
    triage_category: triage,
    vitals: { ...template.initial_vitals },
    symptoms: isClinical
      ? ['Reports pain', 'Appears distressed']
      : ['Visible trauma', 'Anxiety'],
    known_injuries: isClinical
      ? ['Extremity injury. Field care may be in place.']
      : ['Visible extremity trauma'],
    revealed_findings: [],
    revealed_assessments: [],
    interventions: isClinical ? ['Prior field interventions may be present'] : [],
    march: initialMarchState(),
    mental_status:
      template.initial_vitals.gcs >= 13 ? 'Alert, distressed' : 'Altered mental status',
    bleeding_status: isClinical
      ? 'Status unknown. Assess bleeding.'
      : 'Possible active bleeding. Assess.',
    body_zones,
  };

  return { scenarioPatient, patientState };
}

export function expandScenarioPatients(
  scenario: Scenario,
  casualties: CasualtyConfiguration,
): { scenario: Scenario; patients: PatientState[] } {
  const template = scenario.patients[0];
  if (!template || casualties.total <= 1) {
    const body_zones = resolveInitialVisibleInjuries(template);
    const isClinical = scenario.target_section === 'D_clinical';
    const single: PatientState = {
      patient_id: template.patient_id,
      display_label: 'Casualty 1',
      triage_category: 'immediate',
      vitals: { ...template.initial_vitals },
      symptoms: isClinical ? ['Reports pain', 'Appears distressed'] : ['Visible trauma'],
      known_injuries: isClinical
        ? ['Extremity injury. Field care may be in place.']
        : ['Visible extremity trauma'],
      revealed_findings: [],
      revealed_assessments: [],
      interventions: isClinical ? ['Prior field interventions may be present'] : [],
      march: initialMarchState(),
      mental_status:
        template.initial_vitals.gcs >= 13 ? 'Alert, distressed' : 'Altered mental status',
      bleeding_status: isClinical
        ? 'Status unknown. Assess bleeding.'
        : 'Possible active bleeding. Assess.',
      body_zones,
    };
    return { scenario, patients: [single] };
  }

  const scenarioPatients: ScenarioPatient[] = [];
  const patientStates: PatientState[] = [];
  let index = 0;

  for (const category of TRIAGE_ORDER) {
    for (let i = 0; i < casualties.triage[category]; i += 1) {
      const built = buildPatientFromTemplate(template, index, category, scenario);
      scenarioPatients.push(built.scenarioPatient);
      patientStates.push(built.patientState);
      index += 1;
    }
  }

  return {
    scenario: { ...scenario, patients: scenarioPatients, casualty_count: casualties.total },
    patients: patientStates,
  };
}
