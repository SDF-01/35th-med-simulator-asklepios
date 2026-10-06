import { useEffect, useMemo, useRef, useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { AppFooter, PageShell } from '@/components/ui/PageShell';
import { facilityArrivalContext } from '@/facility-arrival/context';
import {
  FACILITY_DECISION_ALTERNATE_SEQUENCE,
  FACILITY_DECISION_CANONICAL_SEQUENCE,
  applyFacilityDecisionSubmission,
  buildFacilityDecisionView,
  createFacilityDecisionSession,
  facilityDecisionContext,
  facilityDecisionSubmission,
  facilityDecisionSubmissionId,
  validateFacilityDecisionSubmission,
} from '@/facility-decision';
import type {
  FacilityDecisionActionView,
  FacilityDecisionFieldPresentation,
  FacilityDecisionIntegritySession,
  FacilityDecisionUiMode,
  FacilityDecisionValidationResult,
  FacilityDecisionValue,
} from '@/facility-decision';

const context = facilityDecisionContext(facilityArrivalContext);

const MODE_COPY: Record<FacilityDecisionUiMode, { label: string; description: string }> = {
  learner_assessment: {
    label: 'Learner assessment',
    description: 'No live score, points, provenance, WIT observations, correctness labels, autoplay, or completed replay are supplied to this projection.',
  },
  learner_teaching: {
    label: 'Learner teaching',
    description: 'Prerequisite explanations are available, but scores, answer labels, provenance, and evaluator-only observations remain absent.',
  },
  instructor: {
    label: 'Instructor review',
    description: 'Instructor-only source binding, multidimensional records, and process observations are available for facilitated review.',
  },
  stakeholder_demo: {
    label: 'Stakeholder demonstration',
    description: 'Autoplay and explicit branch demonstrations are enabled. This route is not a learner assessment.',
  },
};

const VALIDATION_REASON_COPY: Record<string, string> = {
  missing: 'is required.',
  type: 'has an invalid value type.',
  min_length: 'needs a more complete response.',
  allowed_values: 'must use one of the listed values.',
  min_items: 'requires more selected or listed items.',
  required_values: 'is missing one or more required selections.',
  must_equal: 'must be explicitly confirmed.',
};

function formatTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

function formatIdentifier(value: string): string {
  return value.replaceAll('_', ' ');
}

function initialValue(field: FacilityDecisionFieldPresentation): FacilityDecisionValue {
  if (field.type === 'boolean') return false;
  if (field.type === 'multi_choice' || field.type === 'list') return [];
  return '';
}

function valuesFor(action: FacilityDecisionActionView): Record<string, FacilityDecisionValue> {
  return Object.fromEntries(action.fields.map((field) => [field.field_id, initialValue(field)]));
}

function runSequence(sequence: readonly string[], mode: FacilityDecisionUiMode): FacilityDecisionIntegritySession {
  let session = createFacilityDecisionSession(facilityArrivalContext, mode);
  sequence.forEach((decisionId, index) => {
    session = applyFacilityDecisionSubmission(
      session,
      facilityDecisionSubmission(decisionId, session.revision, index + 1),
      context,
    );
  });
  return session;
}

function runHighRisk(decisionId: 'discharge_without_workup' | 'remove_tourniquet'): FacilityDecisionIntegritySession {
  let session = createFacilityDecisionSession(facilityArrivalContext, 'stakeholder_demo');
  for (const [index, next] of ['receive_handoff', decisionId].entries()) {
    session = applyFacilityDecisionSubmission(
      session,
      facilityDecisionSubmission(next, session.revision, index + 1),
      context,
    );
  }
  return session;
}

function fieldIdFromValidationError(error: string): string | null {
  const fieldMatch = /^field:([^:]+):/.exec(error);
  if (fieldMatch?.[1]) return fieldMatch[1];
  if (error === 'high_risk_confirmation_required') return 'deliberate_confirmation';
  if (error === 'high_risk_rationale_required') return 'rationale';
  return null;
}

function validationErrorCopy(
  error: string,
  fields: readonly FacilityDecisionFieldPresentation[],
): string {
  const fieldId = fieldIdFromValidationError(error);
  const fieldLabel = fields.find((field) => field.field_id === fieldId)?.label ?? formatIdentifier(fieldId ?? 'submission');
  const reason = /^field:[^:]+:(.+)$/.exec(error)?.[1];
  if (reason) return `${fieldLabel} ${VALIDATION_REASON_COPY[reason] ?? `could not be accepted (${formatIdentifier(reason)}).`}`;
  if (error === 'high_risk_confirmation_required') return `${fieldLabel} must be selected before this deliberate branch can be recorded.`;
  if (error === 'high_risk_rationale_required') return `${fieldLabel} must explain the deliberate choice in at least 15 characters.`;
  if (error.startsWith('unknown_field:')) return 'The submission contains a field that is not part of the reviewed decision contract.';
  if (error.startsWith('concrete_treatment_field_forbidden:') || error === 'concrete_treatment_activation_forbidden') {
    return 'Concrete treatment activation is outside this training contract and remains blocked.';
  }
  return `The submission could not be accepted: ${formatIdentifier(error)}.`;
}

function errorsForField(validation: FacilityDecisionValidationResult | null, fieldId: string): string[] {
  if (!validation) return [];
  return validation.errors.filter((error) => fieldIdFromValidationError(error) === fieldId);
}

function FieldErrors({ id, errors, fields }: {
  id: string;
  errors: readonly string[];
  fields: readonly FacilityDecisionFieldPresentation[];
}) {
  if (errors.length === 0) return null;
  return (
    <ul id={id} className="mt-2 space-y-1 text-sm text-ask-critical" aria-live="polite">
      {errors.map((error) => <li key={error}>{validationErrorCopy(error, fields)}</li>)}
    </ul>
  );
}

function FieldEditor({
  field,
  value,
  errors,
  allFields,
  onChange,
}: {
  field: FacilityDecisionFieldPresentation;
  value: FacilityDecisionValue;
  errors: readonly string[];
  allFields: readonly FacilityDecisionFieldPresentation[];
  onChange: (value: FacilityDecisionValue) => void;
}) {
  const id = `decision-field-${field.field_id}`;
  const errorId = `${id}-error`;
  const describedBy = errors.length > 0 ? errorId : undefined;
  const required = field.required ? ' *' : '';

  if (field.type === 'boolean') {
    return (
      <div>
        <label htmlFor={id} className="flex min-h-11 items-start gap-3 rounded-ask-sm border border-ask-border p-3 text-sm text-ask-text-dim focus-within:border-ask-accent/50">
          <input
            id={id}
            type="checkbox"
            checked={value === true}
            aria-invalid={errors.length > 0 || undefined}
            aria-describedby={describedBy}
            onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.checked)}
            className="mt-0.5 h-5 w-5 shrink-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ask-accent"
          />
          <span>{field.label}{required}</span>
        </label>
        <FieldErrors id={errorId} errors={errors} fields={allFields} />
      </div>
    );
  }

  if (field.type === 'choice') {
    return (
      <label htmlFor={id} className="block text-sm text-ask-text-dim">
        <span className="mb-1 block font-medium text-ask-text">{field.label}{required}</span>
        <select
          id={id}
          value={typeof value === 'string' ? value : ''}
          aria-invalid={errors.length > 0 || undefined}
          aria-describedby={describedBy}
          onChange={(event: ChangeEvent<HTMLSelectElement>) => onChange(event.target.value)}
          className="min-h-11 w-full rounded-ask-sm border border-ask-border bg-ask-panel px-3 py-2 text-ask-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ask-accent aria-[invalid=true]:border-ask-critical"
        >
          <option value="">Select…</option>
          {(field.allowed_values ?? []).map((item) => <option key={item} value={item}>{formatIdentifier(item)}</option>)}
        </select>
        <FieldErrors id={errorId} errors={errors} fields={allFields} />
      </label>
    );
  }

  if (field.type === 'multi_choice') {
    const selected = Array.isArray(value) ? value : [];
    return (
      <fieldset
        aria-invalid={errors.length > 0 || undefined}
        aria-describedby={describedBy}
        className="rounded-ask-sm border border-ask-border p-3 aria-[invalid=true]:border-ask-critical"
      >
        <legend className="px-1 text-sm font-medium text-ask-text">{field.label}{required}</legend>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {(field.allowed_values ?? []).map((item) => (
            <label key={item} className="flex min-h-11 items-center gap-2 rounded-ask-sm px-2 text-sm text-ask-text-dim hover:bg-ask-surface">
              <input
                type="checkbox"
                checked={selected.includes(item)}
                onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.checked
                  ? [...selected, item]
                  : selected.filter((candidate) => candidate !== item))}
                className="h-5 w-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ask-accent"
              />
              {formatIdentifier(item)}
            </label>
          ))}
        </div>
        <FieldErrors id={errorId} errors={errors} fields={allFields} />
      </fieldset>
    );
  }

  if (field.type === 'list') {
    return (
      <label htmlFor={id} className="block text-sm text-ask-text-dim">
        <span className="mb-1 block font-medium text-ask-text">{field.label}{required}</span>
        <textarea
          id={id}
          rows={3}
          value={Array.isArray(value) ? value.join('\n') : ''}
          aria-invalid={errors.length > 0 || undefined}
          aria-describedby={describedBy}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => onChange(event.target.value.split('\n').map((line: string) => line.trim()).filter(Boolean))}
          placeholder="One item per line"
          className="w-full rounded-ask-sm border border-ask-border bg-ask-panel px-3 py-2 text-ask-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ask-accent aria-[invalid=true]:border-ask-critical"
        />
        <FieldErrors id={errorId} errors={errors} fields={allFields} />
      </label>
    );
  }

  return (
    <label htmlFor={id} className="block text-sm text-ask-text-dim">
      <span className="mb-1 block font-medium text-ask-text">{field.label}{required}</span>
      <textarea
        id={id}
        rows={3}
        value={typeof value === 'string' ? value : ''}
        aria-invalid={errors.length > 0 || undefined}
        aria-describedby={describedBy}
        onChange={(event: ChangeEvent<HTMLTextAreaElement>) => onChange(event.target.value)}
        className="w-full rounded-ask-sm border border-ask-border bg-ask-panel px-3 py-2 text-ask-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ask-accent aria-[invalid=true]:border-ask-critical"
      />
      <FieldErrors id={errorId} errors={errors} fields={allFields} />
    </label>
  );
}

