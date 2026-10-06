import { useEffect, useMemo, useRef, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { AppFooter, PageShell } from '@/components/ui/PageShell';
import { facilityArrivalContext } from '@/facility-arrival/context';
import {
  applyFacilityCommand,
  buildFacilityAar,
  createFacilitySession,
  evaluateFacilityAction,
  facilityCommandId,
  runCanonicalFacilitySession,
} from '@/facility-arrival/engine';
import type { FacilitySession } from '@/facility-arrival/types';

const context = facilityArrivalContext;

type ViewMode = 'learner' | 'wit' | 'provenance';

function formatTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

function runBranch(actionId: 'discharge_without_workup' | 'remove_tourniquet'): FacilitySession {
  let session = createFacilitySession(context);
  for (const next of ['receive_handoff', actionId]) {
    const result = applyFacilityCommand(session, {
      command_id: facilityCommandId(next, session.command_receipts.length + 1),
      action_id: next,
      expected_revision: session.final_state.revision,
    }, context);
    session = result.session;
  }
  return session;
}

function runTimeoutBranch(): FacilitySession {
  let session = createFacilitySession(context);
  let ordinal = 1;
  while (session.final_state.terminal_status === 'active' && ordinal < 30) {
    session = applyFacilityCommand(session, {
      command_id: facilityCommandId('wait_60', ordinal),
      action_id: 'wait_60',
      expected_revision: session.final_state.revision,
    }, context).session;
    ordinal += 1;
  }
  return session;
}

export function FacilityArrivalExamplePage() {
  const [session, setSession] = useState<FacilitySession>(() => createFacilitySession(context));
  const [view, setView] = useState<ViewMode>('learner');
  const [branchLabel, setBranchLabel] = useState('manual learner-controlled run');
  const [autoplayIndex, setAutoplayIndex] = useState<number | null>(null);
  const autoplayTimer = useRef<number | null>(null);
  const aar = useMemo(() => buildFacilityAar(session, context), [session]);
  const sourcePatient = context.scenario.patients[0];

  const enabledActions = useMemo(() => context.spec.actions.filter((action) => {
    const trace = evaluateFacilityAction(session, {
      command_id: `preview-${session.final_state.revision}-${action.action_id}`,
      action_id: action.action_id,
      expected_revision: session.final_state.revision,
    }, context);
    return trace.enabled;
  }), [session]);

  useEffect(() => () => {
    if (autoplayTimer.current !== null) window.clearTimeout(autoplayTimer.current);
  }, []);

  useEffect(() => {
    if (autoplayIndex === null) return;
    if (autoplayIndex >= context.spec.canonical_command_sequence.length) {
      setAutoplayIndex(null);
      return;
    }
    autoplayTimer.current = window.setTimeout(() => {
      const actionId = context.spec.canonical_command_sequence[autoplayIndex];
      setSession((current) => applyFacilityCommand(current, {
        command_id: `autoplay-${(autoplayIndex + 1).toString().padStart(2, '0')}-${actionId}`,
        action_id: actionId,
        expected_revision: current.final_state.revision,
      }, context).session);
      setAutoplayIndex((current) => current === null ? null : current + 1);
    }, 450);
    return () => {
      if (autoplayTimer.current !== null) window.clearTimeout(autoplayTimer.current);
    };
  }, [autoplayIndex]);

  function applyAction(actionId: string): void {
    setSession((current) => applyFacilityCommand(current, {
      command_id: facilityCommandId(actionId, current.command_receipts.length + 1),
      action_id: actionId,
      expected_revision: current.final_state.revision,
    }, context).session);
  }

  function reset(): void {
    setAutoplayIndex(null);
    setBranchLabel('manual learner-controlled run');
    setSession(createFacilitySession(context));
  }

  function startAutoplay(): void {
    setBranchLabel('timed canonical autoplay');
    setSession(createFacilitySession(context));
    setAutoplayIndex(0);
  }

  function load(label: string, next: FacilitySession): void {
    setAutoplayIndex(null);
    setBranchLabel(label);
    setSession(next);
  }

  return (
    <PageShell>
      <main id="main-content" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-6">
        <div className="mb-5">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-ask-accent">Canonical interactive example</p>
          <h1 className="mt-2 font-display text-3xl font-bold text-ask-text">Facility arrival after CUF and TFC</h1>
          <p className="mt-3 max-w-4xl text-sm leading-relaxed text-ask-text-dim">
            A deterministic post-field-care receiving simulation bound to the repository&apos;s ASK-D-001 clinic template. The learner controls the receiving sequence; system events, hidden findings, scoring, and the WIT trail are independently replayable.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge variant="accent">Source: ASK-D-001</Badge>
            <Badge variant="caution">Exercise timings not calibrated</Badge>
            <Badge variant="muted">Run: {branchLabel}</Badge>
            <Badge variant={session.final_state.terminal_status === 'completed' ? 'success' : session.final_state.terminal_status === 'active' ? 'default' : 'critical'}>
              {session.final_state.terminal_status}
            </Badge>
          </div>
        </div>

        <Card className="mb-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-display text-base font-semibold text-ask-text">Reference and alternate branches</h2>
              <p className="mt-1 text-sm text-ask-muted">Play manually, watch the canonical sequence unfold, or load a fail-closed branch.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={reset}>Reset</Button>
              <Button size="sm" variant="secondary" onClick={startAutoplay} disabled={autoplayIndex !== null}>Autoplay</Button>
              <Button size="sm" variant="secondary" onClick={() => load('complete canonical replay', runCanonicalFacilitySession(context))}>Complete replay</Button>
              <Button size="sm" variant="secondary" onClick={() => load('alternate branch · source-bound timeout', runTimeoutBranch())}>Timeout</Button>
              <Button size="sm" variant="danger" onClick={() => load('alternate branch · unsafe discharge', runBranch('discharge_without_workup'))}>Unsafe discharge</Button>
              <Button size="sm" variant="danger" onClick={() => load('alternate branch · unsafe tourniquet action', runBranch('remove_tourniquet'))}>Unsafe tourniquet</Button>
            </div>
          </div>
        </Card>

        <div className="mb-5 flex flex-wrap gap-2" role="tablist" aria-label="Facility example views">
          {(['learner', 'wit', 'provenance'] as const).map((item) => (
            <Button key={item} size="sm" variant={view === item ? 'primary' : 'secondary'} onClick={() => setView(item)} role="tab" aria-selected={view === item}>
              {item === 'wit' ? 'WIT process view' : item === 'provenance' ? 'Provenance view' : 'Learner view'}
            </Button>
          ))}
        </div>

        {view === 'learner' && (
          <div className="grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-5">
              <Card variant="accent">
                <h2 className="font-display text-lg font-semibold text-ask-text">Receiving brief</h2>
                <p className="mt-2 text-sm leading-relaxed text-ask-text-dim">{sourcePatient?.initial_presentation}</p>
                {sourcePatient && (
                  <div className="mt-4 grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
                    <span>HR {sourcePatient.initial_vitals.hr}</span>
                    <span>BP {sourcePatient.initial_vitals.bp_systolic}/{sourcePatient.initial_vitals.bp_diastolic}</span>
                    <span>RR {sourcePatient.initial_vitals.rr}</span>
                    <span>SpO₂ {sourcePatient.initial_vitals.spo2}%</span>
                  </div>
                )}
              </Card>

              <Card>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h2 className="font-display text-lg font-semibold text-ask-text">Available learner actions</h2>
                    <p className="mt-1 text-sm text-ask-muted">The reducer—not the UI—enforces revision, idempotency, prerequisites, event requirements, timeout, and completion rules.</p>
                  </div>
                  <span className="text-sm text-ask-muted">{formatTime(session.final_state.elapsed_seconds)}</span>
                </div>
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {enabledActions.length === 0 ? (
                    <p className="text-sm text-ask-muted">No action is enabled in this terminal state.</p>
                  ) : enabledActions.map((action) => (
                    <Button
                      key={action.action_id}
                      variant={action.terminal_effect === 'failed' ? 'danger' : action.origin === 'operational_workflow' ? 'secondary' : 'primary'}
                      onClick={() => applyAction(action.action_id)}
                      className="h-auto min-h-12 justify-start text-left"
                    >
                      <span>
                        <span className="block">{action.label}</span>
                        <span className="block text-xs opacity-75">{action.origin === 'operational_workflow' ? 'Operational workflow · 0 clinical points' : `Inherited source action · ${action.source_action_id}`}</span>
                      </span>
                    </Button>
                  ))}
                </div>
              </Card>

              <Card>
                <h2 className="font-display text-lg font-semibold text-ask-text">Learner-visible findings</h2>
                {session.final_state.revealed_hidden_findings.length === 0 ? (
                  <p className="mt-2 text-sm text-ask-muted">Hidden source findings remain withheld until both diagnostic orders are complete and the authenticated diagnostics-ready event fires.</p>
                ) : (
                  <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-ask-text-dim">
                    {session.final_state.revealed_hidden_findings.map((finding) => <li key={finding}>{finding}</li>)}
                  </ul>
                )}
              </Card>
            </div>

            <div className="space-y-5">
              <Card variant="muted">
                <h2 className="font-display text-lg font-semibold text-ask-text">Operational alerts</h2>
                <ul className="mt-3 space-y-2 text-sm text-ask-text-dim">
                  {session.final_state.alerts.length === 0 ? <li>No current alert.</li> : session.final_state.alerts.map((alert) => <li key={alert}>{alert}</li>)}
                </ul>
              </Card>
              <Card>
                <h2 className="font-display text-lg font-semibold text-ask-text">Event-sourced interaction timeline</h2>
                <ol className="mt-3 max-h-[34rem] space-y-3 overflow-auto pr-2 text-sm">
                  {session.transitions.map((transition) => (
                    <li key={transition.transition_id} className="border-l border-ask-border pl-3">
                      <p className="font-medium text-ask-text">{transition.label}</p>
                      <p className="text-xs text-ask-muted">#{transition.sequence} · {formatTime(transition.completed_at_seconds)} · {transition.actor_id}</p>
                    </li>
                  ))}
                </ol>
              </Card>
              {session.final_state.terminal_status !== 'active' && (
                <Card variant={aar.passed ? 'accent' : 'critical'}>
                  <h2 className="font-display text-lg font-semibold text-ask-text">After-action summary</h2>
                  <p className="mt-2 text-sm text-ask-text-dim">{session.final_state.outcome}</p>
                  <p className="mt-3 text-sm">Score: {(aar.normalized_score_bps / 100).toFixed(2)}% · {aar.passed ? 'Passed reference threshold' : 'Did not pass reference threshold'}</p>
                  <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-ask-text-dim">
                    {aar.improvement_opportunities.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </Card>
              )}
            </div>
          </div>
        )}

        {view === 'wit' && (
          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <h2 className="font-display text-lg font-semibold text-ask-text">Process observations</h2>
              <p className="mt-1 text-sm text-ask-muted">WIT output is structurally process-only and cannot create a clinical action or alter clinical score.</p>
              <ol className="mt-4 space-y-3">
                {session.transitions.map((transition) => (
                  <li key={transition.transition_id} className="rounded-ask-sm border border-ask-border p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-ask-muted">{transition.wit_observation.category}</p>
                    <p className="mt-1 text-sm text-ask-text-dim">{transition.wit_observation.statement}</p>
                  </li>
                ))}
              </ol>
            </Card>
            <Card variant="muted">
              <h2 className="font-display text-lg font-semibold text-ask-text">Actor information state</h2>
              {Object.entries(session.final_state.actor_knowledge).map(([actor, facts]) => (
                <div key={actor} className="mt-4">
                  <p className="text-sm font-medium text-ask-text">{actor}</p>
                  <p className="mt-1 text-xs text-ask-muted">{facts.length === 0 ? 'No recorded facts.' : facts.join(' · ')}</p>
                </div>
              ))}
            </Card>
          </div>
        )}

        {view === 'provenance' && (
          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <h2 className="font-display text-lg font-semibold text-ask-text">Source and registry binding</h2>
              <dl className="mt-4 space-y-3 text-sm">
                {Object.entries(session.source_binding).map(([key, value]) => (
                  <div key={key}>
                    <dt className="text-xs font-semibold uppercase tracking-wide text-ask-muted">{key}</dt>
                    <dd className="mt-1 break-all text-ask-text-dim">{Array.isArray(value) ? value.join(', ') : value}</dd>
                  </div>
                ))}
              </dl>
            </Card>
            <Card>
              <h2 className="font-display text-lg font-semibold text-ask-text">Validity boundary</h2>
              <p className="mt-2 text-sm text-ask-text-dim">This release demonstrates deterministic source binding, replay, information timing, score isolation, and fail-closed alternate branches. Exercise-design timing values are not presented as measured real-world distributions.</p>
              <h3 className="mt-4 text-sm font-semibold text-ask-text">Open obligations</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ask-text-dim">
                {aar.validity_ledger.open.map((gate) => <li key={gate}>{gate}</li>)}
              </ul>
            </Card>
          </div>
        )}
      </main>
      <AppFooter>Project Asklepios · Facility-arrival production-training reference · Patient-care use prohibited</AppFooter>
    </PageShell>
  );
}
