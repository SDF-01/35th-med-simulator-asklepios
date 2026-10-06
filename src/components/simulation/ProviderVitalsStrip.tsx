import type { PatientState } from '@/types';

function StripTile({
  label,
  value,
  unit,
  revealed,
  alert = false,
}: {
  label: string;
  value: string;
  unit?: string;
  revealed: boolean;
  alert?: boolean;
}) {
  return (
    <div
      className={`provider-vitals-strip__tile ${revealed ? 'provider-vitals-strip__tile--live' : ''} ${alert ? 'provider-vitals-strip__tile--alert' : ''}`}
    >
      <span className="provider-vitals-strip__label">{label}</span>
      <span className="provider-vitals-strip__value">
        {revealed ? value : '---'}
        {revealed && unit ? <span className="provider-vitals-strip__unit">{unit}</span> : null}
      </span>
      {!revealed && <span className="provider-vitals-strip__hint">no sig</span>}
    </div>
  );
}

interface ProviderVitalsStripProps {
  patient: PatientState;
}

/** Compact always-visible vitals row for bedside simulation. */
export function ProviderVitalsStrip({ patient }: ProviderVitalsStripProps) {
  const vitalsRevealed = patient.revealed_assessments.includes('vitals');
  const vitals = patient.vitals;
  const hrAlert = vitalsRevealed && vitals.hr > 100;
  const spo2Alert = vitalsRevealed && vitals.spo2 < 94;
  const bpAlert = vitalsRevealed && vitals.bp_systolic < 90;

  return (
    <div className="provider-vitals-strip" role="region" aria-label="Patient vitals">
      <StripTile label="HR" value={String(vitals.hr)} unit="bpm" revealed={vitalsRevealed} alert={hrAlert} />
      <StripTile
        label="BP"
        value={`${vitals.bp_systolic}/${vitals.bp_diastolic}`}
        unit="mmHg"
        revealed={vitalsRevealed}
        alert={bpAlert}
      />
      <StripTile label="RR" value={String(vitals.rr)} unit="/m" revealed={vitalsRevealed} />
      <StripTile
        label="SpO2"
        value={String(vitals.spo2)}
        unit="%"
        revealed={vitalsRevealed}
        alert={spo2Alert}
      />
      <StripTile label="GCS" value={String(vitals.gcs)} revealed={vitalsRevealed} />
    </div>
  );
}
