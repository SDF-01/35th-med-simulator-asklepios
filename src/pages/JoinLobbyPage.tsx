import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { HubSetupAlert } from '@/components/ui/HubSetupAlert';
import { MobileAppShell } from '@/components/mobile/MobileAppShell';
import { CodeInput } from '@/components/mobile/CodeInput';
import { MobileHeader } from '@/components/mobile/MobileHeader';
import { PageHeader } from '@/components/ui/PageHeader';
import { PageShell } from '@/components/ui/PageShell';
import { useDevice } from '@/context/DeviceContext';
import { useHubStatus } from '@/hooks/useHubStatus';
import { getHubSetupIssue } from '@/utils/hubMessages';
import { validateExerciseLobby } from '@/services/networkHub';
import {
  buildJoinPath,
  isValidLobbyCode,
  normalizeLobbyCode,
  saveLobbyCode,
} from '@/utils/lobbyCode';

export function JoinLobbyPage() {
  const navigate = useNavigate();
  const { formFactor } = useDevice();
  const isMobile = formFactor === 'mobile';
  const { code: routeCode } = useParams<{ code?: string }>();
  const { connection } = useHubStatus();
  const hubIssue = getHubSetupIssue(connection);
  const [inputCode, setInputCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const prefilledCode = routeCode ? normalizeLobbyCode(routeCode) : '';

  useEffect(() => {
    if (prefilledCode) {
      setInputCode(prefilledCode);
    }
  }, [prefilledCode]);

  async function joinWithCode(code: string) {
    setError('');
    const normalized = normalizeLobbyCode(code);
    if (!isValidLobbyCode(normalized)) {
      setError('Enter the 6-character exercise code from your host.');
      return;
    }

    setBusy(true);
    const exists = await validateExerciseLobby(normalized);
    setBusy(false);

    if (!exists) {
      setError('Exercise not found. Check the code with your WIT host.');
      return;
    }

    saveLobbyCode(normalized);
    navigate(buildJoinPath(normalized, 'provider'));
  }

  async function handleJoin() {
    await joinWithCode(inputCode);
  }

  const canJoin =
    isValidLobbyCode(normalizeLobbyCode(inputCode)) &&
    !busy &&
    (import.meta.env.DEV || connection !== 'offline');

  if (isMobile) {
    return (
      <MobileAppShell
        header={<MobileHeader title="Join exercise" subtitle="Enter host code" backTo="/home" />}
        footer={
          <div className="mobile-sticky-footer">
            <Button type="button" className="w-full" size="lg" disabled={!canJoin} onClick={handleJoin}>
              {busy ? 'Joining…' : 'Join lobby'}
            </Button>
          </div>
        }
      >
        <div className="mobile-page-pad lobby-stagger">
          <HubSetupAlert connection={connection} className="mb-4" />

          <p className="mb-6 text-center text-sm text-ask-muted">
            Enter the 6-character code your WIT host shared with you.
          </p>

          <CodeInput value={inputCode} onChange={setInputCode} disabled={busy} autoFocus />

          {error && (
            <Alert variant="critical" className="mt-4" role="alert" title="Could not join">
              {error}
            </Alert>
          )}

          <Alert variant="info" className="mt-6" title="Exercise staff use a secure link">
            WIT and command staff must open the secure controller link supplied by the exercise host.
            A provider code never grants exercise-control access.
          </Alert>


          <button
            type="button"
            className="mt-8 w-full text-center text-sm text-ask-muted"
            onClick={() => navigate('/host')}
          >
            Hosting? <span className="text-ask-accent">Create exercise</span>
          </button>
        </div>
      </MobileAppShell>
    );
  }

  return (
    <PageShell showTrainingBanner={false}>
      <div className="mx-auto w-full max-w-lg flex-1 px-4 py-8 sm:px-6">
        <PageHeader
          eyebrow="Join"
          title="Join exercise"
          description="Enter the exercise code your host sent you."
          className="mb-6"
        />

        <HubSetupAlert connection={connection} className="mb-4" />

        <Card as="section" padding="lg" className="lobby-stagger">
          <div className="space-y-4">
            <div>
              <label htmlFor="exercise-code" className="mb-2 block text-sm font-medium text-ask-text">
                Exercise code
              </label>
              <Input
                id="exercise-code"
                value={inputCode}
                onChange={(event) => setInputCode(event.target.value.toUpperCase())}
                autoComplete="off"
                inputMode="text"
                maxLength={8}
                placeholder="ABC123"
                className="exercise-code-input text-center font-mono text-xl tracking-[0.35em]"
              />
              <p className="mt-2 text-center text-xs text-ask-muted">Not case-sensitive</p>
            </div>

            <Alert variant="info" title="Provider join only">
              WIT and command staff must use the secure link from the host. This code joins a provider role only.
            </Alert>


            <Button type="button" className="w-full" disabled={!canJoin} onClick={handleJoin}>
              {busy ? 'Joining…' : 'Join lobby'}
            </Button>
          </div>
        </Card>

        {error && (
          <Alert variant="critical" className="mt-4" role="alert" title="Could not join">
            {error}
          </Alert>
        )}

        {hubIssue === 'unreachable' && import.meta.env.PROD && (
          <p className="mt-4 text-xs text-ask-muted">
            Local testing: run <code className="text-ask-accent">npm run dev</code> on your computer.
          </p>
        )}

        <p className="mt-6 text-center text-sm text-ask-muted">
          Hosting the exercise?{' '}
          <button
            type="button"
            className="text-ask-accent underline-offset-2 hover:underline"
            onClick={() => navigate('/host')}
          >
            Create exercise
          </button>
        </p>
      </div>
    </PageShell>
  );
}
