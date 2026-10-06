import type { BodyInjuryHighlight } from '../types/bodyInjury';
import type { CommsStatus, MedicalSection, ResourceStatus, SkillLevel, UserRole } from '../types';
import type { ScenarioEvidenceTopic } from './types';

export interface TopicProfile {
  topic_id: ScenarioEvidenceTopic;
  title_stem: string;
  target_section: MedicalSection;
  target_role: UserRole;
  difficulty: SkillLevel;
  threat_type: string;
  locations: readonly string[];
  mechanisms: readonly string[];
  presentations: readonly string[];
  injury_profile_refs: readonly string[];
  visible_body_zones: readonly BodyInjuryHighlight[];
  age_bands: readonly string[];
  sex_values: readonly string[];
  role_contexts: readonly string[];
  vital_ranges: {
    hr: readonly [number, number];
    bp_systolic: readonly [number, number];
    bp_diastolic: readonly [number, number];
    rr: readonly [number, number];
    spo2: readonly [number, number];
    temp_c_tenths: readonly [number, number];
    gcs: readonly [number, number];
  };
  hidden_findings: readonly string[];
  deterioration: readonly string[];
  objectives: readonly string[];
  cues: readonly string[];
  complications: readonly string[];
  resource_events: readonly string[];
  comms: readonly CommsStatus[];
  resources: readonly ResourceStatus[];
}

const FIELD_SECTION: MedicalSection = 'A_field_reaction_triage_incident_response';