export function FacilityDecisionSessionPage({ mode }: { mode: FacilityDecisionUiMode }) {
  const [session, setSession] = useState(() => createFacilityDecisionSession(facilityArrivalContext, mode));
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, FacilityDecisionValue>>({});
  const [validation, setValidation] = useState<FacilityDecisionValidationResult | null>(null);
  const [message, setMessage] = useState('Begin by receiving the casualty and reconciling the field report.');
  const submissionOrdinal = useRef(1);
  const formHeading = useRef<HTMLHeadingElement | null>(null);
  const errorSummary = useRef<HTMLDivElement | null>(null);
  const priorWorldEventIds = useRef<Set<string>>(new Set());
  const priorResultIds = useRef<Set<string>>(new Set());
  const view = useMemo(() => buildFacilityDecisionView(session, context), [session]);
  const selectedAction = selectedDecisionId
    ? view.actions.find((candidate) => candidate.decision_id === selectedDecisionId) ?? null
    : null;
  const copy = MODE_COPY[mode];
  const activeOrders = view.orders.filter((order) => order.status === 'in_progress' || order.status === 'completed_pending_release').length;
  const queuedOrders = view.orders.filter((order) => order.status === 'queued').length;
  const enabledActions = view.actions.filter((action) => action.enabled).length;
  const completedCount = view.completed_decision_count;
  const instructorTimeline = view.instructor?.decision_timeline ?? [];

  useEffect(() => {
    if (selectedDecisionId) formHeading.current?.focus();
  }, [selectedDecisionId]);

  useEffect(() => {
    const newEvents = view.visible_world_events.filter((event) => !priorWorldEventIds.current.has(event.event_id));
    const newResults = view.results.filter((result) => !priorResultIds.current.has(result.result_id));
    priorWorldEventIds.current = new Set(view.visible_world_events.map((event) => event.event_id));
    priorResultIds.current = new Set(view.results.map((result) => result.result_id));
    if (newEvents.length > 0 || newResults.length > 0) {
      const updates = [
        ...newEvents.map((event) => `Operational update: ${formatIdentifier(event.event_id)}.`),
        ...newResults.map((result) => `New source-limited result: ${formatIdentifier(result.order_code)}.`),
      ];
      setMessage(updates.join(' '));
    }
  }, [view.results, view.visible_world_events]);

  function announce(next: string): void {
    setMessage(next);
  }

  function reset(): void {
    setSession(createFacilityDecisionSession(facilityArrivalContext, mode));
    setSelectedDecisionId(null);
    setDraft({});
    setValidation(null);
    submissionOrdinal.current = 1;
    priorWorldEventIds.current = new Set();
    priorResultIds.current = new Set();
    announce('Scenario reset. The role-specific projection remains unchanged.');
  }

  function chooseDecision(decisionId: string): void {
    const next = view.actions.find((candidate) => candidate.decision_id === decisionId);
    if (!next) return;
    if (!next.enabled) {
      const detail = next.disabled_reasons?.length
        ? `Unavailable: ${next.disabled_reasons.map(formatIdentifier).join(' · ')}.`
        : 'This decision is not available at this point. Continue with another available decision.';
      announce(detail);
      return;
    }
    setSelectedDecisionId(decisionId);
    setDraft(valuesFor(next));
    setValidation(null);
    setMessage(`Complete the structured submission for ${next.label}.`);
  }

  function submit(): void {
    if (!selectedAction) return;
    const submission = {
      submission_id: facilityDecisionSubmissionId(selectedAction.decision_id, submissionOrdinal.current),
      decision_id: selectedAction.decision_id,
      expected_revision: session.revision,
      values: draft,
    };
    const result = validateFacilityDecisionSubmission(submission, context.profile);
    if (!result.valid) {
      setValidation(result);
      setMessage('The decision was not recorded. Review the highlighted fields and try again.');
      window.requestAnimationFrame(() => errorSummary.current?.focus());
      return;
    }
    try {
      const next = applyFacilityDecisionSubmission(session, submission, context);
      submissionOrdinal.current += 1;
      setSession(next);
      setSelectedDecisionId(null);
      setDraft({});
      setValidation(null);
      announce(`${selectedAction.label} recorded at ${formatTime(next.facility_session.final_state.elapsed_seconds)}.`);
    } catch (error) {
      setValidation(null);
      announce(error instanceof Error ? error.message : 'Decision submission failed.');
    }
  }

  function loadSequence(sequence: readonly string[], label: string): void {
    setSession(runSequence(sequence, mode));
    setSelectedDecisionId(null);
    setDraft({});
    setValidation(null);
    announce(label);
  }

  return (
    <PageShell>
      <main id="main-content" className="mx-auto w-full max-w-7xl px-4 py-6 md:px-6">
        <div className="mb-5">
          <Link to="/examples/facility-decision" className="text-sm text-ask-accent underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ask-accent">Decision-integrity overview</Link>
          <p className="mt-4 text-xs font-semibold uppercase tracking-[0.22em] text-ask-accent">RC3.6A · {copy.label}</p>
          <h1 className="mt-2 font-display text-3xl font-bold text-ask-text">Facility decision realism without invented treatment</h1>
          <p className="mt-3 max-w-4xl text-sm leading-relaxed text-ask-text-dim">{copy.description}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge variant="accent">Source: ASK-D-001</Badge>
            <Badge variant="caution">Concrete treatment activation blocked</Badge>
            <Badge variant="muted">Operational timing not calibrated</Badge>
            <Badge variant={view.terminal_status === 'completed' ? 'success' : view.terminal_status === 'active' ? 'default' : 'critical'}>{view.terminal_status}</Badge>
          </div>
        </div>

        <Card className="mb-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-display text-lg font-semibold text-ask-text">Fixed role projection</h2>
              <p className="mt-1 text-sm text-ask-muted">This route cannot switch into another role. Use the overview page to open a different projection.</p>
            </div>
            <Button type="button" size="sm" onClick={reset}>Reset</Button>
          </div>
          {view.demo && (
            <div className="mt-4 flex flex-wrap gap-2 border-t border-ask-border pt-4" aria-label="Stakeholder demonstration controls">
              <Button type="button" size="sm" onClick={() => loadSequence(FACILITY_DECISION_CANONICAL_SEQUENCE, 'Loaded the reviewed canonical structured decision sequence.')}>Canonical replay</Button>
              <Button type="button" size="sm" variant="secondary" onClick={() => loadSequence(FACILITY_DECISION_ALTERNATE_SEQUENCE, 'Loaded an alternate valid action ordering.')}>Alternate valid ordering</Button>
              <Button type="button" size="sm" variant="secondary" onClick={() => { setSession(runHighRisk('discharge_without_workup')); announce('Loaded the source-defined discharge failure branch.'); }}>Discharge branch</Button>
              <Button type="button" size="sm" variant="secondary" onClick={() => { setSession(runHighRisk('remove_tourniquet')); announce('Loaded the source-defined tourniquet-change failure branch.'); }}>Tourniquet branch</Button>
            </div>
          )}
        </Card>

        <div role="status" aria-live="polite" aria-atomic="true" className="mb-5 rounded-ask-sm border border-ask-border bg-ask-panel-muted px-4 py-3 text-sm text-ask-text-dim">
          {message}
        </div>

        <Card variant="muted" className="mb-5" as="section" aria-label="Scenario state dashboard">
          <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-6">
            <div><dt className="text-xs uppercase tracking-wide text-ask-muted">Phase</dt><dd className="mt-1 font-medium text-ask-text">{formatIdentifier(view.phase)}</dd></div>
            <div><dt className="text-xs uppercase tracking-wide text-ask-muted">Elapsed</dt><dd className="mt-1 font-medium text-ask-text">{formatTime(view.elapsed_seconds)}</dd></div>
            <div><dt className="text-xs uppercase tracking-wide text-ask-muted">Recorded</dt><dd className="mt-1 font-medium text-ask-text">{completedCount} decisions</dd></div>
            <div><dt className="text-xs uppercase tracking-wide text-ask-muted">Available now</dt><dd className="mt-1 font-medium text-ask-text">{enabledActions} choices</dd></div>
            <div><dt className="text-xs uppercase tracking-wide text-ask-muted">Orders</dt><dd className="mt-1 font-medium text-ask-text">{activeOrders} active · {queuedOrders} queued</dd></div>
            <div><dt className="text-xs uppercase tracking-wide text-ask-muted">Reassessment</dt><dd className="mt-1 font-medium text-ask-text">{view.information_state.reassessment_due ? 'Due' : 'Current'}</dd></div>
          </dl>
        </Card>

        <div className="grid gap-5 lg:grid-cols-[1.08fr_0.92fr]">
          <div className="space-y-5">
            <Card variant="accent">
              <h2 className="font-display text-lg font-semibold text-ask-text">Receiving brief</h2>
              <p className="mt-2 text-sm leading-relaxed text-ask-text-dim">{view.initial_patient_snapshot.presentation}</p>
              <div className="mt-4 grid grid-cols-2 gap-2 text-sm md:grid-cols-4" aria-label="Initial observations">
                <span>HR {view.initial_patient_snapshot.vitals.hr}</span>
                <span>BP {view.initial_patient_snapshot.vitals.bp_systolic}/{view.initial_patient_snapshot.vitals.bp_diastolic}</span>
                <span>RR {view.initial_patient_snapshot.vitals.rr}</span>
                <span>SpO₂ {view.initial_patient_snapshot.vitals.spo2}%</span>
              </div>
            </Card>

            <Card>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="font-display text-lg font-semibold text-ask-text">Structured decisions</h2>
                  <p className="mt-1 text-sm text-ask-muted">Missing information fails closed. Unavailable choices remain keyboard-discoverable without exposing restricted answer data.</p>
                </div>
                <span className="text-sm text-ask-muted" aria-label={`Elapsed time ${formatTime(view.elapsed_seconds)}`}>{formatTime(view.elapsed_seconds)}</span>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-2" aria-label="Decision choices">
                {view.actions.map((action) => {
                  const availabilityText = action.enabled
                    ? 'Available now'
                    : action.disabled_reasons?.length
                      ? `Unavailable: ${action.disabled_reasons.map(formatIdentifier).join(' · ')}`
                      : 'Not available at this point';
                  return (
                    <Button
                      key={action.decision_id}
                      type="button"
                      variant={action.requires_deliberate_confirmation ? 'secondary' : 'primary'}
                      aria-disabled={!action.enabled}
                      aria-describedby={`decision-availability-${action.decision_id}`}
                      onClick={() => chooseDecision(action.decision_id)}
                      className="h-auto min-h-12 justify-start text-left aria-disabled:cursor-not-allowed aria-disabled:opacity-55"
                    >
                      <span className="w-full">
                        <span className="flex items-start justify-between gap-2">
                          <span className="block">{action.label}</span>
                          <span className="rounded-full border border-current/20 px-2 py-0.5 text-[0.65rem] uppercase tracking-wide opacity-75">{formatIdentifier(action.category)}</span>
                        </span>
                        <span id={`decision-availability-${action.decision_id}`} className="mt-1 block text-xs opacity-75">{availabilityText}</span>
                      </span>
                    </Button>
                  );
                })}
              </div>
            </Card>

            {selectedAction && (
              <Card variant={selectedAction.requires_deliberate_confirmation ? 'critical' : 'default'}>
                <h2 id="decision-form-heading" ref={formHeading} tabIndex={-1} className="font-display text-lg font-semibold text-ask-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ask-accent">{selectedAction.label}</h2>
                <p id="decision-form-help" className="mt-1 text-sm text-ask-muted">Required fields are validated by the source-bound decision contract before the action is recorded.</p>
                {selectedAction.requires_deliberate_confirmation && (
                  <div role="note" aria-label="Deliberate confirmation required" className="mt-4 rounded-ask-sm border border-ask-critical/45 bg-ask-critical/10 p-3 text-sm text-ask-text-dim">
                    This source-defined consequence branch is not a recommendation. It requires explicit confirmation and a written rationale before the simulator will record it.
                  </div>
                )}
                {validation && !validation.valid && (
                  <div
                    ref={errorSummary}
                    role="alert"
                    aria-live="assertive"
                    tabIndex={-1}
                    className="mt-4 rounded-ask-sm border border-ask-critical bg-ask-critical/10 p-3 text-sm text-ask-text-dim focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ask-critical"
                  >
                    <p className="font-semibold text-ask-text">Review {validation.errors.length} submission issue{validation.errors.length === 1 ? '' : 's'}.</p>
                    <ul className="mt-2 list-disc space-y-1 pl-5">
                      {validation.errors.map((error) => {
                        const fieldId = fieldIdFromValidationError(error);
                        return (
                          <li key={error}>
                            {fieldId
                              ? <a className="underline underline-offset-2" href={`#decision-field-${fieldId}`}>{validationErrorCopy(error, selectedAction.fields)}</a>
                              : validationErrorCopy(error, selectedAction.fields)}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
                <form
                  aria-labelledby="decision-form-heading"
                  aria-describedby="decision-form-help"
                  noValidate
                  onSubmit={(event: FormEvent<HTMLFormElement>) => {
                    event.preventDefault();
                    submit();
                  }}
                  className="mt-4 space-y-4"
                >
                  {selectedAction.fields.map((field) => (
                    <FieldEditor
                      key={field.field_id}
                      field={field}
                      value={draft[field.field_id] ?? initialValue(field)}
                      errors={errorsForField(validation, field.field_id)}
                      allFields={selectedAction.fields}
                      onChange={(value) => {
                        setDraft((current) => ({ ...current, [field.field_id]: value }));
                        setValidation(null);
                      }}
                    />
                  ))}
                  <div className="mt-5 flex flex-wrap gap-2">
                    <Button type="submit">{selectedAction.requires_deliberate_confirmation ? 'Confirm and submit deliberate branch' : 'Submit decision'}</Button>
                    <Button type="button" variant="secondary" onClick={() => { setSelectedDecisionId(null); setDraft({}); setValidation(null); announce('Decision form cancelled.'); }}>Cancel</Button>
                  </div>
                </form>
              </Card>
            )}
          </div>

          <div className="space-y-5 lg:sticky lg:top-4 lg:self-start">
            <Card variant="muted">
              <h2 className="font-display text-lg font-semibold text-ask-text">Orders and source-limited results</h2>
              <div className="mt-3 space-y-3 text-sm">
                {view.orders.length === 0 && <p className="text-ask-muted">No structured diagnostic order has been recorded.</p>}
                {view.orders.map((order) => (
                  <div key={`${order.order_code}-${order.placed_at_seconds}`} className="rounded-ask-sm border border-ask-border p-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-medium text-ask-text">{formatIdentifier(order.order_code)}</p>
                      <Badge variant={order.status === 'result_available' ? 'success' : order.status === 'queued' ? 'caution' : 'muted'}>{formatIdentifier(order.status)}</Badge>
                    </div>
                    <dl className="mt-2 grid grid-cols-3 gap-2 text-xs text-ask-muted">
                      <div><dt>Placed</dt><dd className="text-ask-text-dim">{formatTime(order.placed_at_seconds)}</dd></div>
                      <div><dt>Started</dt><dd className="text-ask-text-dim">{formatTime(order.started_at_seconds)}</dd></div>
                      <div><dt>Due</dt><dd className="text-ask-text-dim">{formatTime(order.due_at_seconds)}</dd></div>
                    </dl>
                  </div>
                ))}
                {view.results.map((result) => (
                  <div key={result.result_id} className="rounded-ask-sm border border-ask-accent/40 bg-ask-accent/5 p-3">
                    <p className="font-medium text-ask-text">{result.learner_result}</p>
                    <p className="mt-1 text-xs text-ask-muted">Available at {formatTime(result.available_at_seconds)} · {result.limitation}</p>
                  </div>
                ))}
              </div>
            </Card>

            <Card>
              <h2 className="font-display text-lg font-semibold text-ask-text">Operational and information state</h2>
              <p className="mt-2 text-sm text-ask-text-dim">World events are scheduled by elapsed time, not by an unrelated diagnostic choice.</p>
              <ul className="mt-3 space-y-2 text-sm text-ask-text-dim">
                {view.visible_world_events.length === 0
                  ? <li>No scheduled surge event is currently visible.</li>
                  : view.visible_world_events.map((event) => <li key={event.event_id}><strong>{formatIdentifier(event.event_id)}</strong> at {formatTime(event.visible_at_seconds)}. {event.note}</li>)}
              </ul>
              <p className="mt-3 text-sm text-ask-text-dim">Information staleness: {view.information_state.staleness_seconds}s · reassessment {view.information_state.reassessment_due ? 'due' : 'not due'}</p>
              <ul className="mt-3 space-y-1 text-xs text-ask-muted" aria-label="Resource workload">
                {view.resources.map((resource) => <li key={resource.resource_id}>{formatIdentifier(resource.resource_id)}: {resource.active_order_count} active, {resource.queued_order_count} queued</li>)}
              </ul>
            </Card>

            <Card>
              <h2 className="font-display text-lg font-semibold text-ask-text">Closed-loop handoff state</h2>
              <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                <dt className="text-ask-muted">Receiver acknowledged</dt><dd>{String(view.handoff_status.receiver_acknowledged)}</dd>
                <dt className="text-ask-muted">Questions offered</dt><dd>{String(view.handoff_status.questions_offered)}</dd>
                <dt className="text-ask-muted">Sender confirmed</dt><dd>{String(view.handoff_status.sender_confirmed)}</dd>
                <dt className="text-ask-muted">Responsibility transferred</dt><dd>{String(view.handoff_status.responsibility_transferred)}</dd>
              </dl>
            </Card>

            {view.instructor && (
              <Card variant="accent">
                <h2 className="font-display text-lg font-semibold text-ask-text">Instructor assurance view</h2>
                <p className="mt-2 text-sm text-ask-text-dim">Source score: {(view.instructor.normalized_source_score_bps / 100).toFixed(2)}%</p>
                <p className="mt-2 break-all text-xs text-ask-muted">Registry root: {view.instructor.source_binding.content_registry_merkle_root}</p>
                <p className="mt-2 text-xs text-ask-muted">WIT observations: {view.instructor.wit_observations.length}</p>
                <h3 className="mt-4 text-sm font-semibold text-ask-text">Decision timeline</h3>
                {instructorTimeline.length === 0
                  ? <p className="mt-2 text-xs text-ask-muted">No decisions recorded.</p>
                  : (
                    <ol className="mt-2 space-y-2 text-xs text-ask-text-dim">
                      {instructorTimeline.map((record) => (
                        <li key={record.record_id} className="rounded-ask-sm border border-ask-border/70 p-2">
                          <span className="font-medium text-ask-text">{record.sequence}. {formatIdentifier(record.decision_id)}</span>
                          <span className="ml-2 text-ask-muted">{formatTime(record.started_at_seconds)}–{formatTime(record.completed_at_seconds)}</span>
                        </li>
                      ))}
                    </ol>
                  )}
              </Card>
            )}

            {view.terminal_summary && (
              <Card variant={view.terminal_status === 'completed' ? 'accent' : 'critical'}>
                <h2 className="font-display text-lg font-semibold text-ask-text">Post-run multidimensional review</h2>
                <p className="mt-2 text-sm text-ask-text-dim">These exercise-policy dimensions are not a substitute for clinical validity.</p>
                <p className="mt-3 text-sm text-ask-text-dim">Recorded decisions: {view.terminal_summary.completed_decisions.map(formatIdentifier).join(', ') || 'none'}.</p>
                <ul className="mt-3 space-y-2 text-sm text-ask-text-dim">
                  {view.terminal_summary.dimensions.map((dimension) => (
                    <li key={dimension.dimension_id} className="rounded-ask-sm border border-ask-border p-2">
                      <span className="font-medium text-ask-text">{formatIdentifier(dimension.dimension_id)}</span>: {dimension.completed_decision_ids.length} recorded decision(s)
                      {dimension.safety_events.length > 0 && <span className="block text-xs text-ask-critical">Safety events: {dimension.safety_events.map(formatIdentifier).join(', ')}</span>}
                      <span className="block text-xs text-ask-muted">Calibration: {dimension.calibration_status}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>
        </div>
      </main>
      <AppFooter />
    </PageShell>
  );
}

export function FacilityDecisionLearnerPage() {
  return <FacilityDecisionSessionPage mode="learner_assessment" />;
}

export function FacilityDecisionTeachingPage() {
  return <FacilityDecisionSessionPage mode="learner_teaching" />;
}

export function FacilityDecisionInstructorPage() {
  return <FacilityDecisionSessionPage mode="instructor" />;
}

export function FacilityDecisionDemoPage() {
  return <FacilityDecisionSessionPage mode="stakeholder_demo" />;
}
