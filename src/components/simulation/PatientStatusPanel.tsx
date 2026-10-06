import type { PatientState } from '@/types';
import { getSubjectiveHints } from '@/engines/assessmentRevealEngine';

function marchStatusClass(status: PatientState['march'][0]['status']): string {
  switch (status) {
    case 'critical':
      return 'text-ask-critical';
    case 'addressed':
      return 'text-ask-accent';
    case 'in_progress':
      return 'text-ask-caution';
    default:
      return 'text-ask-muted';
  }
}

function AssessmentRow({
  label,
  revealed,
  value,
}: {
  label: string;
  revealed: boolean;
  value: string;
}) {
  if (revealed) {
    return (
      <div>
        <span className="text-ask-muted">{label}: </span>
        <span className="font-mono">{value}</span>
      </div>
    );
  }

  return (
    <div className="text-ask-muted italic">
      {label}: not assessed
    </div>
  );
}

interface PatientStatusPanelProps {
  patients: PatientState[];
  mode: 'provider' | 'wit';
}

export function PatientStatusPanel({ patients, mode }: PatientStatusPanelProps) {
  const patient = patients[0];
  if (!patient) {
    return <p className="text-sm text-ask-muted">No patient data.</p>;
  }

  if (mode === 'wit') {
    return (
      <div className="space-y-4 text-sm">
        <p className="text-xs uppercase tracking-wider text-ask-accent">WIT: Confirmed Patient Data</p>

        <div>
          <p className="mb-2 text-xs uppercase tracking-wider text-ask-muted">Vitals (Actual)</p>
          <div className="grid grid-cols-2 gap-2 font-mono text-xs">
            <div>HR: {patient.vitals.hr}</div>
            <div>
              BP: {patient.vitals.bp_systolic}/{patient.vitals.bp_diastolic}
            </div>
            <div>RR: {patient.vitals.rr}</div>
            <div>SpO2: {patient.vitals.spo2}%</div>
            <div>Temp: {patient.vitals.temp_c}C</div>
            <div>GCS: {patient.vitals.gcs}</div>
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs uppercase tracking-wider text-ask-muted">MARCH</p>
          <ul className="space-y-1">
            {patient.march.map((step) => (
              <li key={step.step} className="flex items-center justify-between">
                <span>{step.label}</span>
                <span className={`text-xs uppercase ${marchStatusClass(step.status)}`}>
                  {step.status.replace('_', ' ')}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <p className="mb-2 text-xs uppercase tracking-wider text-ask-muted">Bleeding</p>
          <p>{patient.bleeding_status}</p>
        </div>

        <div>
          <p className="mb-2 text-xs uppercase tracking-wider text-ask-muted">Injuries</p>
          <ul className="list-inside list-disc space-y-1">
            {patient.known_injuries.map((injury) => (
              <li key={injury}>{injury}</li>
            ))}
          </ul>
        </div>

        {patient.revealed_findings.length > 0 && (
          <div>
            <p className="mb-2 text-xs uppercase tracking-wider text-ask-muted">Hidden Findings</p>
            <ul className="list-inside list-disc space-y-1 text-ask-caution">
              {patient.revealed_findings.map((finding) => (
                <li key={finding}>{finding}</li>
              ))}
            </ul>
          </div>
        )}

        {patient.interventions.length > 0 && (
          <div>
            <p className="mb-2 text-xs uppercase tracking-wider text-ask-muted">Interventions</p>
            <ul className="list-inside list-disc space-y-1">
              {patient.interventions.map((intervention) => (
                <li key={intervention}>{intervention}</li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <p className="mb-2 text-xs uppercase tracking-wider text-ask-muted">
            Provider-Confirmed Assessments
          </p>
          <p className="text-xs text-ask-muted">
            {patient.revealed_assessments.length
              ? patient.revealed_assessments.join(', ')
              : 'None yet. Provider has not assessed.'}
          </p>
        </div>
      </div>
    );
  }

  const vitalsRevealed = patient.revealed_assessments.includes('vitals');
  const hints = getSubjectiveHints(patient);

  return (
    <div className="space-y-4 text-sm">
      <p className="text-xs uppercase tracking-wider text-ask-muted">
        Clinical Observations (Unconfirmed)
      </p>
      <p className="text-xs text-ask-muted italic">
        No monitors visible. Assess the patient through examination and orders to confirm findings.
      </p>

      <div>
        <p className="mb-2 text-xs uppercase tracking-wider text-ask-muted">Subjective Impressions</p>
        <ul className="list-inside list-disc space-y-1 text-ask-text/80">
          {hints.map((hint) => (
            <li key={hint}>{hint}</li>
          ))}
        </ul>
      </div>

      <div>
        <p className="mb-2 text-xs uppercase tracking-wider text-ask-muted">Confirmed by You</p>
        <div className="space-y-1 font-mono text-xs">
          <AssessmentRow
            label="Vitals"
            revealed={vitalsRevealed}
            value={`HR ${patient.vitals.hr} | BP ${patient.vitals.bp_systolic}/${patient.vitals.bp_diastolic} | RR ${patient.vitals.rr} | SpO2 ${patient.vitals.spo2}%`}
          />
          <AssessmentRow
            label="Mental status"
            revealed={patient.revealed_assessments.includes('mental_status')}
            value={patient.mental_status}
          />
          <AssessmentRow
            label="Bleeding"
            revealed={patient.revealed_assessments.includes('bleeding')}
            value={patient.bleeding_status}
          />
          <AssessmentRow
            label="Injuries"
            revealed={patient.revealed_assessments.includes('injuries')}
            value={patient.known_injuries.join('; ')}
          />
        </div>
      </div>

      {patient.interventions.length > 0 && (
        <div>
          <p className="mb-2 text-xs uppercase tracking-wider text-ask-muted">Your Interventions</p>
          <ul className="list-inside list-disc space-y-1">
            {patient.interventions.map((intervention) => (
              <li key={intervention}>{intervention}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