export const TOPIC_PROFILES: Record<ScenarioEvidenceTopic, TopicProfile> = {
  massive_hemorrhage: {
    topic_id: 'massive_hemorrhage', title_stem: 'Hemorrhage recognition under constrained evacuation',
    target_section: FIELD_SECTION, target_role: 'medic_or_technician', difficulty: 'advanced', threat_type: 'blast_event',
    locations: ['damaged flightline shelter', 'remote convoy halt', 'expeditionary collection point'],
    mechanisms: ['fragmentation injury with severe extremity bleeding', 'high-energy limb injury during blast response'],
    presentations: ['Conscious casualty with visible lower-extremity bleeding, pallor, and increasing fatigue.'],
    injury_profile_refs: ['extremity_hemorrhage'],
    visible_body_zones: [{ zone: 'right_thigh', label: 'Visible severe extremity bleeding', severity: 'visible' }],
    age_bands: ['18-24', '25-34', '35-44'], sex_values: ['F', 'M'], role_contexts: ['Airman', 'Security Forces member', 'Civilian contractor'],
    vital_ranges: { hr: [112, 148], bp_systolic: [78, 104], bp_diastolic: [44, 66], rr: [22, 34], spo2: [91, 98], temp_c_tenths: [356, 367], gcs: [12, 15] },
    hidden_findings: ['Perfusion may worsen while evacuation is delayed.'], deterioration: ['Observable perfusion cues worsen if the scenario clock advances without reassessment.'],
    objectives: ['Recognize time-sensitive deterioration cues', 'Document serial observations', 'Communicate resource and transport constraints'],
    cues: ['visible bleeding', 'weakening radial pulse', 'increasing confusion'], complications: ['worsening shock concern', 'delayed evacuation'],
    resource_events: ['blood product unavailable', 'transport delayed', 'limited warming equipment'], comms: ['degraded', 'intermittent'], resources: ['constrained', 'overwhelmed'],
  },
  airway: {
    topic_id: 'airway', title_stem: 'Airway deterioration during constrained transport',
    target_section: FIELD_SECTION, target_role: 'medic_or_technician', difficulty: 'advanced', threat_type: 'transport_disruption',
    locations: ['offshore rescue aircraft cabin', 'armored evacuation vehicle', 'expeditionary ambulance bay'],
    mechanisms: ['blunt facial and neck trauma during emergency extraction', 'airway obstruction concern after blast exposure'],
    presentations: ['Casualty is anxious, speaking in short phrases, and developing noisy respirations during transport.'],
    injury_profile_refs: ['neck_trauma', 'possible_chest_contusion'],
    visible_body_zones: [{ zone: 'neck', label: 'Neck swelling and airway concern', severity: 'suspected' }, { zone: 'chest', label: 'Respiratory distress', severity: 'suspected' }],
    age_bands: ['18-24', '25-34', '35-44'], sex_values: ['F', 'M'], role_contexts: ['Aircrew member', 'Maintainer', 'Rescue team member'],
    vital_ranges: { hr: [104, 138], bp_systolic: [94, 132], bp_diastolic: [58, 82], rr: [24, 38], spo2: [82, 94], temp_c_tenths: [360, 372], gcs: [11, 15] },
    hidden_findings: ['Airway patency may change as swelling progresses.'], deterioration: ['Voice, respiratory effort, and oxygenation cues may worsen over several timed events.'],
    objectives: ['Recognize changing airway cues', 'Reassess after environmental changes', 'Communicate a concise transport update'],
    cues: ['voice change', 'increasing work of breathing', 'declining oxygen saturation'], complications: ['progressive obstruction concern', 'limited positioning space'],
    resource_events: ['lighting failure', 'transport turbulence', 'primary airway device unavailable'], comms: ['degraded', 'intermittent'], resources: ['constrained'],
  },
  respiration_chest: {
    topic_id: 'respiration_chest', title_stem: 'Chest-trauma deterioration before definitive care',
    target_section: FIELD_SECTION, target_role: 'medic_or_technician', difficulty: 'advanced', threat_type: 'blast_event',
    locations: ['forward casualty collection point', 'damaged hangar', 'ground evacuation route'],
    mechanisms: ['blunt and penetrating chest trauma after blast', 'high-energy impact with chest injury'],
    presentations: ['Casualty has chest pain, asymmetric respiratory effort, and worsening distress.'],
    injury_profile_refs: ['blast_injury', 'possible_chest_contusion'],
    visible_body_zones: [{ zone: 'chest', label: 'Chest trauma and respiratory concern', severity: 'suspected' }],
    age_bands: ['18-24', '25-34', '35-44'], sex_values: ['F', 'M'], role_contexts: ['Airman', 'Responder'],
    vital_ranges: { hr: [108, 146], bp_systolic: [84, 118], bp_diastolic: [48, 74], rr: [26, 42], spo2: [78, 92], temp_c_tenths: [358, 370], gcs: [10, 15] },
    hidden_findings: ['Respiratory mechanics may worsen during delay.'], deterioration: ['Respiratory rate and oxygenation cues change with elapsed time.'],
    objectives: ['Identify changing respiratory cues', 'Track serial observations', 'Escalate communication when the casualty worsens'],
    cues: ['asymmetric chest movement', 'increasing respiratory distress', 'falling oxygen saturation'], complications: ['obstructive shock concern', 'transport delay'],
    resource_events: ['oxygen supply limited', 'monitor battery low', 'transport asset diverted'], comms: ['degraded', 'intermittent'], resources: ['constrained', 'overwhelmed'],
  },
  shock_resuscitation: {
    topic_id: 'shock_resuscitation', title_stem: 'Shock-pattern recognition during delayed movement',
    target_section: FIELD_SECTION, target_role: 'medic_or_technician', difficulty: 'advanced', threat_type: 'multi_system_trauma',
    locations: ['austere treatment point', 'remote training range', 'damaged clinic receiving area'],
    mechanisms: ['multiple trauma with suspected circulatory compromise'],
    presentations: ['Casualty is pale, tachycardic, and increasingly confused after multiple trauma.'],
    injury_profile_refs: ['blast_injury', 'extremity_hemorrhage_controlled'],
    visible_body_zones: [{ zone: 'right_thigh', label: 'Prior field hemorrhage control', severity: 'controlled' }, { zone: 'abdomen', label: 'Occult injury concern', severity: 'suspected' }],
    age_bands: ['18-24', '25-34', '35-44'], sex_values: ['F', 'M'], role_contexts: ['Airman', 'Contractor'],
    vital_ranges: { hr: [112, 152], bp_systolic: [72, 102], bp_diastolic: [40, 64], rr: [22, 36], spo2: [88, 97], temp_c_tenths: [352, 366], gcs: [9, 14] },
    hidden_findings: ['The mechanism may involve occult blood loss.'], deterioration: ['Perfusion and mental-status cues worsen during untreated delay.'],
    objectives: ['Recognize a changing shock pattern', 'Capture serial vitals', 'Communicate uncertainty and resource constraints'],
    cues: ['narrowing pulse pressure', 'cool skin', 'worsening mental status'], complications: ['occult injury concern', 'temperature loss'],
    resource_events: ['vascular access supplies limited', 'transport delayed', 'warming equipment shared'], comms: ['degraded', 'intermittent'], resources: ['constrained', 'overwhelmed'],
  },
  tbi_neurologic: {
    topic_id: 'tbi_neurologic', title_stem: 'Neurologic reassessment after blast exposure',
    target_section: FIELD_SECTION, target_role: 'medic_or_technician', difficulty: 'advanced', threat_type: 'blast_event',
    locations: ['flightline shelter', 'field triage lane', 'evacuation holding area'], mechanisms: ['blast exposure with head impact'],
    presentations: ['Casualty is confused, repeats questions, and has a worsening headache after a blast.'],
    injury_profile_refs: ['possible_tbi'], visible_body_zones: [{ zone: 'head', label: 'Head injury concern', severity: 'suspected' }],
    age_bands: ['18-24', '25-34', '35-44'], sex_values: ['F', 'M'], role_contexts: ['Airman', 'Responder'],
    vital_ranges: { hr: [72, 118], bp_systolic: [104, 158], bp_diastolic: [62, 94], rr: [14, 28], spo2: [90, 99], temp_c_tenths: [360, 374], gcs: [10, 14] },
    hidden_findings: ['Neurologic findings may evolve despite an initially stable appearance.'], deterioration: ['Mental-status and pupil-observation cues may change over time.'],
    objectives: ['Perform repeat neurologic observations', 'Recognize trend changes', 'Communicate destination and monitoring concerns'],
    cues: ['repeated questioning', 'worsening headache', 'declining responsiveness'], complications: ['evolving neurologic deficit concern', 'delayed recognition'],
    resource_events: ['monitoring interrupted', 'multiple casualties arrive', 'transport destination changes'], comms: ['normal', 'degraded'], resources: ['constrained'],
  },
  burns_hypothermia: {
    topic_id: 'burns_hypothermia', title_stem: 'Thermal injury with temperature-loss risk',
    target_section: FIELD_SECTION, target_role: 'medic_or_technician', difficulty: 'advanced', threat_type: 'fuel_fire',
    locations: ['fuel storage perimeter', 'cold-weather flightline', 'decontamination corridor'], mechanisms: ['thermal and inhalation exposure during fuel fire'],
    presentations: ['Casualty has visible thermal injury, soot exposure concern, and progressive heat loss during evacuation.'],
    injury_profile_refs: ['burn_injury', 'inhalation_injury'], visible_body_zones: [{ zone: 'chest', label: 'Thermal and inhalation exposure concern', severity: 'suspected' }, { zone: 'right_forearm', label: 'Visible thermal injury', severity: 'visible' }],
    age_bands: ['18-24', '25-34', '35-44'], sex_values: ['F', 'M'], role_contexts: ['Fuel systems technician', 'Responder'],
    vital_ranges: { hr: [106, 144], bp_systolic: [88, 124], bp_diastolic: [50, 78], rr: [22, 38], spo2: [82, 96], temp_c_tenths: [348, 365], gcs: [11, 15] },
    hidden_findings: ['Airway and temperature-related concerns may evolve during transport.'], deterioration: ['Temperature and respiratory cues worsen when exposure continues.'],
    objectives: ['Recognize combined thermal and respiratory cues', 'Track temperature trend', 'Communicate burn and transport constraints'],
    cues: ['soot exposure concern', 'cooling trend', 'increasing respiratory effort'], complications: ['inhalation-injury concern', 'progressive heat loss'],
    resource_events: ['warming supplies limited', 'water supply interrupted', 'transport delayed'], comms: ['degraded', 'intermittent'], resources: ['constrained', 'overwhelmed'],
  },
  analgesia_sedation: {
    topic_id: 'analgesia_sedation', title_stem: 'Medication-safety observation during painful trauma care',
    target_section: 'D_clinical', target_role: 'provider', difficulty: 'advanced', threat_type: 'trauma_surge',
    locations: ['expeditionary clinic', 'urgent treatment bay', 'transport staging area'], mechanisms: ['painful orthopedic trauma during surge operations'],
    presentations: ['Casualty reports severe pain and becomes intermittently agitated while monitoring resources are constrained.'],
    injury_profile_refs: ['pelvis_fracture'], visible_body_zones: [{ zone: 'pelvis', label: 'Painful high-energy injury', severity: 'suspected' }],
    age_bands: ['18-24', '25-34', '35-44'], sex_values: ['F', 'M'], role_contexts: ['Airman', 'Civilian'],
    vital_ranges: { hr: [96, 132], bp_systolic: [94, 148], bp_diastolic: [56, 88], rr: [16, 30], spo2: [88, 99], temp_c_tenths: [360, 374], gcs: [12, 15] },
    hidden_findings: ['Monitoring changes may emerge after any externally directed intervention.'], deterioration: ['Respiratory and mental-status cues can change during the observation period.'],
    objectives: ['Recognize medication-safety cues', 'Document monitoring trends', 'Communicate changes without assuming a treatment rule'],
    cues: ['agitation', 'pain behavior', 'changing respiratory pattern'], complications: ['monitoring gap', 'adverse-event concern'],
    resource_events: ['monitor unavailable', 'staff diverted', 'handoff interrupted'], comms: ['normal', 'degraded'], resources: ['constrained'],
  },
  toxicology: {
    topic_id: 'toxicology', title_stem: 'Overdose recognition with recurrent deterioration risk',
    target_section: 'D_clinical', target_role: 'provider', difficulty: 'advanced', threat_type: 'toxic_exposure',
    locations: ['base clinic intake', 'ambulance transfer bay', 'field aid station'], mechanisms: ['suspected opioid-associated toxic exposure'],
    presentations: ['Casualty has depressed mental status, slow respirations, and an uncertain exposure history.'],
    injury_profile_refs: ['toxic_exposure'], visible_body_zones: [{ zone: 'head', label: 'Depressed mental status', severity: 'suspected' }, { zone: 'chest', label: 'Respiratory depression concern', severity: 'suspected' }],
    age_bands: ['18-24', '25-34', '35-44'], sex_values: ['F', 'M'], role_contexts: ['Service member', 'Civilian visitor'],
    vital_ranges: { hr: [48, 104], bp_systolic: [82, 132], bp_diastolic: [44, 82], rr: [6, 16], spo2: [72, 92], temp_c_tenths: [352, 370], gcs: [5, 12] },
    hidden_findings: ['Respiratory depression may recur during observation.'], deterioration: ['Respiratory rate and mental status may worsen again after transient improvement.'],
    objectives: ['Recognize toxidrome-compatible cues', 'Track recurrent changes', 'Document uncertainty and escalation needs'],
    cues: ['slow respirations', 'depressed consciousness', 'recurrent decline'], complications: ['recurrent respiratory depression concern', 'uncertain co-exposure'],
    resource_events: ['transport delayed', 'history unavailable', 'monitoring space constrained'], comms: ['normal', 'degraded'], resources: ['constrained'],
  },
  evacuation_transport: {
    topic_id: 'evacuation_transport', title_stem: 'En-route deterioration with degraded communication',
    target_section: 'B_transport', target_role: 'medic_or_technician', difficulty: 'advanced', threat_type: 'evacuation_delay',
    locations: ['rotary-wing evacuation cabin', 'ground ambulance convoy', 'patient movement staging area'], mechanisms: ['multi-system trauma requiring prolonged transport'],
    presentations: ['Casualty is initially stable enough for movement but has evolving respiratory and neurologic cues.'],
    injury_profile_refs: ['possible_tbi', 'possible_chest_contusion'], visible_body_zones: [{ zone: 'head', label: 'Neurologic monitoring concern', severity: 'suspected' }, { zone: 'chest', label: 'Respiratory monitoring concern', severity: 'suspected' }],
    age_bands: ['18-24', '25-34', '35-44'], sex_values: ['F', 'M'], role_contexts: ['Airman', 'Responder'],
    vital_ranges: { hr: [90, 132], bp_systolic: [92, 138], bp_diastolic: [52, 84], rr: [18, 32], spo2: [84, 96], temp_c_tenths: [350, 368], gcs: [10, 15] },
    hidden_findings: ['Transport stressors may expose previously subtle deterioration.'], deterioration: ['Communication, positioning, and monitoring interruptions alter observable cues.'],
    objectives: ['Perform serial reassessment', 'Maintain a concise handoff record', 'Adapt communication to transport constraints'],
    cues: ['changing respiratory effort', 'mental-status trend', 'monitoring interruption'], complications: ['transport delay', 'equipment access limitation'],
    resource_events: ['route diversion', 'communications blackout', 'monitor battery low'], comms: ['degraded', 'intermittent', 'unavailable'], resources: ['constrained'],
  },
  mass_casualty_systems: {
    topic_id: 'mass_casualty_systems', title_stem: 'Casualty-flow disruption during a surge event',
    target_section: 'I_mcc_ucc', target_role: 'mcc_ucc_controller', difficulty: 'expert', threat_type: 'mass_casualty_incident',
    locations: ['installation casualty collection network', 'medical command cell', 'facility surge corridor'], mechanisms: ['blast and ballistic casualty surge'],
    presentations: ['A representative casualty record shows evolving needs while the wider system exceeds normal capacity.'],
    injury_profile_refs: ['blast_injury'], visible_body_zones: [{ zone: 'chest', label: 'Representative blast casualty', severity: 'suspected' }],
    age_bands: ['18-24', '25-34', '35-44'], sex_values: ['F', 'M'], role_contexts: ['Airman', 'Civilian'],
    vital_ranges: { hr: [88, 134], bp_systolic: [88, 142], bp_diastolic: [50, 86], rr: [18, 34], spo2: [84, 98], temp_c_tenths: [352, 372], gcs: [9, 15] },
    hidden_findings: ['System-level delay may change individual casualty priority.'], deterioration: ['New arrivals and bed constraints alter the common operating picture.'],
    objectives: ['Track casualty flow', 'Recognize resource saturation', 'Document changes for handoff and review'],
    cues: ['arrival surge', 'bed saturation', 'transport queue growth'], complications: ['resource saturation', 'misrouted casualty risk'],
    resource_events: ['bed capacity exhausted', 'transport queue doubles', 'communications degraded'], comms: ['degraded', 'intermittent'], resources: ['overwhelmed'],
  },
  documentation_aar: {
    topic_id: 'documentation_aar', title_stem: 'Traceable handoff and performance-review scenario',
    target_section: 'C_patient_administration', target_role: 'admin_staff', difficulty: 'advanced', threat_type: 'documentation_disruption',
    locations: ['casualty tracking cell', 'handoff station', 'after-action review room'], mechanisms: ['trauma transfer with incomplete prehospital records'],
    presentations: ['Casualty arrives with partial identifiers, incomplete vital trends, and fragmented handoff information.'],
    injury_profile_refs: ['extremity_hemorrhage_controlled'], visible_body_zones: [{ zone: 'right_thigh', label: 'Prior field intervention documented incompletely', severity: 'controlled' }],
    age_bands: ['18-24', '25-34', '35-44'], sex_values: ['F', 'M'], role_contexts: ['Airman', 'Unknown casualty'],
    vital_ranges: { hr: [86, 126], bp_systolic: [92, 136], bp_diastolic: [54, 84], rr: [16, 30], spo2: [88, 99], temp_c_tenths: [356, 372], gcs: [11, 15] },
    hidden_findings: ['Missing timestamps obscure the trajectory of prior care.'], deterioration: ['Incomplete records create conflicting interpretations during handoff.'],
    objectives: ['Reconstruct a traceable timeline', 'Identify missing data', 'Preserve uncertainty in the handoff record'],
    cues: ['missing vital timestamp', 'conflicting identifier', 'undocumented intervention time'], complications: ['handoff ambiguity', 'duplicate casualty record'],
    resource_events: ['network unavailable', 'paper record damaged', 'simultaneous handoffs'], comms: ['degraded', 'intermittent'], resources: ['constrained', 'overwhelmed'],
  },
};
