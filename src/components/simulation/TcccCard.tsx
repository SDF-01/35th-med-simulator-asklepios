import { useMemo, useState } from 'react';
import type { ScenarioPatient, PatientState } from '@/types';
import type { BodyZone } from '@/types/bodyInjury';
import { TcccInjuryDiagram } from '@/components/simulation/TcccInjuryDiagram';
import { TCCC_MOI_ROW_A, TCCC_MOI_ROW_B } from '@/content/tcccFormDiagram';
import {
  resolveDisplayedInjuryHighlights,
  resolveScenarioInjuryCatalog,
} from '@/engines/injuryBodyMapper';
import {
  buildPatientDisplayName,
  buildTcccVitalsRow,
  formatTcccDate,
  formatTcccTime,
  resolveEvacCategory,
  resolveMechanismChecks,
  resolveMechanismOtherText,
  resolveTourniquetEntries,
} from '@/engines/tcccCardMapper';

interface TcccCardProps {
  scenarioPatient: ScenarioPatient;
  patientState: PatientState;
  sessionStartTime?: number;
  unitLabel?: string;
}

const VITALS_TIME_COLUMNS = 5;

export function TcccCard({
  scenarioPatient,
  patientState,
  sessionStartTime,
  unitLabel = 'Training evolution',
}: TcccCardProps) {
  const [selectedZone, setSelectedZone] = useState<BodyZone | null>(null);

  const highlights = resolveDisplayedInjuryHighlights(scenarioPatient, patientState);
  const catalog = resolveScenarioInjuryCatalog(scenarioPatient);
  const injuriesRevealed = patientState.revealed_assessments.includes('injuries');
  const vitalsRevealed = patientState.revealed_assessments.includes('vitals');

  const moiChecks = resolveMechanismChecks(scenarioPatient.mechanism_of_injury);
  const moiOther = resolveMechanismOtherText(scenarioPatient.mechanism_of_injury, moiChecks);
  const tqEntries = resolveTourniquetEntries(
    highlights,
    patientState.interventions,
    sessionStartTime,
  );

  const now = sessionStartTime ?? Date.now();
  const vitalsRow = buildTcccVitalsRow(
    patientState.vitals,
    vitalsRevealed,
    formatTcccTime(now),
  );

  const selectedInjury = useMemo(
    () => highlights.find((h) => h.zone === selectedZone),
    [highlights, selectedZone],
  );

  return (
    <div className="tccc-form-shell" role="region" aria-label="Tactical Combat Casualty Care card">
      <article className="tccc-form">
        <div className="tccc-form__rule tccc-form__rule--top" />

        <div className="tccc-form__meta-row">
          <FormLine label="EVAC CATEGORY" value={resolveEvacCategory(patientState.triage_category)} />
          <FormLine
            label="BATTLE ROSTER #"
            value={scenarioPatient.patient_id}
            align="right"
          />
        </div>

        <div className="tccc-form__rule" />

        <h2 className="tccc-form__title">TACTICAL COMBAT CASUALTY CARE (TCCC) CARD</h2>

        <div className="tccc-form__rule" />

        <div className="tccc-form__identity-row tccc-form__identity-row--primary">
          <FormLine
            label="NAME (Last, First)"
            value={buildPatientDisplayName(scenarioPatient)}
            wide
          />
          <FormLine label="LAST 4" value={scenarioPatient.patient_id.slice(-4)} narrow />
          <FormLine label="DATE (DD-MMM-YY)" value={formatTcccDate(now)} narrow />
          <FormLine label="TIME" value={formatTcccTime(now)} narrow />
        </div>

        <div className="tccc-form__identity-row">
          <FormLine label="UNIT" value={unitLabel} wide />
          <FormLine label="ALLERGIES" value="NKDA" wide />
        </div>

        <div className="tccc-form__rule" />

        <section className="tccc-form__block">
          <p className="tccc-form__prompt">Mechanism of Injury: (X all that apply)</p>
          <div className="tccc-form__moi-row">
            {TCCC_MOI_ROW_A.map((option) => (
              <MoiCheck key={option} label={option} checked={moiChecks[option]} />
            ))}
          </div>
          <div className="tccc-form__moi-row">
            {TCCC_MOI_ROW_B.map((option) => (
              <MoiCheck
                key={option}
                label={option}
                checked={moiChecks[option]}
                trailingLine={option === 'Other'}
                trailingValue={option === 'Other' ? moiOther : undefined}
              />
            ))}
          </div>
        </section>

        <div className="tccc-form__rule" />

        <section className="tccc-form__block">
          <p className="tccc-form__prompt">Injury: (Mark injuries with an X)</p>
          <TcccInjuryDiagram
            highlights={highlights}
            tqEntries={tqEntries}
            selectedZone={selectedZone}
            onSelectZone={setSelectedZone}
          />
          {selectedInjury ? (
            <p className="tccc-form__note tccc-form__note--active" role="status">
              {selectedInjury.label}
            </p>
          ) : catalog.some((h) => h.severity === 'suspected') && !injuriesRevealed ? (
            <p className="tccc-form__note">
              Tap an X to inspect. Complete injury survey to document suspected sites.
            </p>
          ) : null}
        </section>

        <div className="tccc-form__rule" />

        <section className="tccc-form__block">
          <p className="tccc-form__prompt">Signs &amp; Symptoms: (Fill in the blank)</p>
          <table className="tccc-form__vitals">
            <tbody>
              <tr>
                <th scope="row">Time</th>
                {Array.from({ length: VITALS_TIME_COLUMNS }, (_, index) => (
                  <td key={index}>{index === 0 && vitalsRevealed ? vitalsRow.time : ''}</td>
                ))}
              </tr>
              <VitalsDataRow
                label="Pulse (Rate & Location)"
                value={vitalsRow.pulse}
                revealed={vitalsRevealed}
                shaded
              />
              <VitalsDataRow label="Blood Pressure" value={vitalsRow.bp} revealed={vitalsRevealed} />
              <VitalsDataRow
                label="Respiratory Rate"
                value={vitalsRow.rr}
                revealed={vitalsRevealed}
                shaded
              />
              <VitalsDataRow
                label="Pulse Ox % O2 Sat"
                value={vitalsRow.spo2}
                revealed={vitalsRevealed}
              />
              <VitalsDataRow label="AVPU" value={vitalsRow.avpu} revealed={vitalsRevealed} shaded />
              <VitalsDataRow
                label="Pain Scale (0-10)"
                value={vitalsRow.pain}
                revealed={vitalsRevealed}
                shaded
              />
            </tbody>
          </table>
        </section>

        <div className="tccc-form__rule tccc-form__rule--bottom" />
      </article>

      <footer className="tccc-form__footer">
        <span>DD FORM 1380</span>
        <span>Page 1 of 2</span>
      </footer>
      <p className="tccc-form__sim-disclaimer">Training simulation. Not for operational use.</p>
    </div>
  );
}

