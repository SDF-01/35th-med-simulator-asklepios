import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ExerciseCodeDisplay } from '@/components/lobby/ExerciseCodeDisplay';
import { ControllerSharePanel } from '@/components/lobby/ControllerSharePanel';
import { LobbyPlayerRoster } from '@/components/lobby/LobbyPlayerRoster';
import { HubSetupAlert } from '@/components/ui/HubSetupAlert';
import { MobileAppShell } from '@/components/mobile/MobileAppShell';
import { MobileHeader } from '@/components/mobile/MobileHeader';
import { PageHeader } from '@/components/ui/PageHeader';
import { PageShell } from '@/components/ui/PageShell';
import { useDevice } from '@/context/DeviceContext';
import { useHubStatus } from '@/hooks/useHubStatus';
import { createExerciseLobby, joinWitDashboard, onExerciseUpdate, setActiveLobbyCode } from '@/services/networkHub';
import type { ProviderDevice } from '@/types/device';
import type { ActiveExerciseState } from '@/types/exercise';
import { buildJoinPath, isValidLobbyCode, normalizeLobbyCode, saveLobbyCode } from '@/utils/lobbyCode';
import { getHubSetupIssue } from '@/utils/hubMessages';
import { disableSoloMode } from '@/utils/soloMode';

export function HostExercisePage() {
  const navigate = useNavigate();
  const { formFactor } = useDevice();
  const isMobile = formFactor === 'mobile';
  const { code: routeCode } = useParams<{ code?: string }>();
  const { connection } = useHubStatus();
  const hubIssue = getHubSetupIssue(connection);
  const hubReady = import.meta.env.DEV || connection !== 'offline';
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [players, setPlayers] = useState<ProviderDevice[]>([]);
  const [exercise, setExercise] = useState<ActiveExerciseState | null>(null);

  const displayCode = routeCode ? normalizeLobbyCode(routeCode) : '';
  const inLobby = isValidLobbyCode(displayCode);

  useEffect(() => {
    disableSoloMode();
  }, []);

  useEffect(() => {
    if (!inLobby || !displayCode) return;
    saveLobbyCode(displayCode);
    setActiveLobbyCode(displayCode);
  }, [displayCode, inLobby]);

  useEffect(() => {
    if (!inLobby || !displayCode) return;
    const unsubDevices = joinWitDashboard(setPlayers, setError);
    const unsubExercise = onExerciseUpdate(({ exercise: next }) => setExercise(next));
    return () => {
      unsubDevices();
      unsubExercise();
    };
  }, [displayCode, inLobby]);

  async function handleCreate() {
    setError('');
    if (!hubReady) {
      setError('Complete hub setup on Vercel before creating lobbies (see steps above).');
      return;
    }
    setBusy(true);
    try {
      const { code } = await createExerciseLobby();
      saveLobbyCode(code);
      navigate(`/host/${encodeURIComponent(code)}`, { replace: true });
    } catch {
      setError('Could not reach the exercise hub. See setup steps above.');
    } finally {
      setBusy(false);
    }
  }

  function openWitConsole() {
    if (!displayCode) return;
    navigate(buildJoinPath(displayCode, 'wit'));
  }

  if (!inLobby) {
    const createContent = (
      <>
        <HubSetupAlert connection={connection} className="mb-4" />
        <p className="text-sm leading-relaxed text-ask-muted">
          You will get a 6-character code. Providers enter that code on their phones, like a game
          lobby.
        </p>
        <Button
          type="button"
          className="mt-6 w-full"
          size={isMobile ? 'lg' : 'md'}
          disabled={busy || !hubReady}
          onClick={handleCreate}
        >
          {busy ? 'Creating lobby…' : 'Create exercise'}
        </Button>
        {!hubReady && (
          <p className="mt-3 text-xs text-ask-muted">
            Button unlocks after hub setup. For local tests, run npm run dev on your machine.
          </p>
        )}
        {error && (
          <Alert variant="critical" className="mt-4" role="alert" title="Could not create">
            {error}
          </Alert>
        )}
      </>
    );

    if (isMobile) {
      return (
        <MobileAppShell
          showTabBar={false}
          header={<MobileHeader title="Host exercise" backTo="/home" />}
        >
          <div className="mobile-page-pad">{createContent}</div>
          <p className="mobile-page-pad pb-8 text-center text-sm text-ask-muted">
            Joining as provider?{' '}
            <button type="button" className="text-ask-accent" onClick={() => navigate('/join')}>
              Enter code
            </button>
          </p>
        </MobileAppShell>
      );
    }

    return (
      <PageShell showTrainingBanner={false}>
        <div className="mx-auto w-full max-w-lg flex-1 px-4 py-8 sm:px-6">
          <PageHeader
            eyebrow="Host"
            title="Host an exercise"
            description="Create a lobby and share the exercise code with providers on their cell phones."
            className="mb-6"
          />
          <Card padding="lg" className="text-center">
            {createContent}
          </Card>
          <p className="mt-6 text-center text-sm text-ask-muted">
            Joining as a provider?{' '}
            <button type="button" className="text-ask-accent" onClick={() => navigate('/join')}>
              Enter exercise code
            </button>
          </p>
        </div>
      </PageShell>
    );
  }

  const exerciseStarted = Boolean(exercise);
  const lobbyBody = (
    <>
      {hubIssue !== 'ok' && hubIssue !== 'dev' && (
        <HubSetupAlert connection={connection} className="mb-4" />
      )}
      <ExerciseCodeDisplay code={displayCode} className="mb-4" />
      <ControllerSharePanel code={displayCode} className="mb-4" />
      {error && (
        <Alert variant="critical" className="mb-4" role="alert" title="Controller authorization unavailable">
          {error}
        </Alert>
      )}
      <LobbyPlayerRoster players={players} className="mb-4" />
      <Card padding="md">
        {exerciseStarted ? (
          <Alert variant="success" title="Exercise in progress">
            Open the authorized WIT console on a laptop to facilitate the simulation.
          </Alert>
        ) : (
          <p className="text-sm text-ask-muted">
            {players.length === 0
              ? 'Waiting for providers to join…'
              : `${players.length} provider(s) ready.`}
          </p>
        )}
        <Button type="button" className="mt-4 w-full" size={isMobile ? 'lg' : 'md'} onClick={openWitConsole}>
          {exerciseStarted ? 'Open WIT console' : 'Start exercise (laptop)'}
        </Button>
      </Card>
    </>
  );

  if (isMobile) {
    return (
      <MobileAppShell
        showTabBar={false}
        header={<MobileHeader title="Host lobby" subtitle="Share code" backTo="/host" />}
      >
        <div className="mobile-page-pad">{lobbyBody}</div>
      </MobileAppShell>
    );
  }

  return (
    <PageShell showTrainingBanner={false}>
      <div className="mx-auto w-full max-w-lg flex-1 px-4 py-8 sm:px-6">
        <PageHeader
          eyebrow="Host lobby"
          title="Share the exercise code"
          description="Providers enter the lobby code. Exercise staff use the separate secure controller links."
          className="mb-4"
        />
        {lobbyBody}
      </div>
    </PageShell>
  );
}
