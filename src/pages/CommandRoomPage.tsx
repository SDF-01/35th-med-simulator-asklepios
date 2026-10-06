import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppChrome } from '@/components/ui/AppChrome';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHeader } from '@/components/ui/PageHeader';
import { PageShell } from '@/components/ui/PageShell';
import { HubNetworkPanel } from '@/components/ui/HubNetworkPanel';
import { LobbySharePanel } from '@/components/lobby/LobbySharePanel';
import { Alert } from '@/components/ui/Alert';
import { useDevice } from '@/context/DeviceContext';
import { DesktopRequiredGate } from '@/components/mobile/DesktopRequiredGate';
import { useLobbyCode } from '@/hooks/useLobbyCode';
import {
  joinCommandRoom,
  onSessionUpdate,
  subscribeHubAuthorizationErrors,
} from '@/services/networkHub';
import { getHubOfflineMessage } from '@/utils/hubMessages';
import { buildJoinPath } from '@/utils/lobbyCode';
import type { ProviderDevice, SessionSyncPayload } from '@/types/device';
import type { Scenario, SimulationSession } from '@/types';
import { getDepartmentLabel } from '@/types/providerProfile';

const STATUS_VARIANT: Record<
  ProviderDevice['status'],
  'muted' | 'accent' | 'success' | 'caution' | 'default'
> = {
  waiting: 'muted',
  standby: 'caution',
  briefing: 'caution',
  in_simulation: 'accent',
  handoff_ready: 'accent',
  completed: 'success',
  offline: 'default',
};

const STATUS_LABELS: Record<ProviderDevice['status'], string> = {
  waiting: 'Waiting',
  standby: 'Standby',
  briefing: 'Briefing',
  in_simulation: 'In Simulation',
  handoff_ready: 'Handoff ready',
  completed: 'Complete',
  offline: 'Offline',
};

export function CommandRoomPage() {
  const { formFactor } = useDevice();
  const lobbyCode = useLobbyCode({ redirectIfMissing: true });

  if (formFactor === 'mobile') {
    return <DesktopRequiredGate role="command" lobbyCode={lobbyCode} />;
  }

  return <CommandRoomDesktop lobbyCode={lobbyCode} />;
}

function CommandRoomDesktop({ lobbyCode }: { lobbyCode: string | null }) {
  const navigate = useNavigate();
  const [devices, setDevices] = useState<ProviderDevice[]>([]);
  const [sessions, setSessions] = useState<Record<string, SimulationSession>>({});
  const [scenarios, setScenarios] = useState<Record<string, Scenario>>({});
  const [authorizationError, setAuthorizationError] = useState('');

  useEffect(() => {
    if (!lobbyCode) return;
    const unsubDevices = joinCommandRoom(setDevices, setAuthorizationError);
    const unsubAuthorization = subscribeHubAuthorizationErrors(setAuthorizationError);
    const unsubSessions = onSessionUpdate((payload: SessionSyncPayload) => {
      setSessions((prev) => ({ ...prev, [payload.deviceId]: payload.session }));
      setScenarios((prev) => ({ ...prev, [payload.deviceId]: payload.scenario }));
    });
    return () => {
      unsubDevices();
      unsubAuthorization();
      unsubSessions();
    };
  }, [lobbyCode]);

  const activeCount = devices.filter(
    (d) => d.status === 'in_simulation' || d.status === 'briefing',
  ).length;

  return (
    <PageShell>
      <AppChrome role="command" title="Exercise command room" />
      <div className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <PageHeader
          eyebrow="Commander View"
          title="Exercise Command Room"
          description={`${devices.length} participant(s) · ${activeCount} active evolution(s)`}
          actions={
            <>
              <Button
                variant="secondary"
                onClick={() => lobbyCode && navigate(buildJoinPath(lobbyCode, 'wit'))}
              >
                WIT Dashboard
              </Button>
              <Button variant="ghost" onClick={() => navigate('/home')}>
                Home
              </Button>
            </>
          }
          className="mb-8"
        />

        <HubNetworkPanel className="mb-6" />
        {lobbyCode && <LobbySharePanel code={lobbyCode} className="mb-6" />}
        {authorizationError && (
          <Alert variant="critical" className="mb-6" role="alert" title="Command authorization required">
            {authorizationError}
          </Alert>
        )}

        <main id="main-content" className="pb-8">
          {devices.length === 0 ? (
            <EmptyState
              title="No participants connected"
              description={getHubOfflineMessage()}
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {devices.map((device) => {
                const session = sessions[device.deviceId];
                const scenario = scenarios[device.deviceId];
                return (
                  <Card key={device.deviceId} as="article" padding="md">
                    <p className="font-mono text-xs text-ask-accent">{device.deviceId}</p>
                    <h2 className="mt-1 text-lg font-semibold">{device.displayName}</h2>
                    <p className="mt-1 text-xs text-ask-muted">
                      {getDepartmentLabel(device.hospitalDepartment ?? 'clinical_immediate')}
                    </p>
                    <Badge variant={STATUS_VARIANT[device.status]} className="mt-3">
                      {STATUS_LABELS[device.status]}
                    </Badge>

                    {session && scenario && (
                      <dl className="mt-4 space-y-1 border-t border-ask-border pt-3 text-xs">
                        <div className="flex justify-between gap-2">
                          <dt className="text-ask-muted">Scenario</dt>
                          <dd className="text-right">{scenario.title}</dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-ask-muted">Turn</dt>
                          <dd className="font-mono">{session.current_turn}</dd>
                        </div>
                        <div className="flex justify-between gap-2">
                          <dt className="text-ask-muted">Casualties</dt>
                          <dd className="font-mono">{session.patients.length}</dd>
                        </div>
                      </dl>
                    )}
                  </Card>
                );
              })}
            </div>
          )}
        </main>
      </div>
    </PageShell>
  );
}

