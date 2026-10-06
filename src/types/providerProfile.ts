import type { MedicalSection } from '@/types';

export type HospitalDepartmentId =
  | 'field_response_team'
  | 'triage'
  | 'clinical_immediate'
  | 'clinical_delayed'
  | 'clinical_minimal'
  | 'surgery'
  | 'radiology'
  | 'lab'
  | 'pharm'
  | 'emergency_ops_center'
  | 'medical_command_center'
  | 'patient_administration'
  | 'transport'
  | 'manpower_security'
  | 'decon'
  | 'logistics';

/** @deprecated Legacy IDs from prior profile saves — mapped on load */
export type LegacyHospitalDepartmentId =
  | 'first_responder'
  | 'urgent_care'
  | 'emergency_department'
  | 'clinical_inpatient'
  | 'laboratory'
  | 'pharmacy'
  | 'mcc_ucc';

export interface ProviderProfile {
  fullName: string;
  hospitalDepartment: HospitalDepartmentId;
}

export interface HospitalDepartmentOption {
  id: HospitalDepartmentId;
  label: string;
  description: string;
  preferredSections: MedicalSection[];
}

export interface ResponseOfficeGroup {
  label: string;
  options: HospitalDepartmentOption[];
}

const LEGACY_DEPARTMENT_MAP: Record<LegacyHospitalDepartmentId, HospitalDepartmentId> = {
  first_responder: 'field_response_team',
  urgent_care: 'clinical_immediate',
  emergency_department: 'clinical_immediate',
  clinical_inpatient: 'clinical_delayed',
  laboratory: 'lab',
  pharmacy: 'pharm',
  mcc_ucc: 'medical_command_center',
};

export const HOSPITAL_DEPARTMENTS: HospitalDepartmentOption[] = [
  {
    id: 'field_response_team',
    label: 'Field Response Team',
    description: 'Point-of-injury response, scene safety, initial stabilization',
    preferredSections: ['A_field_reaction_triage_incident_response'],
  },
  {
    id: 'triage',
    label: 'Triage',
    description: 'Sort, tag, and prioritize casualties under surge',
    preferredSections: ['A_field_reaction_triage_incident_response'],
  },
  {
    id: 'clinical_immediate',
    label: 'Clinical (Immediate)',
    description: 'Life-threatening casualties requiring immediate intervention',
    preferredSections: ['D_clinical'],
  },
  {
    id: 'clinical_delayed',
    label: 'Clinical (Delayed)',
    description: 'Urgent casualties that can wait briefly for definitive care',
    preferredSections: ['D_clinical'],
  },
  {
    id: 'clinical_minimal',
    label: 'Clinical (Minimal)',
    description: 'Walking wounded and minor injuries in clinical workflow',
    preferredSections: ['D_clinical'],
  },
  {
    id: 'surgery',
    label: 'Surgery',
    description: 'Operative triage, OR queue, and pre-op handoff',
    preferredSections: ['H_surgery', 'D_clinical'],
  },
  {
    id: 'radiology',
    label: 'Radiology',
    description: 'Imaging prioritization and critical findings communication',
    preferredSections: ['E_radiology'],
  },
  {
    id: 'lab',
    label: 'Lab',
    description: 'Specimen triage, critical values, and surge processing',
    preferredSections: ['F_lab'],
  },
  {
    id: 'pharm',
    label: 'Pharm',
    description: 'Medication safety, formulary, and allergy checks under surge',
    preferredSections: ['G_pharmacy'],
  },
  {
    id: 'emergency_ops_center',
    label: 'Emergency Ops Center',
    description: 'Installation emergency operations and resource coordination',
    preferredSections: ['I_mcc_ucc'],
  },
  {
    id: 'medical_command_center',
    label: 'Medical Command Center',
    description: 'Medical command, casualty flow, and capacity oversight',
    preferredSections: ['I_mcc_ucc'],
  },
  {
    id: 'patient_administration',
    label: 'Patient Administration',
    description: 'Tracking, identifiers, flow, and privacy under MCI',
    preferredSections: ['C_patient_administration'],
  },
  {
    id: 'transport',
    label: 'Transport',
    description: 'CASEVAC/MEDEVAC coordination and en-route care',
    preferredSections: ['B_transport'],
  },
  {
    id: 'manpower_security',
    label: 'Man Power Security',
    description: 'Force protection, access control, and personnel accountability',
    preferredSections: ['A_field_reaction_triage_incident_response', 'I_mcc_ucc'],
  },
  {
    id: 'decon',
    label: 'In place Patient Decontamination (De-con)',
    description: 'Decontamination lanes, patient flow, and CBRNE support',
    preferredSections: ['A_field_reaction_triage_incident_response'],
  },
  {
    id: 'logistics',
    label: 'Logistics',
    description: 'Supply, equipment, and sustainment under constrained resources',
    preferredSections: ['I_mcc_ucc', 'G_pharmacy'],
  },
];

export const RESPONSE_OFFICE_GROUPS: ResponseOfficeGroup[] = [
  {
    label: 'Response Offices',
    options: HOSPITAL_DEPARTMENTS.filter((d) =>
      ['field_response_team', 'triage'].includes(d.id),
    ),
  },
  {
    label: 'Clinical',
    options: HOSPITAL_DEPARTMENTS.filter((d) => d.id.startsWith('clinical_')),
  },
  {
    label: 'Specialty & Support',
    options: HOSPITAL_DEPARTMENTS.filter((d) =>
      ['surgery', 'radiology', 'lab', 'pharm'].includes(d.id),
    ),
  },
  {
    label: 'Command & Administration',
    options: HOSPITAL_DEPARTMENTS.filter((d) =>
      [
        'emergency_ops_center',
        'medical_command_center',
        'patient_administration',
        'transport',
        'manpower_security',
        'decon',
        'logistics',
      ].includes(d.id),
    ),
  },
];

export const DEFAULT_PROVIDER_PROFILE: ProviderProfile = {
  fullName: '',
  hospitalDepartment: 'clinical_immediate',
};

export function normalizeHospitalDepartmentId(
  id: string | undefined,
): HospitalDepartmentId {
  if (!id) return DEFAULT_PROVIDER_PROFILE.hospitalDepartment;
  if (HOSPITAL_DEPARTMENTS.some((d) => d.id === id)) {
    return id as HospitalDepartmentId;
  }
  const migrated = LEGACY_DEPARTMENT_MAP[id as LegacyHospitalDepartmentId];
  return migrated ?? DEFAULT_PROVIDER_PROFILE.hospitalDepartment;
}

export function getDepartmentLabel(id: HospitalDepartmentId | string): string {
  const normalized = normalizeHospitalDepartmentId(id);
  return HOSPITAL_DEPARTMENTS.find((d) => d.id === normalized)?.label ?? normalized;
}

export function getDepartmentOption(
  id: HospitalDepartmentId | string,
): HospitalDepartmentOption | undefined {
  const normalized = normalizeHospitalDepartmentId(id);
  return HOSPITAL_DEPARTMENTS.find((d) => d.id === normalized);
}
