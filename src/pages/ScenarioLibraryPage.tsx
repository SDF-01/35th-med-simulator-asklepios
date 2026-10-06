import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { AppFooter, PageShell } from '@/components/ui/PageShell';

interface ScenarioCatalogEntry {
  catalog_entry_id: string;
  title: string;
  plain_language_summary: string;
  topic_id: string;
  operational_behavior_profile_id: string;
  profile_label: string;
  context: {
    location: string;
    weather: string;
    visibility: string;
    communications: string;
    resources: string;
    resource_event: string;
  };
  learning_focus: string[];
  reproducibility: {
    package_sha256: string;
    context_signature_sha256: string;
    policy_signature_sha256: string;
    equivalence_class_id: string;
  };
  authority: {
    healthcare_simulation: string;
    direct_patient_care: string;
    clinical_decision_support: string;
    operational_timing: string;
    scoring_state: string;
    treatment_state: string;
  };
}

interface ScenarioScoreDimension {
  dimension_id: string;
  status: string;
  plain_language_finding: string;
  psychometric_validity: string;
}

interface ReferenceScorecard {
  operational_behavior_profile_id: string;
  overall_status: string;
  safety_gate: string;
  source_conformance_score_bps: number | null;
  validity_boundary: string;
  timing_score_effect: string;
  dimensions: ScenarioScoreDimension[];
}

interface TreatmentEntry {
  treatment_id: string;
  display_name: string;
  current_state: string;
  simulation_admitted: boolean;
  missing_requirements: string[];
}

interface CapabilityEntry {
  capability_id: string;
  plain_language_name: string;
  stakeholders: string[];
  user_problem: string;
  evidence_level: string;
  limitations: string[];
}

interface StakeholderDashboard {
  dashboard_id: string;
  dashboard_root_sha256: string;
  scenario_pack: {
    catalog_id: string;
    entry_count: number;
    entries: ScenarioCatalogEntry[];
    profile_counts: Record<string, number>;
  };
  stakeholder_capability_map: {
    capabilities: CapabilityEntry[];
  };
  reference_scorecards: ReferenceScorecard[];
  treatment_admission: {
    admitted_treatment_count: number;
    entries: TreatmentEntry[];
  };
  scenario_science_readiness: {
    current_operational_timing: string;
    current_scoring_state: string;
    telemetry_profile: string;
  };
  truth_boundaries: {
    healthcare_simulation: string;
    direct_patient_care: string;
    clinical_decision_support: string;
    operational_timing: string;
    scoring_validity: string;
    concrete_treatments_admitted: number;
  };
}

