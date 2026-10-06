import { useNavigate } from 'react-router-dom';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { HeroBackground } from '@/components/ui/HeroBackground';
import { AppFooter, PageShell } from '@/components/ui/PageShell';

const STEPS = [
  {
    step: '1',
    title: 'Host creates the exercise',
    body: 'WIT taps Host Exercise and gets a 6-character code.',
  },
  {
    step: '2',
    title: 'Players join with the code',
    body: 'Each provider enters that code on their phone, like a game lobby.',
  },
  {
    step: '3',
    title: 'Host starts the scenario',
    body: 'When everyone is in the lobby, the host opens the WIT console and runs the evolution.',
  },
] as const;

export function LandingPage() {
  const navigate = useNavigate();

  return (
    <PageShell showTrainingBanner={false} showGrid={false} variant="hero" className="relative overflow-hidden">
      <HeroBackground />

      <main id="main-content" className="landing-main relative z-10">
        <section className="landing-hero">
          <p className="landing-hero__eyebrow">USAF Medical Readiness</p>
          <h1 className="hero-title landing-hero__title">Project Asklepios</h1>
          <p className="landing-hero__tagline">Tactical casualty care training platform</p>
          <p className="landing-hero__lead">
            Host an exercise, share a code, and run multi-device TCCC training from any browser.
          </p>
        </section>

        <section className="landing-section" aria-labelledby="lobby-heading">
          <div className="landing-section__intro">
            <h2 id="lobby-heading" className="landing-section__title">
              Exercise lobby
            </h2>
            <p className="landing-section__desc">
              Same flow as a party game: one host, everyone else joins with a code.
            </p>
          </div>

          <div className="mx-auto flex max-w-md flex-col gap-3 sm:flex-row">
            <Button type="button" className="flex-1 min-h-12" onClick={() => navigate('/solo')}>
              Solo practice
            </Button>
            <Button type="button" variant="secondary" className="flex-1 min-h-12" onClick={() => navigate('/host')}>
              Host exercise
            </Button>
          </div>
          <p className="mx-auto mt-2 max-w-md text-center text-xs text-ask-muted">
            Past practices and local AAR summaries live on the solo practice page (this device only).
          </p>
          <div className="mx-auto mt-3 max-w-md">
            <Button
              type="button"
              variant="secondary"
              className="w-full min-h-12"
              onClick={() => navigate('/join')}
            >
              Join exercise
            </Button>
          </div>
          <div className="mx-auto mt-3 max-w-md">
            <Button
              type="button"
              variant="ghost"
              className="w-full"
              onClick={() => navigate('/research-sandbox')}
            >
              Research scenario lab
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="mt-2 w-full"
              onClick={() => navigate('/scenarios')}
            >
              Scenario library and scorecard
            </Button>
          </div>
        </section>

        <section className="landing-section" aria-labelledby="how-heading">
          <div className="landing-section__intro">
            <h2 id="how-heading" className="landing-section__title">
              How it works
            </h2>
          </div>
          <div className="landing-steps">
            {STEPS.map((item) => (
              <Card key={item.step} padding="md" elevation="raised" className="landing-step">
                <span className="landing-step__number">{item.step}</span>
                <h3 className="landing-step__title">{item.title}</h3>
                <p className="landing-step__body">{item.body}</p>
              </Card>
            ))}
          </div>
        </section>

        <Alert variant="info" className="landing-hub-note" title="For providers on cell phones">
          Open the site, tap Join exercise, and type the code your WIT host gives you. No app
          install and no localhost setup.
        </Alert>

        <p className="landing-disclaimer">
          Training simulation only. Not for operational use. Follow instructor guidance and approved
          doctrine.
        </p>
      </main>

      <AppFooter className="relative z-10 border-ask-border/40 bg-ask-bg/60 backdrop-blur-sm">
        <span>
          Project Asklepios v0.3.0 ·{' '}
          <a
            href="https://github.com/swolem12/ProjectAsklepios"
            className="text-ask-accent hover:text-ask-accent-bright"
            target="_blank"
            rel="noreferrer"
          >
            GitHub
          </a>
        </span>
      </AppFooter>
    </PageShell>
  );
}
