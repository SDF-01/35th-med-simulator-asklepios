import type { Scenario } from '@/types';

const askA001: Scenario = {
  scenario_id: 'ASK-A-001',
  title: 'Flightline Fragmentation Casualty After Missile Warning',
  version: '1.0.0',
  fictionalization_notice:
    'Fictional training scenario. Not real medical advice. Follow local medical authority and current approved doctrine.',
  operational_context: {
    location_type: 'flightline',
    threat_type: 'missile_attack',
    weather: 'Clear, cold, wind from northwest',
    visibility: 'Good with intermittent smoke from distant impacts',
    comms_status: 'degraded',
    resource_status: 'constrained',
    narrative:
      'Missile warning sounded approximately four minutes ago. You are responding to a single casualty on the flightline maintenance area. Secondary attack risk remains possible. Comms are degraded; expect delayed CASEVAC coordination. One tourniquet and one IFAK are immediately available.',
  },
  training_objectives: [
    'Assess scene safety and threat',
    'Control life-threatening hemorrhage',
    'Assess airway and breathing',
    'Request evacuation',
  ],
  target_section: 'A_field_reaction_triage_incident_response',
  target_role: 'combat_lifesaver',
  skill_level: 'intermediate',
  difficulty: 'intermediate',
  threat_type: 'missile_attack',
  casualty_count: 1,
  patients: [
    {
      patient_id: 'P1',
      age_band: '25-34',
      sex: 'M',
      role_context: 'Maintenance Airman',
      mechanism_of_injury: 'Fragmentation wound from nearby blast',
      initial_presentation:
        'Conscious male lying supine near equipment. Yelling in pain. Obvious bleeding from right thigh. Rapid, shallow breathing. Clutching chest but primary visible injury is lower extremity.',
      injury_profile_refs: ['extremity_hemorrhage', 'possible_chest_contusion'],
      initial_vitals: {
        hr: 128,
        bp_systolic: 92,
        bp_diastolic: 58,
        rr: 28,
        spo2: 91,
        temp_c: 36.2,
        gcs: 14,
      },
      hidden_findings: ['Possible tension pneumothorax developing if chest injury worsens'],
      deterioration_timeline: [
        'Without hemorrhage control: BP drops within 2 minutes',
        'Without airway support if needed: SpO2 declines',
      ],
      visible_body_zones: [
        { zone: 'right_thigh', label: 'Fragmentation / active hemorrhage', severity: 'visible' },
        { zone: 'chest', label: 'Guarding chest. Possible contusion.', severity: 'suspected' },
      ],
    },
  ],
  expected_actions: {
    critical: [
      {
        id: 'scene_safety',
        label: 'Assess scene safety / threat',
        priority: 'critical',
        synonyms: [
          'scene safe',
          'threat assessment',
          'check for threats',
          'scene security',
          'cover',
          'concealment',
          'additional casualties',
        ],
        points: 10,
      },
      {
        id: 'hemorrhage_control',
        label: 'Control massive hemorrhage',
        priority: 'critical',
        synonyms: [
          'tourniquet',
          'tq',
          'apply tourniquet',
          'stop bleeding',
          'hemorrhage control',
          'pressure dressing',
          'pack wound',
          'direct pressure',
        ],
        points: 20,
        marchStep: 'massive_hemorrhage',
      },
      {
        id: 'airway_assessment',
        label: 'Assess and manage airway',
        priority: 'critical',
        synonyms: [
          'airway',
          'jaw thrust',
          'recovery position',
          'nasopharyngeal',
          'npa',
          'open airway',
        ],
        points: 15,
        marchStep: 'airway',
      },
      {
        id: 'breathing_assessment',
        label: 'Assess breathing / respiration',
        priority: 'critical',
        synonyms: [
          'breathing',
          'respiration',
          'chest seal',
          'needle decompression',
          'check breath sounds',
          'ventilation',
        ],
        points: 15,
        marchStep: 'respiration',
      },
    ],
    important: [
      {
        id: 'circulation_check',
        label: 'Assess circulation / shock',
        priority: 'important',
        synonyms: ['pulse', 'circulation', 'shock', 'perfusion', 'iv access'],
        points: 8,
        marchStep: 'circulation',
      },
      {
        id: 'hypothermia_prevention',
        label: 'Prevent hypothermia',
        priority: 'important',
        synonyms: ['hypothermia', 'blanket', 'hpmk', 'keep warm', 'prevent heat loss'],
        points: 5,
        marchStep: 'hypothermia_head',
      },
      {
        id: 'evacuation_request',
        label: 'Request evacuation / CASEVAC',
        priority: 'important',
        synonyms: [
          'evac',
          'evacuation',
          'casevac',
          'medevac',
          'request transport',
          '9-line',
          'call for help',
        ],
        points: 10,
      },
    ],
    optional: [
      {
        id: 'pain_management',
        label: 'Address pain when appropriate',
        priority: 'optional',
        synonyms: ['pain', 'analgesia', 'comfort'],
        points: 3,
        marchStep: 'pain',
      },
      {
        id: 'documentation',
        label: 'Document interventions',
        priority: 'optional',
        synonyms: ['document', 'record', 'note', 'tccc card'],
        points: 3,
      },
    ],
    unsafe: [
      {
        id: 'ignore_hemorrhage',
        label: 'Delay or ignore hemorrhage control',
        priority: 'unsafe',
        synonyms: ['wait and see', 'skip tourniquet', 'bleeding will stop'],
        points: -25,
      },
      {
        id: 'remove_tourniquet_early',
        label: 'Remove tourniquet without medical direction',
        priority: 'unsafe',
        synonyms: ['remove tourniquet', 'take off tourniquet'],
        points: -20,
      },
    ],
  },
  end_conditions: {
    success: [
      'Hemorrhage controlled',
      'Airway and breathing addressed',
      'Evacuation requested',
      'Patient stable for handoff',
    ],
    failure: ['Preventable death from hemorrhage', 'Critical unsafe action'],
    timeout_minutes: 15,
  },
  aar_teaching_points: [
    'MARCH prioritizes massive hemorrhage before detailed airway work when bleeding is obvious.',
    'Scene safety and threat assessment remain continuous during point-of-injury care.',
    'Degraded comms require early evacuation request even while stabilizing.',
  ],
};

