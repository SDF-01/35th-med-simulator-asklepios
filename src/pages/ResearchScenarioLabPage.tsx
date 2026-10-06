import { useEffect, useMemo, useRef, useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Alert } from '../components/ui/Alert';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Input, Select } from '../components/ui/Input';
import { PageHeader } from '../components/ui/PageHeader';
import { ScenarioScorecard } from '../components/scenario/ScenarioScorecard';
import { AppFooter, PageShell } from '../components/ui/PageShell';
import { scenariosById } from '../content/scenarios';
import { loadResearchRuntimeBridge } from '../research';
import type { ResearchRuntimeBridge } from '../research';
import { verifyScenarioPackage } from '../scenario-checker/verify';
import {
  FIELD_VARIANT_BLUEPRINT,
  buildScenarioSourceConformanceScorecard,
  buildTemplateLockedScenario,
  selectNextNode,
  validateScenarioExperience,
  validateScenarioPackage,
} from '../scenario-core';
import type {
  ScenarioExperienceReport,
  ScenarioRouteEdge,
  ScenarioSourceConformanceScorecard,
  VerifiedScenarioPackage,
} from '../scenario-core';
import type { ScenarioEvidenceTopic } from '../scenario-generation';

const TOPICS = [...FIELD_VARIANT_BLUEPRINT.allowed_topics];

const TRIGGER_LABELS: Record<ScenarioRouteEdge['trigger'], string> = {
  start: 'Begin movement',
  arrive: 'Mark arrival',
  facilitator_event: 'Inject operational constraint',
  handoff_ready: 'Proceed to handoff',
  close: 'Close the evolution',
};

