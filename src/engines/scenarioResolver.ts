import type { MedicalSection } from '@/types';
import type { HospitalDepartmentId } from '@/types/providerProfile';
import { HOSPITAL_DEPARTMENTS, normalizeHospitalDepartmentId } from '@/types/providerProfile';
import type { ScenarioSelection } from '@/content/scenarioTaxonomy';
import {
  getCategoryById,
  getEventTypeById,
  getSpecificOption,
} from '@/content/scenarioTaxonomy';

const FIELD_EVENTS = new Set([
  'inbound_missile',
  'drone_attack',
  'explosion_blast',
  'indirect_fire',
  'sniper_attack',
  'unexploded_ordnance',
  'active_shooter',
  'vehicle_accident',
]);

const ADMIN_HEAVY_EVENTS = new Set(['mass_casualty_incident', 'cyber_attack_cascading']);

const LAB_EVENTS = new Set(['cbrne', 'biological_agent', 'chemical_agent', 'hazmat_release']);

const RADIOLOGY_EVENTS = new Set(['explosion_blast', 'structural_collapse', 'earthquake']);

const PHARMACY_EVENTS = new Set(['cbrne', 'biological_agent', 'chemical_agent']);

const FIELD_DEPARTMENTS = new Set<HospitalDepartmentId>([
  'field_response_team',
  'triage',
  'decon',
  'manpower_security',
]);

const CLINICAL_DEPARTMENTS = new Set<HospitalDepartmentId>([
  'clinical_immediate',
  'clinical_delayed',
  'clinical_minimal',
]);

const COMMAND_DEPARTMENTS = new Set<HospitalDepartmentId>([
  'emergency_ops_center',
  'medical_command_center',
  'logistics',
]);

const DEPARTMENT_DEFAULT_SCENARIO: Record<HospitalDepartmentId, string> = {
  field_response_team: 'ASK-A-001',
  triage: 'ASK-A-001',
  clinical_immediate: 'ASK-D-001',
  clinical_delayed: 'ASK-D-001',
  clinical_minimal: 'ASK-D-001',
  surgery: 'ASK-D-001',
  radiology: 'ASK-D-001',
  lab: 'ASK-D-001',
  pharm: 'ASK-D-001',
  emergency_ops_center: 'ASK-D-001',
  medical_command_center: 'ASK-D-001',
  patient_administration: 'ASK-D-001',
  transport: 'ASK-A-001',
  manpower_security: 'ASK-A-001',
  decon: 'ASK-A-001',
  logistics: 'ASK-D-001',
};

const PLAYABLE_SCENARIOS = new Set(['ASK-A-001', 'ASK-D-001']);

export function resolveBaseScenarioId(
  selection: ScenarioSelection,
  department: HospitalDepartmentId | string,
): string {
  const dept = normalizeHospitalDepartmentId(department);
  const eventId = selection.eventTypeId;

  if (FIELD_DEPARTMENTS.has(dept) || FIELD_EVENTS.has(eventId)) {
    return 'ASK-A-001';
  }

  if (dept === 'patient_administration' || ADMIN_HEAVY_EVENTS.has(eventId)) {
    return 'ASK-D-001';
  }

  if (dept === 'lab' || LAB_EVENTS.has(eventId)) {
    return 'ASK-D-001';
  }

  if (dept === 'radiology' || RADIOLOGY_EVENTS.has(eventId)) {
    return 'ASK-D-001';
  }

  if (dept === 'pharm' || PHARMACY_EVENTS.has(eventId)) {
    return 'ASK-D-001';
  }

  if (
    dept === 'surgery' ||
    COMMAND_DEPARTMENTS.has(dept) ||
    CLINICAL_DEPARTMENTS.has(dept) ||
    dept === 'transport' ||
    dept === 'logistics'
  ) {
    return 'ASK-D-001';
  }

  const fallback = DEPARTMENT_DEFAULT_SCENARIO[dept];
  return fallback && PLAYABLE_SCENARIOS.has(fallback) ? fallback : 'ASK-D-001';
}

export function buildScenarioContextNarrative(
  selection: ScenarioSelection,
  department: HospitalDepartmentId | string,
  providerName?: string,
): string {
  const dept = normalizeHospitalDepartmentId(department);
  const category = getCategoryById(selection.categoryId);
  const event = getEventTypeById(selection.eventTypeId);
  const specific = getSpecificOption(selection.eventTypeId, selection.specificId);
  const office = HOSPITAL_DEPARTMENTS.find((d) => d.id === dept);

  const parts = [
    category?.settingNarrative,
    specific?.narrativeDetail ?? event?.description,
    office ? `Training tailored for ${office.label} workflow and scope of practice.` : undefined,
    providerName?.trim()
      ? `Provider profile: ${providerName.trim()} (${office?.label ?? dept}).`
      : undefined,
  ].filter(Boolean);

  return parts.join(' ');
}

export function getDepartmentPreferredSections(
  department: HospitalDepartmentId | string,
): MedicalSection[] {
  const dept = normalizeHospitalDepartmentId(department);
  return HOSPITAL_DEPARTMENTS.find((d) => d.id === dept)?.preferredSections ?? ['D_clinical'];
}

export function isScenarioPlayable(scenarioId: string): boolean {
  return PLAYABLE_SCENARIOS.has(scenarioId);
}

export function getResolvedScenarioLabel(
  selection: ScenarioSelection,
  baseScenarioId: string,
): string {
  const category = getCategoryById(selection.categoryId);
  const event = getEventTypeById(selection.eventTypeId);
  const specific = getSpecificOption(selection.eventTypeId, selection.specificId);
  return `${category?.label} / ${event?.label} / ${specific?.label} (${baseScenarioId})`;
}