function label(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function shortHash(value: string): string {
  return `${value.slice(0, 10)}…${value.slice(-8)}`;
}

const PROFILE_ORDER = [
  'DIRECT_HANDOFF_BASELINE',
  'COMMUNICATION_RELAY_REQUIRED',
  'RESOURCE_COORDINATION_REQUIRED',
  'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
];

export function ScenarioLibraryPage() {
  const [dashboard, setDashboard] = useState<StakeholderDashboard | null>(null);
  const [error, setError] = useState('');
  const [profile, setProfile] = useState('ALL');

  useEffect(() => {
    let active = true;
    fetch('/data/scenario_library/stakeholder-dashboard.json', { cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Scenario library could not be loaded (${response.status}).`);
        return response.json() as Promise<StakeholderDashboard>;
      })
      .then((value) => {
        if (active) setDashboard(value);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => { active = false; };
  }, []);

  const scenarios = useMemo(() => {
    const all = dashboard?.scenario_pack.entries ?? [];
    return profile === 'ALL' ? all : all.filter((item) => item.operational_behavior_profile_id === profile);
  }, [dashboard, profile]);

  return (
    <PageShell>
      <main id="main-content" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-8">
        <PageHeader
          eyebrow="RC3.8 stakeholder product surface"
          title="Scenario library and evidence dashboard"
          description="Choose a reproducible operational training scenario, understand what behavior it changes, and see the current scoring, treatment, timing, and evidence limits in plain language."
          actions={<Link className="rounded-ask-sm border border-ask-border px-4 py-2 text-sm font-semibold text-ask-text" to="/home">Back home</Link>}
        />

        <Alert variant="caution" title="Simulation-only boundary" className="mb-4">
          Healthcare simulation is permitted within the validated scope. Direct patient care and clinical decision support remain prohibited. Operational timing is not calibrated.
        </Alert>

        {error && <Alert role="alert" variant="critical" title="Scenario library unavailable" className="mb-4">{error}</Alert>}

        {!dashboard && !error && <Card variant="muted"><p>Loading the authenticated scenario catalog…</p></Card>}

        {dashboard && (
          <div className="space-y-6">
            <section aria-labelledby="scenario-pack-heading">
              <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                <div>
                  <h2 id="scenario-pack-heading" className="font-display text-2xl font-semibold text-ask-text">Twelve-scenario operational pack</h2>
                  <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ask-text-dim">
                    The catalog contains three scenarios from each verified behavior profile. Names, weather, and seeds alone do not count as new behavior.
                  </p>
                </div>
                <label className="text-sm font-semibold text-ask-text-dim" htmlFor="behavior-profile-filter">
                  Behavior profile
                  <select
                    id="behavior-profile-filter"
                    className="ml-2 rounded-ask-sm border border-ask-border bg-ask-surface px-3 py-2 text-ask-text"
                    value={profile}
                    onChange={(event) => setProfile(event.target.value)}
                  >
                    <option value="ALL">All profiles</option>
                    {PROFILE_ORDER.map((item) => <option key={item} value={item}>{label(item)}</option>)}
                  </select>
                </label>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {scenarios.map((scenario) => (
                  <Card key={scenario.catalog_entry_id}>
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <h3 className="font-display text-lg font-semibold text-ask-text">{scenario.title}</h3>
                      <Badge variant="accent">{scenario.profile_label}</Badge>
                    </div>
                    <p className="mt-3 text-sm leading-relaxed text-ask-text-dim">{scenario.plain_language_summary}</p>
                    <dl className="mt-4 grid grid-cols-2 gap-2 text-xs">
                      <div><dt className="text-ask-muted">Topic</dt><dd>{label(scenario.topic_id)}</dd></div>
                      <div><dt className="text-ask-muted">Visibility</dt><dd>{label(scenario.context.visibility)}</dd></div>
                      <div><dt className="text-ask-muted">Communications</dt><dd>{label(scenario.context.communications)}</dd></div>
                      <div><dt className="text-ask-muted">Resources</dt><dd>{label(scenario.context.resources)}</dd></div>
                    </dl>
                    <h4 className="mt-4 text-sm font-semibold text-ask-text">Learning focus</h4>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ask-text-dim">
                      {scenario.learning_focus.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                    <div className="mt-4 rounded-ask-sm border border-ask-border bg-ask-bg/40 p-3 text-xs text-ask-muted">
                      <p>Reproducibility: <code>{shortHash(scenario.reproducibility.package_sha256)}</code></p>
                      <p className="mt-1">Policy class: <code>{scenario.reproducibility.equivalence_class_id}</code></p>
                    </div>
                  </Card>
                ))}
              </div>
            </section>

            <section aria-labelledby="scorecard-heading">
              <h2 id="scorecard-heading" className="font-display text-2xl font-semibold text-ask-text">Source-conformance scorecard</h2>
              <p className="mt-2 max-w-4xl text-sm leading-relaxed text-ask-text-dim">
                This scorecard explains observable completion evidence. It is not a validated proficiency measure, and uncalibrated timing cannot change the score.
              </p>
              <div className="mt-4 grid gap-4 xl:grid-cols-2">
                {dashboard.reference_scorecards.map((scorecard) => (
                  <Card key={scorecard.operational_behavior_profile_id} variant="accent">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="font-display text-lg font-semibold">{label(scorecard.operational_behavior_profile_id)}</h3>
                      <Badge variant={scorecard.safety_gate === 'PASS' ? 'accent' : 'critical'}>Safety {scorecard.safety_gate}</Badge>
                    </div>
                    <p className="mt-2 text-sm text-ask-text-dim">Reference source-conformance score: {scorecard.source_conformance_score_bps === null ? 'Insufficient evidence' : `${scorecard.source_conformance_score_bps / 100}%`}</p>
                    <ul className="mt-4 space-y-2">
                      {scorecard.dimensions.map((dimension) => (
                        <li key={dimension.dimension_id} className="rounded-ask-sm border border-ask-border p-3">
                          <div className="flex items-start justify-between gap-3">
                            <span className="font-semibold text-ask-text">{label(dimension.dimension_id)}</span>
                            <Badge variant={dimension.status === 'SATISFIED' ? 'accent' : 'muted'}>{label(dimension.status)}</Badge>
                          </div>
                          <p className="mt-1 text-xs leading-relaxed text-ask-text-dim">{dimension.plain_language_finding}</p>
                        </li>
                      ))}
                    </ul>
                  </Card>
                ))}
              </div>
            </section>

            <section aria-labelledby="treatment-heading">
              <h2 id="treatment-heading" className="font-display text-2xl font-semibold text-ask-text">Treatment admission</h2>
              <p className="mt-2 max-w-4xl text-sm leading-relaxed text-ask-text-dim">
                No concrete treatment is simulation-admitted. A treatment concept remains inactive until its source, evidence span, applicability, role, contraindication, simulated effect, and independent review are complete.
              </p>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                {dashboard.treatment_admission.entries.map((entry) => (
                  <Card key={entry.treatment_id}>
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="font-display text-lg font-semibold text-ask-text">{entry.display_name}</h3>
                      <Badge variant={entry.simulation_admitted ? 'accent' : 'caution'}>{label(entry.current_state)}</Badge>
                    </div>
                    <p className="mt-3 text-sm text-ask-text-dim">
                      {entry.simulation_admitted ? 'Admitted for the declared simulation scope.' : `${entry.missing_requirements.length} admission requirements remain.`}
                    </p>
                    {!entry.simulation_admitted && (
                      <details className="mt-3 text-sm text-ask-text-dim">
                        <summary className="cursor-pointer font-semibold text-ask-text">Show remaining requirements</summary>
                        <ul className="mt-2 list-disc space-y-1 pl-5">
                          {entry.missing_requirements.map((item) => <li key={item}>{label(item)}</li>)}
                        </ul>
                      </details>
                    )}
                  </Card>
                ))}
              </div>
            </section>

            <section aria-labelledby="capability-heading">
              <h2 id="capability-heading" className="font-display text-2xl font-semibold text-ask-text">Stakeholder capability map</h2>
              <p className="mt-2 max-w-4xl text-sm leading-relaxed text-ask-text-dim">
                Every major capability must identify who uses it, where it appears, what problem it solves, what evidence supports it, and what limitation remains. Orphan features are not admitted.
              </p>
              <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {dashboard.stakeholder_capability_map.capabilities.map((capability) => (
                  <Card key={capability.capability_id} variant="muted">
                    <h3 className="font-display text-lg font-semibold text-ask-text">{capability.plain_language_name}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-ask-text-dim">{capability.user_problem}</p>
                    <div className="mt-3 flex flex-wrap gap-1">
                      {capability.stakeholders.map((stakeholder) => <Badge key={stakeholder} variant="muted">{label(stakeholder)}</Badge>)}
                    </div>
                    <p className="mt-3 text-xs text-ask-muted">Evidence: {label(capability.evidence_level)}</p>
                    <p className="mt-2 text-xs leading-relaxed text-ask-muted">Limit: {capability.limitations.join(' ')}</p>
                  </Card>
                ))}
              </div>
            </section>

            <Card variant="accent">
              <h2 className="font-display text-xl font-semibold text-ask-text">Scenario science readiness</h2>
              <dl className="mt-4 grid gap-3 text-sm md:grid-cols-3">
                <div><dt className="text-ask-muted">Telemetry</dt><dd className="mt-1 font-semibold">Hash-chained and privacy bounded</dd></div>
                <div><dt className="text-ask-muted">Timing</dt><dd className="mt-1 font-semibold">{label(dashboard.scenario_science_readiness.current_operational_timing)}</dd></div>
                <div><dt className="text-ask-muted">Scoring</dt><dd className="mt-1 font-semibold">{label(dashboard.scenario_science_readiness.current_scoring_state)}</dd></div>
              </dl>
              <p className="mt-4 text-xs text-ask-muted">Dashboard identity: <code>{shortHash(dashboard.dashboard_root_sha256)}</code></p>
            </Card>
          </div>
        )}
      </main>
      <AppFooter />
    </PageShell>
  );
}