function FormLine({
  label,
  value,
  wide = false,
  narrow = false,
  align = 'left',
}: {
  label: string;
  value: string;
  wide?: boolean;
  narrow?: boolean;
  align?: 'left' | 'right';
}) {
  return (
    <div
      className={[
        'tccc-form__line-field',
        wide ? 'tccc-form__line-field--wide' : '',
        narrow ? 'tccc-form__line-field--narrow' : '',
        align === 'right' ? 'tccc-form__line-field--right' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <span className="tccc-form__line-label">{label}</span>
      <span className="tccc-form__line-value">{value}</span>
    </div>
  );
}

function MoiCheck({
  label,
  checked,
  trailingLine,
  trailingValue,
}: {
  label: string;
  checked: boolean;
  trailingLine?: boolean;
  trailingValue?: string;
}) {
  return (
    <span className={`tccc-form__moi-item ${trailingLine ? 'tccc-form__moi-item--other' : ''}`}>
      <span className={`tccc-form__moi-box ${checked ? 'tccc-form__moi-box--checked' : ''}`}>
        {checked ? 'X' : ''}
      </span>
      <span>{label}</span>
      {trailingLine && <span className="tccc-form__moi-other">{trailingValue ?? ''}</span>}
    </span>
  );
}

function VitalsDataRow({
  label,
  value,
  revealed,
  shaded = false,
}: {
  label: string;
  value: string;
  revealed: boolean;
  shaded?: boolean;
}) {
  const cells = Array<string>(VITALS_TIME_COLUMNS).fill('');
  if (revealed && value) cells[0] = value;

  return (
    <tr className={shaded ? 'tccc-form__vitals-row--shaded' : undefined}>
      <th scope="row">{label}</th>
      {cells.map((cell, index) => (
        <td key={index}>{cell}</td>
      ))}
    </tr>
  );
}