const askD001: Scenario = {
  scenario_id: 'ASK-D-001',
  title: 'Clinic Receives Blast Patient With Confusion And Chest Pain',
  version: '1.0.0',
  fictionalization_notice:
    'Fictional training scenario. Not real medical advice. Follow local medical authority and current approved doctrine.',
  operational_context: {
    location_type: 'clinic',
    threat_type: 'missile_attack',
    weather: 'Overcast, 12C',
    visibility: 'Normal indoors',
    comms_status: 'normal',
    resource_status: 'constrained',
    narrative:
      'A blast casualty arrived from the flightline via CASEVAC ten minutes ago. You are the provider on duty in the base clinic. The patient is confused with chest pain and tachycardia. Radiology and lab are available with standard delays. One additional casualty is inbound.',
  },
  training_objectives: [
    'Perform focused assessment and differential',
    'Order appropriate diagnostics',
    'Recognize deterioration',
    'Escalate disposition',
  ],
  target_section: 'D_clinical',
  target_role: 'provider',
  skill_level: 'advanced',
  difficulty: 'advanced',
  threat_type: 'missile_attack',
  casualty_count: 1,
  patients: [
    {
      patient_id: 'P1',
      age_band: '25-34',
      sex: 'M',
      role_context: 'Maintenance Airman',
      mechanism_of_injury: 'Primary blast and fragmentation from flightline incident',
      initial_presentation:
        'Male patient on gurney, alert but confused. Complains of chest pain and shortness of breath. Tourniquet in place on right thigh from field care. Skin pale, diaphoretic.',
      injury_profile_refs: ['blast_injury', 'possible_tbi', 'extremity_hemorrhage_controlled'],
      initial_vitals: {
        hr: 118,
        bp_systolic: 98,
        bp_diastolic: 62,
        rr: 24,
        spo2: 93,
        temp_c: 36.4,
        gcs: 13,
      },
      hidden_findings: ['Developing pneumothorax', 'Elevated lactate on labs if ordered'],
      deterioration_timeline: [
        'Without reassessment and orders: SpO2 may decline',
        'Delayed imaging: missed tension pneumothorax risk',
      ],
      visible_body_zones: [
        { zone: 'right_thigh', label: 'Tourniquet applied in field', severity: 'controlled' },
        { zone: 'chest', label: 'Chest pain / blast injury', severity: 'suspected' },
        { zone: 'head', label: 'Confusion. Assess for TBI.', severity: 'suspected' },
      ],
    },
  ],
  expected_actions: {
    critical: [
      {
        id: 'primary_assessment',
        label: 'Perform primary assessment',
        priority: 'critical',
        synonyms: [
          'assessment',
          'evaluate patient',
          'primary survey',
          'examine',
          'reassess',
          'clinical assessment',
        ],
        points: 15,
      },
      {
        id: 'order_imaging',
        label: 'Order chest imaging',
        priority: 'critical',
        synonyms: ['chest x-ray', 'x-ray', 'xray', 'imaging', 'radiograph', 'order imaging', 'cxr'],
        points: 15,
      },
      {
        id: 'order_labs',
        label: 'Order relevant labs',
        priority: 'critical',
        synonyms: ['labs', 'blood work', 'cbc', 'bmp', 'lactate', 'order labs', 'draw labs'],
        points: 12,
      },
    ],
    important: [
      {
        id: 'differential',
        label: 'Document differential diagnosis',
        priority: 'important',
        synonyms: [
          'differential',
          'ddx',
          'consider pneumothorax',
          'consider tbi',
          'working diagnosis',
        ],
        points: 10,
      },
      {
        id: 'monitor_vitals',
        label: 'Establish continuous monitoring',
        priority: 'important',
        synonyms: ['monitor', 'vitals', 'pulse ox', 'telemetry', 'continuous monitoring'],
        points: 8,
      },
      {
        id: 'escalation',
        label: 'Escalate disposition / consult',
        priority: 'important',
        synonyms: [
          'escalate',
          'admit',
          'surgery consult',
          'transfer',
          'disposition',
          'or consult',
          'higher level of care',
        ],
        points: 12,
      },
    ],
    optional: [
      {
        id: 'pain_management',
        label: 'Address pain management',
        priority: 'optional',
        synonyms: ['pain', 'analgesia', 'morphine', 'fentanyl'],
        points: 3,
      },
      {
        id: 'documentation',
        label: 'Document findings and plan',
        priority: 'optional',
        synonyms: ['document', 'note', 'record', 'chart'],
        points: 5,
      },
    ],
    unsafe: [
      {
        id: 'discharge_without_workup',
        label: 'Discharge without adequate workup',
        priority: 'unsafe',
        synonyms: ['discharge home', 'send home', 'no workup needed'],
        points: -25,
      },
      {
        id: 'remove_tourniquet',
        label: 'Remove tourniquet without indication',
        priority: 'unsafe',
        synonyms: ['remove tourniquet', 'take off tourniquet'],
        points: -20,
      },
    ],
  },
  end_conditions: {
    success: ['Assessment completed', 'Diagnostics ordered', 'Disposition escalated appropriately'],
    failure: ['Preventable deterioration', 'Critical unsafe action'],
    timeout_minutes: 20,
  },
  aar_teaching_points: [
    'Blast casualties require reassessment for occult chest and TBI injuries after field stabilization.',
    'Providers must order targeted imaging and labs before disposition decisions.',
    'Early escalation prevents deterioration when resources are constrained during surge.',
  ],
};

export const scenariosById: Record<string, Scenario> = {
  'ASK-A-001': askA001,
  'ASK-D-001': askD001,
};

export const scenarioList: Scenario[] = [askA001, askD001];

if (import.meta.env?.DEV) {
  import('@/engines/scenarioInjuryValidation').then(({ validateAllScenarios }) => {
    const issues = validateAllScenarios(scenarioList);
    if (issues.length > 0) {
      console.warn(
        '[Asklepios] Scenario injury map coverage issues:',
        issues.map((i) => `${i.scenarioId}/${i.patientId}: ${i.message}`),
      );
    }
  });
}
