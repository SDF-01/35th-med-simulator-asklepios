import type { PatientState } from '@/types';

function VitalsTile({
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
      className={`vitals-tile ${revealed ? 'vitals-tile--live' : 'vitals-tile--offline'} ${alert ? 'vitals-tile--alert' : ''}`}
    >
      <span className="vitals-tile__label">{label}</span>
      <span className="vitals-tile__value">
        {revealed ? value : '---'}
        {revealed && unit ? <span className="vitals-tile__unit">{unit}</span> : null}
      </span>
      {!revealed && <span className="vitals-tile__hint">no signal</span>}
    </div>
  );
}

interface ProviderVitalsBannerProps {
  patient: PatientState;
  /** When true, show ECG only (vitals strip owns numeric tiles). */
  hideTiles?: boolean;
}

export function ProviderVitalsBanner({ patient, hideTiles = false }: ProviderVitalsBannerProps) {
  const vitalsRevealed = patient.revealed_assessments.includes('vitals');
  const vitals = patient.vitals;
  const hrAlert = vitalsRevealed && vitals.hr > 100;
  const spo2Alert = vitalsRevealed && vitals.spo2 < 94;
  const bpAlert = vitalsRevealed && vitals.bp_systolic < 90;

  return (
    <div className={`provider-vitals-banner ${hideTiles ? 'provider-vitals-banner--ecg-only' : ''}`}>
      <div className="provider-vitals-banner__ecg-panel">
        <div className="provider-vitals-banner__ecg-header">
          <span className="provider-vitals-banner__ecg-label">ECG</span>
          <span
            className={`provider-vitals-banner__status ${vitalsRevealed ? 'provider-vitals-banner__status--live' : ''}`}
          >
            {vitalsRevealed ? 'LEAD II' : 'NO SIGNAL'}
          </span>
        </div>
        <div
          className={`provider-vitals-banner__ecg ${vitalsRevealed ? 'provider-vitals-banner__ecg--live' : ''}`}
        >
          <div className="provider-vitals-banner__ecg-grid" />
          <div className="provider-vitals-banner__ecg-trace" />
        </div>
      </div>

      {!hideTiles && (
        <>
          <div className="provider-vitals-banner__tiles">
            <VitalsTile label="HR" value={String(vitals.hr)} unit="bpm" revealed={vitalsRevealed} alert={hrAlert} />
            <VitalsTile
              label="BP"
              value={`${vitals.bp_systolic}/${vitals.bp_diastolic}`}
              unit="mmHg"
              revealed={vitalsRevealed}
              alert={bpAlert}
            />
            <VitalsTile label="RR" value={String(vitals.rr)} unit="/min" revealed={vitalsRevealed} />
            <VitalsTile
              label="SpO2"
              value={String(vitals.spo2)}
              unit="%"
              revealed={vitalsRevealed}
              alert={spo2Alert}
            />
            <VitalsTile label="GCS" value={String(vitals.gcs)} revealed={vitalsRevealed} />
          </div>

          {!vitalsRevealed && (
            <p className="provider-vitals-banner__prompt">
              No monitor connected. Assess patient to obtain vitals.
            </p>
          )}
        </>
      )}
    </div>
  );
}