function label(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

interface RouteHistoryEntry {
  node_id: string;
  edge_id?: string;
  entered_by: ScenarioRouteEdge['trigger'] | 'initial';
}

export function ResearchScenarioLabPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const autoGenerationStarted = useRef(false);
  const [bridge, setBridge] = useState<ResearchRuntimeBridge | null>(null);
  const [error, setError] = useState('');
  const [topicId, setTopicId] = useState<ScenarioEvidenceTopic>(TOPICS[0] ?? 'airway');
  const [retrieverTrack, setRetrieverTrack] = useState('');
  const [seed, setSeed] = useState(20260727);
  const [generated, setGenerated] = useState<VerifiedScenarioPackage | null>(null);
  const [experience, setExperience] = useState<ScenarioExperienceReport | null>(null);
  const [checksRun, setChecksRun] = useState(0);
  const [busy, setBusy] = useState(false);
  const [routeHistory, setRouteHistory] = useState<RouteHistoryEntry[]>([]);
  const [routeAnnouncement, setRouteAnnouncement] = useState('');

  async function generateFromInputs(
    activeBridge: ResearchRuntimeBridge,
    nextTopic: ScenarioEvidenceTopic,
    nextSeed: number,
    nextTrack: string,
  ): Promise<void> {
    setBusy(true);
    try {
      const next = buildTemplateLockedScenario(activeBridge, {
        topic_id: nextTopic,
        seed: nextSeed,
        retriever_track: nextTrack || activeBridge.retrieval_release.default_research_sandbox_retriever,
      });
      const local = validateScenarioPackage(next, activeBridge);
      if (local.status !== 'PASS') {
        throw new Error(local.issues.map((item) => `${item.path}: ${item.message}`).join(' '));
      }
      const source = scenariosById[next.build.source_scenario_id];
      if (!source) throw new Error(`Source scenario ${next.build.source_scenario_id} is missing.`);
      const independent = await verifyScenarioPackage(source, next, activeBridge);
      if (independent.status !== 'PASS') {
        throw new Error(independent.issues.map((item) => `${item.path}: ${item.message}`).join(' '));
      }
      const experienceReport = validateScenarioExperience(next);
      if (experienceReport.status !== 'PASS') {
        throw new Error(experienceReport.issues.map((item) => `${item.path}: ${item.message}`).join(' '));
      }
      const catalogRequestMatches = searchParams.has('catalog_entry')
        && searchParams.get('topic') === nextTopic
        && Number(searchParams.get('seed')) === nextSeed;
      const expectedProfile = catalogRequestMatches ? searchParams.get('expected_profile') : null;
      const actualProfile = next.route.route_id.split(':').at(-1) ?? '';
      if (expectedProfile && expectedProfile !== actualProfile) {
        throw new Error(`Catalog behavior profile differs: expected ${expectedProfile}, generated ${actualProfile}.`);
      }
      const expectedPackage = catalogRequestMatches ? searchParams.get('expected_package') : null;
      if (expectedPackage && expectedPackage !== next.certificate.package_sha256) {
        throw new Error('Catalog reproducibility hash differs from the generated scenario.');
      }
      setGenerated(next);
      setExperience(experienceReport);
      setChecksRun(local.checks_run + independent.checks_run + experienceReport.checks_run);
      setRouteHistory([{ node_id: next.route.start_node_id, entered_by: 'initial' }]);
      setRouteAnnouncement(`Verified variant ready. Current route step: ${next.route.nodes.find((node) => node.node_id === next.route.start_node_id)?.label ?? 'briefing'}.`);
      setTopicId(nextTopic);
      setSeed(nextSeed);
      setRetrieverTrack(nextTrack);
      setError('');
    } catch (reason) {
      setGenerated(null);
      setExperience(null);
      setChecksRun(0);
      setRouteHistory([]);
      setRouteAnnouncement('');
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    loadResearchRuntimeBridge()
      .then((payload) => {
        setBridge(payload);
        const firstTopic = payload.prototypes.find((item) => (
          TOPICS.includes(item.topic_id as ScenarioEvidenceTopic)
        ))?.topic_id as ScenarioEvidenceTopic | undefined;
        const requestedTopic = searchParams.get('topic') as ScenarioEvidenceTopic | null;
        const requestedSeed = Number(searchParams.get('seed'));
        const nextTopic = requestedTopic && TOPICS.includes(requestedTopic) ? requestedTopic : firstTopic ?? TOPICS[0] ?? 'airway';
        const nextSeed = Number.isSafeInteger(requestedSeed) && requestedSeed >= 0 ? requestedSeed : seed;
        const nextTrack = payload.retrieval_release.default_research_sandbox_retriever
          ?? payload.retrieval_release.candidate_retriever;
        setTopicId(nextTopic);
        setSeed(nextSeed);
        setRetrieverTrack(nextTrack);
        if ((searchParams.has('catalog_entry') || searchParams.has('topic')) && !autoGenerationStarted.current) {
          autoGenerationStarted.current = true;
          void generateFromInputs(payload, nextTopic, nextSeed, nextTrack);
        }
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
  // Catalog parameters are immutable for the lifetime of this page instance.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const tracks = useMemo(
    () => bridge ? Array.from(new Set(bridge.prototypes.map((item) => item.retriever_track))).sort() : [],
    [bridge],
  );

  const currentNodeId = routeHistory.at(-1)?.node_id ?? generated?.route.start_node_id ?? '';
  const currentNode = generated?.route.nodes.find((node) => node.node_id === currentNodeId) ?? null;
  const availableEdges = useMemo(() => (
    generated
      ? generated.route.edges
        .filter((edge) => edge.from === currentNodeId)
        .sort((left, right) => right.priority - left.priority || left.edge_id.localeCompare(right.edge_id))
      : []
  ), [currentNodeId, generated]);

  const scorecard = useMemo<ScenarioSourceConformanceScorecard | null>(() => {
    if (!generated || routeHistory.length === 0) return null;
    const profile = generated.route.route_id.split(':').at(-1);
    if (!profile) return null;
    try {
      return buildScenarioSourceConformanceScorecard(generated.route, {
        schema_version: '1.0.0',
        route_id: generated.route.route_id,
        operational_behavior_profile_id: profile as ScenarioSourceConformanceScorecard['operational_behavior_profile_id'],
        visited_node_ids: routeHistory.map((entry) => entry.node_id),
        traversed_edge_ids: routeHistory.flatMap((entry) => entry.edge_id ? [entry.edge_id] : []),
        safety_event_ids: [],
        terminal_reached: Boolean(currentNode?.terminal),
      });
    } catch {
      return null;
    }
  }, [currentNode?.terminal, generated, routeHistory]);

  async function generate(seedOverride = seed): Promise<void> {
    if (!bridge || busy) return;
    await generateFromInputs(
      bridge,
      topicId,
      seedOverride,
      retrieverTrack || bridge.retrieval_release.default_research_sandbox_retriever,
    );
  }

  function advanceRoute(trigger: ScenarioRouteEdge['trigger']): void {
    if (!generated || !currentNode || currentNode.terminal) return;
    const nextId = selectNextNode(generated.route, currentNode.node_id, trigger);
    const selectedEdge = availableEdges.find((edge) => edge.trigger === trigger && edge.to === nextId);
    if (!nextId) {
      setRouteAnnouncement(`The trigger ${TRIGGER_LABELS[trigger]} is not admitted from ${currentNode.label}.`);
      return;
    }
    const nextNode = generated.route.nodes.find((node) => node.node_id === nextId);
    if (!nextNode) {
      setRouteAnnouncement('The route failed closed because the destination step is missing.');
      return;
    }
    setRouteHistory((history) => [...history, { node_id: nextId, edge_id: selectedEdge?.edge_id, entered_by: trigger }]);
    setRouteAnnouncement(`${TRIGGER_LABELS[trigger]} accepted. Current route step: ${nextNode.label}.`);
  }

  function resetRoute(): void {
    if (!generated) return;
    setRouteHistory([{ node_id: generated.route.start_node_id, entered_by: 'initial' }]);
    const first = generated.route.nodes.find((node) => node.node_id === generated.route.start_node_id);
    setRouteAnnouncement(`Route reset to ${first?.label ?? 'the briefing'}.`);
  }

  async function generateNextVariant(): Promise<void> {
    const nextSeed = seed + 1;
    await generate(nextSeed);
  }

  return (
    <PageShell>
      <main id="main-content" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-8">
        <PageHeader
          eyebrow="Unscored research sandbox"
          title="Scenario Experience Laboratory"
          description="Create a deterministic operational variant, verify it with independent contract checks, and rehearse its bounded route without changing the inherited clinical scaffold."
          actions={<><Button variant="secondary" onClick={() => navigate('/scenario-library')}>Scenario library</Button><Button variant="ghost" onClick={() => navigate('/home')}>Home</Button></>}
        />

        <Alert variant="caution" title="Authority boundary" className="mb-4">
          This laboratory is a research and training sandbox. It does not grant patient-care authority, calibrate operational timing, or convert supporting citations into treatment rules.
        </Alert>

        {error && <Alert role="alert" variant="critical" title="Generation blocked" className="mb-4">{error}</Alert>}
        <p className="sr-only" aria-live="polite">{routeAnnouncement}</p>

        <div className="grid gap-4 xl:grid-cols-[minmax(17rem,0.75fr)_minmax(0,2.25fr)]">
          <Card as="section" variant="accent" className="self-start xl:sticky xl:top-4">
            <form
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault();
                void generate();
              }}
            >
              <h2 className="font-display text-lg font-semibold text-ask-text">Variant controls</h2>
              <p className="mt-2 text-sm leading-relaxed text-ask-text-dim">
                Topic and retrieval track change citation binding. The seed changes only reviewed operational factors.
              </p>

              <label className="mt-4 block text-sm font-medium text-ask-text-dim" htmlFor="scenario-topic">
                Evidence topic
              </label>
              <Select
                id="scenario-topic"
                className="mt-2"
                value={topicId}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => setTopicId(event.target.value as ScenarioEvidenceTopic)}
              >
                {TOPICS.map((topic) => <option key={topic} value={topic}>{label(topic)}</option>)}
              </Select>

              <label className="mt-4 block text-sm font-medium text-ask-text-dim" htmlFor="scenario-track">
                Citation retrieval track
              </label>
              <Select
                id="scenario-track"
                className="mt-2"
                value={retrieverTrack}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => setRetrieverTrack(event.target.value)}
                disabled={!bridge}
              >
                {tracks.map((track) => <option key={track} value={track}>{label(track)}</option>)}
              </Select>

              <label className="mt-4 block text-sm font-medium text-ask-text-dim" htmlFor="scenario-seed">
                Deterministic seed
              </label>
              <Input
                id="scenario-seed"
                className="mt-2"
                type="number"
                min={0}
                step={1}
                value={seed}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setSeed(Math.max(0, Number(event.target.value) || 0))}
                inputMode="numeric"
              />
              <p className="mt-2 text-xs leading-relaxed text-ask-muted">
                Reusing the same topic, track, seed, and bridge produces the same certified package.
              </p>

              <Button className="mt-5 w-full" type="submit" disabled={!bridge || busy}>
                {busy ? 'Building and checking…' : 'Build verified variant'}
              </Button>
              <Button
                className="mt-2 w-full"
                type="button"
                variant="secondary"
                onClick={() => void generateNextVariant()}
                disabled={!bridge || busy}
              >
                Build next deterministic variant
              </Button>

              <dl className="mt-5 space-y-2 border-t border-ask-border pt-4 text-xs">
                <div className="flex justify-between gap-3"><dt className="text-ask-muted">Blueprint</dt><dd className="text-right font-mono">{FIELD_VARIANT_BLUEPRINT.blueprint_id}</dd></div>
                <div className="flex justify-between gap-3"><dt className="text-ask-muted">Reviewed source</dt><dd className="font-mono">{FIELD_VARIANT_BLUEPRINT.source_scenario_id}</dd></div>
                <div className="flex justify-between gap-3"><dt className="text-ask-muted">Clinical authority</dt><dd>NOT_GRANTED</dd></div>
                <div className="flex justify-between gap-3"><dt className="text-ask-muted">Timing</dt><dd>NOT_CALIBRATED</dd></div>
                <div className="flex justify-between gap-3"><dt className="text-ask-muted">Scoring</dt><dd>Inherited unchanged</dd></div>
              </dl>
            </form>
          </Card>

          <section className="space-y-4" aria-label="Verified scenario workspace">
            {!generated && (
              <Card variant="muted">
                <h2 className="font-display text-lg font-semibold">No verified package yet</h2>
                <p className="mt-2 text-sm leading-relaxed text-ask-text-dim">
                  Choose a topic, track, and seed. Nothing is displayed or rehearsed until the local package validator, independent checker, and experience contract all accept the result.
                </p>
              </Card>
            )}

            {generated && experience && (
              <>
                <Card variant="accent">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-ask-accent">Verified package accepted</p>
                      <h2 className="mt-2 font-display text-xl font-semibold">{generated.scenario.title}</h2>
                    </div>
                    <span className="rounded-full border border-ask-accent/35 bg-ask-accent/10 px-3 py-1 text-xs font-semibold text-ask-accent">
                      {checksRun.toLocaleString()} checks
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-relaxed text-ask-text-dim">{generated.scenario.operational_context.narrative}</p>

                  <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3" aria-label="Operational context">
                    {[
                      ['Location', generated.scenario.operational_context.location_type],
                      ['Weather', generated.scenario.operational_context.weather],
                      ['Visibility', generated.scenario.operational_context.visibility],
                      ['Communications', label(generated.scenario.operational_context.comms_status)],
                      ['Resources', label(generated.scenario.operational_context.resource_status)],
                      ['Topic', label(generated.build.topic_id)],
                    ].map(([name, value]) => (
                      <div key={name} className="rounded-ask-sm border border-ask-border bg-ask-bg/50 p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-ask-muted">{name}</p>
                        <p className="mt-1 text-sm text-ask-text">{value}</p>
                      </div>
                    ))}
                  </div>
                </Card>

                <div className="grid gap-4 lg:grid-cols-2">
                  <Card>
                    <h3 className="font-display text-lg font-semibold">What changed</h3>
                    <ul className="mt-3 space-y-2 text-sm text-ask-text-dim">
                      <li>• Location, weather, visibility, communications, and resource pressure.</li>
                      <li>• One reviewed facilitator event and the citation/provenance binding.</li>
                      <li>• Scenario identity and narrative that describe those operational factors.</li>
                    </ul>
                  </Card>
                  <Card>
                    <h3 className="font-display text-lg font-semibold">What stayed locked</h3>
                    <ul className="mt-3 space-y-2 text-sm text-ask-text-dim">
                      <li>• Patients, injuries, vital signs, expected actions, and unsafe actions.</li>
                      <li>• Point values, success/failure conditions, timeout, and AAR teaching points.</li>
                      <li>• Clinical authority, scoring behavior, and patient-care prohibition.</li>
                    </ul>
                  </Card>
                </div>

                <Card as="section" aria-labelledby="route-rehearsal-heading">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 id="route-rehearsal-heading" className="font-display text-lg font-semibold">Interactive route rehearsal</h3>
                      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ask-text-dim">
                        Rehearse only the bounded operational flow. No clinical action is generated, recommended, or changed here, and the route never advances automatically.
                      </p>
                    </div>
                    <Button variant="secondary" size="sm" type="button" onClick={resetRoute}>Reset route</Button>
                  </div>

                  <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(16rem,0.85fr)]">
                    <div>
                      <div className="rounded-ask-md border border-ask-accent/30 bg-ask-accent/5 p-4">
                        <p className="text-xs font-semibold uppercase tracking-wide text-ask-accent">Current step</p>
                        <p className="mt-2 text-lg font-semibold text-ask-text">{currentNode?.label}</p>
                        <p className="mt-1 text-sm text-ask-text-dim">Step {routeHistory.length} of at most {experience.metrics.maximum_route_steps + 1}</p>
                      </div>

                      {currentNode?.terminal ? (
                        <Alert variant="success" title="Route complete" className="mt-3">
                          The operational flow reached its single terminal state. Use the inherited AAR prompts below to debrief; this completion is not a patient-care outcome claim.
                        </Alert>
                      ) : (
                        <div className="mt-3">
                          <p className="text-xs font-semibold uppercase tracking-wide text-ask-muted">Admitted next transitions</p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {availableEdges.map((edge) => (
                              <Button key={edge.edge_id} type="button" onClick={() => advanceRoute(edge.trigger)}>
                                {TRIGGER_LABELS[edge.trigger]}
                              </Button>
                            ))}
                          </div>
                          {availableEdges.length > 1 && (
                            <p className="mt-2 text-xs leading-relaxed text-ask-muted">
                              This is a real operational branch: the facilitator may introduce the reviewed pressure event, or the team may proceed to a traceable handoff when ready.
                            </p>
                          )}
                        </div>
                      )}
                    </div>

                    <ol className="space-y-2" aria-label="Route history">
                      {routeHistory.map((entry, index) => {
                        const node = generated.route.nodes.find((candidate) => candidate.node_id === entry.node_id);
                        return (
                          <li key={`${entry.node_id}-${index}`} className="rounded-ask-sm border border-ask-border p-3 text-sm">
                            <div className="flex gap-3">
                              <span className="font-mono text-xs text-ask-muted">{String(index + 1).padStart(2, '0')}</span>
                              <div>
                                <p className="font-medium text-ask-text">{node?.label ?? entry.node_id}</p>
                                <p className="mt-1 text-xs text-ask-muted">
                                  {entry.entered_by === 'initial' ? 'Starting state' : `Entered by: ${TRIGGER_LABELS[entry.entered_by]}`}
                                </p>
                              </div>
                            </div>
                          </li>
                        );
                      })}
                    </ol>
                  </div>
                </Card>

                {scorecard && <ScenarioScorecard scorecard={scorecard} />}

                <div className="grid gap-4 lg:grid-cols-2">
                  <Card>
                    <h3 className="font-display text-lg font-semibold">Prebrief and objectives</h3>
                    <p className="mt-2 text-sm leading-relaxed text-ask-text-dim">{generated.scenario.fictionalization_notice}</p>
                    <ul className="mt-3 space-y-2 text-sm text-ask-text-dim">
                      {generated.scenario.training_objectives.map((objective) => <li key={objective}>• {objective}</li>)}
                    </ul>
                  </Card>

                  <Card>
                    <h3 className="font-display text-lg font-semibold">After-action review</h3>
                    <p className="mt-2 text-sm text-ask-text-dim">Use the inherited prompts only after the route closes.</p>
                    <ol className="mt-3 space-y-2 text-sm text-ask-text-dim">
                      {generated.scenario.aar_teaching_points.map((point, index) => (
                        <li key={point}><span className="mr-2 font-mono text-xs text-ask-muted">{index + 1}.</span>{point}</li>
                      ))}
                    </ol>
                  </Card>
                </div>

                <Card>
                  <details>
                    <summary className="cursor-pointer font-display text-lg font-semibold text-ask-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ask-accent/40">
                      Verification and provenance details
                    </summary>
                    <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
                      <div><dt className="text-ask-muted">Scenario ID</dt><dd className="font-mono text-xs">{generated.scenario.scenario_id}</dd></div>
                      <div><dt className="text-ask-muted">Source template</dt><dd>{generated.build.source_scenario_id}</dd></div>
                      <div><dt className="text-ask-muted">Seed</dt><dd>{generated.build.seed}</dd></div>
                      <div><dt className="text-ask-muted">Retriever</dt><dd>{generated.build.retriever_track}</dd></div>
                      <div><dt className="text-ask-muted">Route nodes / edges</dt><dd>{experience.metrics.route_nodes} / {experience.metrics.route_edges}</dd></div>
                      <div><dt className="text-ask-muted">Evidence references</dt><dd>{experience.metrics.evidence_references}</dd></div>
                      <div className="sm:col-span-2 lg:col-span-3"><dt className="text-ask-muted">Certified package hash</dt><dd className="break-all font-mono text-[11px]">{generated.certificate.package_sha256}</dd></div>
                      <div className="sm:col-span-2 lg:col-span-3"><dt className="text-ask-muted">Protected projection hash</dt><dd className="break-all font-mono text-[11px]">{generated.certificate.output_protected_sha256}</dd></div>
                    </dl>

                    <h4 className="mt-5 font-semibold text-ask-text">Citation provenance</h4>
                    <ul className="mt-3 space-y-3">
                      {generated.evidence.map((citation) => (
                        <li key={citation.evidence_id} className="rounded-ask-sm border border-ask-border p-3 text-sm">
                          <strong>{citation.title}</strong><br />
                          <span className="text-ask-text-dim">{citation.journal} · DOI {citation.doi}</span><br />
                          <span className="text-xs text-ask-muted">{citation.locator || 'DOI-bound source record'}</span><br />
                          <span className="break-all font-mono text-[10px] text-ask-muted">{citation.evidence_id}</span>
                        </li>
                      ))}
                    </ul>
                  </details>
                </Card>
              </>
            )}
          </section>
        </div>
      </main>
      <AppFooter>Scenario experience laboratory · deterministic · citation-only · unscored · patient-care use prohibited</AppFooter>
    </PageShell>
  );
}
