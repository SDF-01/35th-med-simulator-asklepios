import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { AppFooter, PageShell } from '@/components/ui/PageShell';

const ROLE_ROUTES = [
  {
    path: '/examples/facility-decision/learner',
    label: 'Learner assessment',
    description: 'Structured decisions without live score, source points, provenance, WIT observations, answer labels, autoplay, completed replay, or branch controls.',
    badge: 'Assessment-safe projection',
  },
  {
    path: '/examples/facility-decision/teaching',
    label: 'Learner teaching',
    description: 'The learner-safe projection plus prerequisite explanations after a decision is selected. It still excludes points, provenance, evaluator state, and answer labels.',
    badge: 'Guided learning projection',
  },
  {
    path: '/examples/facility-decision/instructor',
    label: 'Instructor review',
    description: 'Source binding, multidimensional completion records, operational queues, process observations, and replay evidence for facilitated review.',
    badge: 'Privileged review projection',
  },
  {
    path: '/examples/facility-decision/demo',
    label: 'Stakeholder demonstration',
    description: 'Canonical and alternate replays plus explicit failure branches. This route demonstrates the engine and must not be used as a learner assessment.',
    badge: 'Demonstration projection',
  },
] as const;

export function FacilityDecisionIntegrityPage() {
  return (
    <PageShell>
      <main id="main-content" className="mx-auto w-full max-w-6xl px-4 py-6 md:px-6">
        <header className="mb-6">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-ask-accent">RC3.6A treatment and decision integrity</p>
          <h1 className="mt-2 font-display text-3xl font-bold text-ask-text">Choose a role-bound facility decision experience</h1>
          <p className="mt-3 max-w-4xl text-sm leading-relaxed text-ask-text-dim">
            The post-CUF/TFC receiving-clinic case now uses structured assessment, explicit diagnostic orders and results, finite resource queues, source-limited observations, blocked unsupported treatment content, and closed-loop handoff state.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge variant="accent">Source scenario ASK-D-001</Badge>
            <Badge variant="caution">Concrete treatment activation blocked</Badge>
            <Badge variant="muted">Operational parameters not calibrated</Badge>
            <Badge variant="muted">Patient-care use prohibited</Badge>
          </div>
        </header>

        <Card variant="accent" className="mb-6">
          <h2 className="font-display text-lg font-semibold text-ask-text">Role separation is a data boundary</h2>
          <p className="mt-2 text-sm leading-relaxed text-ask-text-dim">
            Each route constructs a fixed projection. There is no in-session role switch. In a networked production deployment, an authenticated server boundary must also authorize the role and withhold privileged data; client-side routing alone is not an authorization system.
          </p>
        </Card>

        <section aria-labelledby="role-options-heading">
          <h2 id="role-options-heading" className="font-display text-xl font-semibold text-ask-text">Available projections</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {ROLE_ROUTES.map((role) => (
              <Card key={role.path}>
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-display text-lg font-semibold text-ask-text">{role.label}</h3>
                  <Badge variant="muted">{role.badge}</Badge>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-ask-text-dim">{role.description}</p>
                <Link
                  to={role.path}
                  className="mt-4 inline-flex min-h-11 items-center rounded-ask-sm border border-ask-accent px-4 py-2 text-sm font-semibold text-ask-accent transition hover:bg-ask-accent/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ask-accent"
                >
                  Open {role.label.toLowerCase()}
                </Link>
              </Card>
            ))}
          </div>
        </section>

        <section aria-labelledby="validity-heading" className="mt-6">
          <Card>
            <h2 id="validity-heading" className="font-display text-lg font-semibold text-ask-text">Current validity boundary</h2>
            <ul className="mt-3 space-y-2 text-sm leading-relaxed text-ask-text-dim">
              <li>Clinical actions and points remain inherited from ASK-D-001.</li>
              <li>Concrete medication, dose, route, procedure, device setting, provider scope, and treatment-effect models remain blocked without an adjudicated governing-source contract.</li>
              <li>Diagnostic and transfer timings are deterministic exercise values marked NOT_CALIBRATED.</li>
              <li>Patient observations are source-bound; validated continuous physiology is not claimed.</li>
              <li>The AAR reconstructs the decision sequence and observed outcome; it does not claim an identified causal effect.</li>
            </ul>
            <Link
              to="/examples/facility-decision/learner"
              className="mt-4 inline-flex min-h-11 items-center rounded-ask-sm bg-ask-accent px-4 py-2 text-sm font-semibold text-ask-bg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ask-accent"
            >
              Begin learner assessment
            </Link>
          </Card>
        </section>
      </main>
      <AppFooter />
    </PageShell>
  );
}
