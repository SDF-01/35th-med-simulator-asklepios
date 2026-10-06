import { useNavigate } from 'react-router-dom';
import { AppChrome } from '@/components/ui/AppChrome';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { PageHeader, SectionLabel } from '@/components/ui/PageHeader';
import { PageShell } from '@/components/ui/PageShell';
import { useSimulationStore } from '@/store/simulationStore';
import { isSoloMode } from '@/utils/soloMode';

export function AARPage() {
  const navigate = useNavigate();
  const aar = useSimulationStore((s) => s.aar);
  const solo = isSoloMode();

  if (!aar) {
    return (
      <PageShell>
        <AppChrome role="provider" title="After action review" />
        <main id="main-content" className="flex flex-1 items-center justify-center px-4 py-12">
          <Alert title="No review">No after-action review available.</Alert>
        </main>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <AppChrome role="provider" title="After action review" />
      <div className="mx-auto w-full max-w-4xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <main id="main-content" className="pb-8">
          <PageHeader
            eyebrow="After Action Review"
            title="Performance Summary"
            actions={
              <>
                <Button onClick={() => navigate(solo ? '/solo' : '/provider')}>
                  {solo ? 'Solo practice' : 'Return to Lobby'}
                </Button>
                {!solo && (
                  <Button variant="secondary" onClick={() => navigate('/wit')}>
                    WIT Command
                  </Button>
                )}
                {solo && (
                  <Button variant="secondary" onClick={() => navigate('/home')}>
                    Home
                  </Button>
                )}
              </>
            }
            className="mb-8"
          />

          <Card padding="lg" className="mb-6">
            <p className="mb-5 text-sm leading-relaxed">{aar.bluf}</p>
            <dl className="flex flex-wrap gap-6 text-sm">
              <div>
                <dt className="text-xs uppercase text-ask-muted">Score</dt>
                <dd className="font-mono text-2xl">{aar.score}/100</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-ask-muted">Pass Threshold</dt>
                <dd className="font-mono text-2xl">{aar.pass_threshold}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-ask-muted">Result</dt>
                <dd>
                  <Badge variant={aar.passed ? 'success' : 'critical'}>
                    {aar.passed ? 'PASS' : 'NEEDS IMPROVEMENT'}
                  </Badge>
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-ask-muted">Patient Outcome</dt>
                <dd>{aar.patient_outcome}</dd>
              </div>
            </dl>
          </Card>

          <div className="mb-6 grid gap-4 md:grid-cols-2 md:gap-6">
            <Card as="section" padding="md">
              <SectionLabel accent className="mb-3">
                Sustain
              </SectionLabel>
              <ul className="list-inside list-disc space-y-1 text-sm leading-relaxed">
                {aar.strengths.length ? (
                  aar.strengths.map((s) => <li key={s}>{s}</li>)
                ) : (
                  <li className="text-ask-muted">No strengths recorded.</li>
                )}
              </ul>
            </Card>

            <Card as="section" padding="md">
              <SectionLabel className="mb-3 text-ask-caution">Improve</SectionLabel>
              <ul className="list-inside list-disc space-y-1 text-sm leading-relaxed">
                {aar.improvements.length ? (
                  aar.improvements.map((i) => <li key={i}>{i}</li>)
                ) : (
                  <li className="text-ask-muted">No improvement areas identified.</li>
                )}
              </ul>
            </Card>
          </div>

          <Card as="section" padding="md" className="mb-6">
            <SectionLabel className="mb-3">Score Breakdown</SectionLabel>
            <ul className="space-y-2">
              {aar.score_breakdown.map((row) => (
                <li key={row.category} className="flex items-center justify-between text-sm">
                  <span>{row.category}</span>
                  <span className="font-mono tabular-nums">
                    {row.points}/{row.max_points}
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          {aar.missed_critical.length > 0 && (
            <Card as="section" variant="critical" padding="md" className="mb-6">
              <SectionLabel className="mb-3 text-ask-critical">Missed Critical Actions</SectionLabel>
              <ul className="list-inside list-disc space-y-1 text-sm leading-relaxed">
                {aar.missed_critical.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </Card>
          )}

          <Card as="section" padding="md" className="mb-6">
            <SectionLabel className="mb-3">Timeline</SectionLabel>
            <ul className="space-y-2 text-sm">
              {aar.timeline.map((entry, i) => (
                <li key={`${entry.time}-${i}`} className="flex gap-4">
                  <span className="shrink-0 font-mono text-ask-muted">{entry.time}</span>
                  <span>{entry.event}</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card as="section" padding="md">
            <SectionLabel className="mb-3">Teaching Points</SectionLabel>
            <ul className="list-inside list-disc space-y-1 text-sm leading-relaxed">
              {aar.teaching_points.map((tp) => (
                <li key={tp}>{tp}</li>
              ))}
            </ul>
          </Card>
        </main>
      </div>
    </PageShell>
  );
}
