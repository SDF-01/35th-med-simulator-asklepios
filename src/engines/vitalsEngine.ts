import type { PatientState, Vitals } from '@/types';

function clampVitals(v: Vitals): Vitals {
  return {
    hr: Math.max(40, Math.min(180, Math.round(v.hr))),
    bp_systolic: Math.max(60, Math.min(180, Math.round(v.bp_systolic))),
    bp_diastolic: Math.max(40, Math.min(110, Math.round(v.bp_diastolic))),
    rr: Math.max(8, Math.min(40, Math.round(v.rr))),
    spo2: Math.max(70, Math.min(100, Math.round(v.spo2))),
    temp_c: Math.round(v.temp_c * 10) / 10,
    gcs: Math.max(3, Math.min(15, Math.round(v.gcs))),
  };
}

export function applyVitalsFromActions(
  patient: PatientState,
  completedActionIds: string[],
): PatientState {
  let vitals = { ...patient.vitals };

  if (completedActionIds.includes('hemorrhage_control')) {
    vitals.hr -= 12;
    vitals.bp_systolic += 8;
    vitals.bp_diastolic += 4;
  }

  if (completedActionIds.includes('airway_assessment')) {
    vitals.rr = Math.max(vitals.rr - 2, 14);
    vitals.spo2 += 1;
  }

  if (completedActionIds.includes('breathing_assessment')) {
    vitals.rr -= 3;
    vitals.spo2 += 2;
  }

  if (completedActionIds.includes('circulation_check')) {
    vitals.bp_systolic += 3;
  }

  if (completedActionIds.includes('order_imaging') || completedActionIds.includes('order_labs')) {
    vitals.rr -= 1;
  }

  if (completedActionIds.includes('escalation')) {
    vitals.gcs = Math.min(vitals.gcs + 1, 15);
  }

  return { ...patient, vitals: clampVitals(vitals) };
}

export function applyTurnDeterioration(
  patient: PatientState,
  turn: number,
  interval: number,
): PatientState {
  if (interval <= 0 || turn % interval !== 0) {
    return patient;
  }

  const bleedingUncontrolled = /active|hemorrhage|uncontrolled/i.test(patient.bleeding_status);

  let vitals = { ...patient.vitals };
  if (bleedingUncontrolled) {
    vitals.hr += 8;
    vitals.bp_systolic -= 6;
    vitals.spo2 -= 2;
    vitals.gcs = Math.max(vitals.gcs - 1, 3);
  } else {
    vitals.hr += 2;
    vitals.rr += 1;
  }

  return {
    ...patient,
    vitals: clampVitals(vitals),
    mental_status:
      vitals.gcs <= 10 ? 'Increasing confusion' : patient.mental_status,
  };
}

export function applyTreatmentTimePressure(
  patient: PatientState,
  elapsedMinutes: number,
  treatmentLimitMinutes: number,
): { patient: PatientState; alert?: string } {
  if (elapsedMinutes < treatmentLimitMinutes) {
    return { patient };
  }

  const vitals = clampVitals({
    ...patient.vitals,
    hr: patient.vitals.hr + 5,
    bp_systolic: patient.vitals.bp_systolic - 4,
    spo2: patient.vitals.spo2 - 2,
    rr: patient.vitals.rr + 2,
  });

  return {
    patient: { ...patient, vitals },
    alert:
      'Treatment time exceeded. Patient deteriorating while awaiting definitive care.',
  };
}
