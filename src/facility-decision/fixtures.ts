import type { FacilityDecisionSubmission, FacilityDecisionValue } from './types';

const VALUES: Record<string, Record<string, FacilityDecisionValue>> = {
  receive_handoff: {
    sender_role: 'CASEVAC team lead',
    casualty_identity_confirmed: true,
    mechanism_summary: 'Blast and fragmentation injury with field stabilization before clinic arrival.',
    field_interventions: ['right-thigh tourniquet remains in place'],
    uncertainties: ['occult chest injury', 'possible traumatic brain injury'],
  },
  primary_assessment: {
    assessment_domains: ['airway', 'breathing', 'circulation', 'neurologic', 'exposure'],
    new_observations: ['confusion', 'chest symptoms', 'borderline perfusion findings'],
    uncertainty_statement: 'The cause and severity of the chest and neurologic findings remain uncertain.',
  },
  monitor_vitals: {
    monitoring_channels: ['heart_rate', 'blood_pressure', 'respiratory_rate', 'oxygen_saturation', 'mental_status'],
    reassessment_trigger: 'Repeat after new information, clinical change, or diagnostic result availability.',
  },
  differential: {
    hypotheses: ['occult thoracic injury', 'blast-associated neurologic injury', 'residual hemorrhage risk'],
    time_critical_concern_present: true,
    evidence_and_uncertainty: 'Chest symptoms, hypoxemia, confusion, and borderline pressure support an urgent differential while important uncertainty remains.',
  },
  order_imaging: {
    order_code: 'CHEST_IMAGING',
    indication: 'Blast exposure with chest pain, dyspnea, and abnormal oxygen saturation.',
    urgency: 'urgent',
  },
  order_labs: {
    order_codes: ['LACTATE'],
    indication: 'Assess the source-defined perfusion-related laboratory concern in the receiving evaluation.',
    urgency: 'urgent',
  },
  pain_management: {
    pain_assessment: 'Pain is present and requires a source-governed management objective.',
    treatment_intent: 'Address pain while preserving monitoring and reassessment; no drug, dose, route, or procedure is generated.',
    monitoring_plan: 'Continue physiologic and mental-status monitoring for change.',
    reassessment_plan: 'Reassess pain and observed response after the selected source-governed intervention.',
  },
  confirm_surge_roles: {
    role_assignments: ['provider retains current casualty', 'clinic nurse prepares next receiving space'],
    continuity_plan: 'Maintain monitoring and pending diagnostic follow-up for the current casualty during surge preparation.',
  },
  wait_for_diagnostics: {
    reassessment_during_wait: 'Continue monitoring and reassess for new respiratory, perfusion, or neurologic change while results are pending.',
  },
  wait_60: {
    observation_plan: 'Continue monitoring respiratory, perfusion, neurologic, and device status during the interval.',
  },
  review_diagnostics: {
    result_interpretation: 'The returned source-template results increase concern for a significant chest process and impaired perfusion.',
    reassessment_summary: 'The casualty is reassessed after result availability with attention to respiratory, perfusion, and neurologic status.',
    remaining_uncertainty: 'The source template does not provide modality-specific detail, a numeric lactate, or a validated dynamic physiology trajectory.',
  },
  escalation: {
    destination_capability: 'HIGHER_LEVEL_TRAUMA_CAPABILITY',
    urgency: 'urgent',
    reason: 'Source-defined chest and perfusion concerns require higher-level capability and continued monitoring.',
    receiving_acceptance: true,
    transport_requirement: 'Monitored transport to higher-level trauma capability.',
    contingency: 'Continue monitoring, reassessment, and escalation if transfer is delayed or the casualty changes.',
  },
  documentation: {
    findings: 'Blast mechanism, confusion, chest symptoms, monitored observations, and returned source-template results documented.',
    actions_and_response: 'Assessment, monitoring, diagnostic requests, result review, and escalation actions documented with observed status.',
    pending_work: 'Transfer execution, continued reassessment, and any unresolved diagnostic or treatment decisions remain pending.',
    plan: 'Maintain monitoring, complete closed-loop transfer, and escalate for deterioration or transport delay.',
  },
  complete_handoff: {
    sender_identity: 'Receiving clinic provider',
    receiver_identity: 'Higher-level trauma receiving provider',
    situation: 'Post-CUF/TFC blast casualty with chest, neurologic, and perfusion concerns requiring transfer.',
    background: 'Field stabilization included a right-thigh tourniquet; clinic assessment and diagnostic evaluation were completed.',
    assessment_and_uncertainty: 'Source-template results increase concern for thoracic injury and impaired perfusion; modality detail and numeric laboratory values remain limited.',
    actions_and_response: 'Assessment, monitoring, diagnostic requests, result review, documentation, and escalation were completed; continued response requires reassessment.',
    pending_tasks: ['continue monitoring', 'complete transfer', 'resolve remaining treatment decisions under governing authority'],
    recommendation: 'Accept urgent transfer to higher-level trauma capability and continue reassessment during movement.',
    contingency: 'If transfer is delayed or the casualty changes, maintain monitoring and escalate through the receiving chain.',
    receiver_acknowledged: true,
    questions_offered: true,
    sender_confirmed: true,
  },
  discharge_without_workup: {
    rationale: 'End the evaluation despite incomplete workup and unresolved source-defined risk.',
    deliberate_confirmation: true,
  },
  remove_tourniquet: {
    rationale: 'Change the tourniquet plan despite the absence of the required eligibility model and governing source details.',
    deliberate_confirmation: true,
  },
};

export function facilityDecisionValues(decisionId: string): Record<string, FacilityDecisionValue> {
  const values = VALUES[decisionId];
  if (!values) throw new Error(`No reviewed decision fixture: ${decisionId}`);
  return structuredClone(values);
}

export function facilityDecisionSubmission(
  decisionId: string,
  revision: number,
  ordinal: number,
): FacilityDecisionSubmission {
  return {
    submission_id: `fixture-${ordinal.toString().padStart(3, '0')}-${decisionId}`,
    decision_id: decisionId,
    expected_revision: revision,
    values: facilityDecisionValues(decisionId),
  };
}

export const FACILITY_DECISION_CANONICAL_SEQUENCE = [
  'receive_handoff',
  'primary_assessment',
  'monitor_vitals',
  'differential',
  'order_imaging',
  'order_labs',
  'pain_management',
  'documentation',
  'wait_for_diagnostics',
  'review_diagnostics',
  'confirm_surge_roles',
  'escalation',
  'complete_handoff',
] as const;

export const FACILITY_DECISION_ALTERNATE_SEQUENCE = [
  'receive_handoff',
  'primary_assessment',
  'differential',
  'order_labs',
  'monitor_vitals',
  'order_imaging',
  'documentation',
  'pain_management',
  'wait_for_diagnostics',
  'review_diagnostics',
  'confirm_surge_roles',
  'escalation',
  'complete_handoff',
] as const;
