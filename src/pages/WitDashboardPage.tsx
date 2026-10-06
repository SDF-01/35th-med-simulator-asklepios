import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PatientStatusPanel } from '@/components/simulation/PatientStatusPanel';
import { WitContextualTimeline } from '@/components/wit/WitContextualTimeline';
import { WitLiveFeed, WitLiveProviderInputs } from '@/components/wit/WitLiveMonitor';
import { WitProviderReportPanel } from '@/components/wit/WitProviderReportPanel';
import { WitExerciseControlBar } from '@/components/wit/WitExerciseControlBar';
import { WitExercisePanel } from '@/components/wit/WitExercisePanel';
import { WitScenarioConfigPanel } from '@/components/wit/WitScenarioConfigPanel';
import { Button } from '@/components/ui/Button';
import { AppChrome } from '@/components/ui/AppChrome';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { HubNetworkPanel } from '@/components/ui/HubNetworkPanel';
import { LobbySharePanel } from '@/components/lobby/LobbySharePanel';
import { useDevice } from '@/context/DeviceContext';
import { DesktopRequiredGate } from '@/components/mobile/DesktopRequiredGate';
import { useLobbyCode } from '@/hooks/useLobbyCode';
import { PageHeader, SectionLabel } from '@/components/ui/PageHeader';
import { Panel, PanelHeader } from '@/components/ui/Panel';
import { PageShell, DashboardBody } from '@/components/ui/PageShell';
import { applyScenarioConfiguration } from '@/engines/scenarioConfigurator';
import { isCasualtyConfigValid } from '@/engines/casualtyTriageEngine';
import { resolveBaseScenarioId } from '@/engines/scenarioResolver';
import { generateWitProviderReport } from '@/engines/witProviderReportEngine';
import type { WitProviderReport } from '@/engines/witProviderReportEngine';
import { scenariosById } from '@/content/scenarios';
import { useSimulationStore } from '@/store/simulationStore';
import type { ActiveExerciseState } from '@/types/exercise';
import type { ProviderDevice, SessionSyncPayload } from '@/types/device';
import { getDepartmentLabel } from '@/types/providerProfile';
import { DEFAULT_SCENARIO_CONFIG, type ScenarioConfiguration } from '@/types/witConfig';
import { getHubOfflineMessage } from '@/utils/hubMessages';
import { buildJoinPath } from '@/utils/lobbyCode';
import {
  deployToDevice,
  armLobbyExercise,
  endActiveExercise,
  endExercise,
  joinWitDashboard,
  subscribeHubAuthorizationErrors,
  onExerciseUpdate,
  onSessionUpdate,
  requestDeviceSession,
} from '@/services/networkHub';
import type { SimulationSession, Scenario } from '@/types';

const STATUS_LABELS: Record<ProviderDevice['status'], string> = {
  waiting: 'Ready. Waiting for scenario',
  standby: 'Standby. Exercise in progress',
  briefing: 'Scenario loaded. Briefing',
  in_simulation: 'In simulation',
  handoff_ready: 'Segment complete. Selecting handoff',
  completed: 'Evolution complete',
  offline: 'Offline',
};

export function WitDashboardPage() {
  const { formFactor } = useDevice();
  const lobbyCode = useLobbyCode({ redirectIfMissing: true });

  if (formFactor === 'mobile') {
    return <DesktopRequiredGate role="wit" lobbyCode={lobbyCode} />;
  }

  return <WitDashboardDesktop lobbyCode={lobbyCode} />;
}

function WitDashboardDesktop({ lobbyCode }: { lobbyCode: string | null }) {
  const navigate = useNavigate();
  const deployConfiguredScenario = useSimulationStore((s) => s.deployConfiguredScenario);
  const [devices, setDevices] = useState<ProviderDevice[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const [config, setConfig] = useState<ScenarioConfiguration>({ ...DEFAULT_SCENARIO_CONFIG });
  const [liveSession, setLiveSession] = useState<SimulationSession | null>(null);
  const [liveScenario, setLiveScenario] = useState<Scenario | null>(null);
  const [sessionsByDevice, setSessionsByDevice] = useState<Record<string, SimulationSession>>({});
  const [scenariosByDevice, setScenariosByDevice] = useState<Record<string, Scenario>>({});
  const [report, setReport] = useState<WitProviderReport | null>(null);
  const [activeExercise, setActiveExercise] = useState<ActiveExerciseState | null>(null);
  const [showEndexConfirm, setShowEndexConfirm] = useState(false);
  const [startingExercise, setStartingExercise] = useState(false);
  const [deployingExercise, setDeployingExercise] = useState(false);
  const [startExerciseError, setStartExerciseError] = useState('');
  const [authorizationError, setAuthorizationError] = useState('');
  const selectedDeviceIdRef = useRef<string | null>(null);

  selectedDeviceIdRef.current = selectedDeviceId;

  useEffect(() => {
    if (!lobbyCode) return;
    const unsubDevices = joinWitDashboard(setDevices, setAuthorizationError);
    const unsubAuthorization = subscribeHubAuthorizationErrors(setAuthorizationError);
    const unsubExercise = onExerciseUpdate(({ exercise }) => setActiveExercise(exercise));
    const unsubSession = onSessionUpdate((payload: SessionSyncPayload) => {
      setSessionsByDevice((prev) => ({ ...prev, [payload.deviceId]: payload.session }));
      setScenariosByDevice((prev) => ({ ...prev, [payload.deviceId]: payload.scenario }));

      if (payload.deviceId === selectedDeviceIdRef.current) {
        setLiveSession(payload.session);
        setLiveScenario(payload.scenario);
      }
    });

    return () => {
      unsubDevices();
      unsubAuthorization();
      unsubExercise();
      unsubSession();
    };
  }, [lobbyCode]);

  const selectedDevice = devices.find((d) => d.deviceId === selectedDeviceId);

  useEffect(() => {
    if (!selectedDevice) return;
    setConfig((prev) => ({
      ...prev,
      baseScenarioId: resolveBaseScenarioId(
        prev.scenarioSelection,
        selectedDevice.hospitalDepartment ?? 'clinical_immediate',
      ),
    }));
  }, [selectedDevice?.deviceId, selectedDevice?.hospitalDepartment]);

  const waitingDevices = devices.filter((d) => d.status === 'waiting' || d.status === 'standby');
  const storedSession = selectedDeviceId ? sessionsByDevice[selectedDeviceId] : null;
  const storedScenario = selectedDeviceId ? scenariosByDevice[selectedDeviceId] : null;
  const activeSession = liveSession ?? storedSession;
  const activeScenario = liveScenario ?? storedScenario;

  const isLive =
    selectedDevice &&
    (selectedDevice.status === 'in_simulation' || selectedDevice.status === 'briefing') &&
    activeSession;

  const canGenerateReport = Boolean(selectedDevice && activeSession && activeScenario);
  const canEndex =
    selectedDeviceId &&
    selectedDevice &&
    (selectedDevice.status === 'in_simulation' || selectedDevice.status === 'briefing');

  const deviceDeployable = Boolean(
    selectedDevice &&
      (selectedDevice.status === 'waiting' || selectedDevice.status === 'standby'),
  );
  const triageValid = isCasualtyConfigValid(config.casualties);
  const baseScenarioId = selectedDevice
    ? resolveBaseScenarioId(
        config.scenarioSelection,
        selectedDevice.hospitalDepartment ?? 'clinical_immediate',
      )
    : config.baseScenarioId;
  const hasPlayableScenario = Boolean(scenariosById[baseScenarioId]);
  const canStartExercise =
    !activeExercise && devices.some((device) => device.status === 'waiting');
  const canDeployExercise = Boolean(
    activeExercise &&
      selectedDeviceId &&
      deviceDeployable &&
      hasPlayableScenario &&
      triageValid,
  );
  const deployHint = !activeExercise
    ? 'Start the exercise first.'
    : !selectedDeviceId
      ? 'Select a provider device from the sidebar.'
      : !deviceDeployable
        ? 'Selected device must be waiting or standby.'
        : !triageValid
          ? 'Fix casualty triage totals before deploy.'
          : !hasPlayableScenario
            ? 'Resolved scenario template is not available.'
            : undefined;

  function handleStartLobbyExercise() {
    setStartingExercise(true);
    setStartExerciseError('');
    armLobbyExercise('Training evolution')
      .then((result) => {
        if (!result.ok) {
          setStartExerciseError(result.error ?? 'Could not start exercise');
        }
      })
      .catch(() => {
        setStartExerciseError('Could not reach exercise hub. Check network connection.');
      })
      .finally(() => {
        setStartingExercise(false);
      });
  }

  function handleDeploy() {
    if (!selectedDeviceId || !selectedDevice || !canDeployExercise) return;

    setDeployingExercise(true);
    const department = selectedDevice.hospitalDepartment ?? 'clinical_immediate';
    const resolvedBaseId = resolveBaseScenarioId(config.scenarioSelection, department);
    const base = scenariosById[resolvedBaseId];
    if (!base) {
      setDeployingExercise(false);
      return;
    }

    const deployConfig = { ...config, baseScenarioId: resolvedBaseId };
    const scenario = applyScenarioConfiguration(base, deployConfig, {
      providerName: selectedDevice.providerName,
      hospitalDepartment: department,
    });
    deployConfiguredScenario(deployConfig);
    deployToDevice({ deviceId: selectedDeviceId, scenario, scenarioConfig: deployConfig });
    setReport(null);
    setDeployingExercise(false);
  }

  function handleEndLobbyExercise() {
    endActiveExercise();
    setStartExerciseError('');
  }

  function handleGenerateReport() {
    if (!selectedDevice || !activeSession || !activeScenario) return;

    const generated = generateWitProviderReport(
      activeSession,
      activeScenario,
      selectedDevice.displayName,
      selectedDevice.deviceId,
      config,
    );
    setReport(generated);
  }

  function handleSelectDevice(deviceId: string) {
    setSelectedDeviceId(deviceId);
    setReport(null);
    setShowEndexConfirm(false);
    setLiveSession(sessionsByDevice[deviceId] ?? null);
    setLiveScenario(scenariosByDevice[deviceId] ?? null);
    requestDeviceSession(deviceId);
  }

  function handleEndex() {
    if (!selectedDeviceId) return;
    endExercise(selectedDeviceId);
    setShowEndexConfirm(false);
  }

  return (
    <PageShell variant="dashboard">
      <AppChrome role="wit" title="Scenario command" layout="dashboard" />
      <DashboardBody>
        <Panel
          as="aside"
          variant="sidebar"
          className="dashboard-sidebar"
          header={
          <PanelHeader
            eyebrow="WIT Evaluator"
            title="Device network"
            description={`${waitingDevices.length} provider device(s) ready`}
          />
        }
        footer={
          <nav className="flex flex-wrap gap-4 p-3" aria-label="WIT navigation">
            <button
              type="button"
              className="min-h-9 text-xs text-ask-muted transition-colors hover:text-ask-accent"
              onClick={() => navigate(lobbyCode ? `/host/${encodeURIComponent(lobbyCode)}` : '/host')}
            >
              Host lobby
            </button>
            <button
              type="button"
              className="min-h-9 text-xs text-ask-muted transition-colors hover:text-ask-accent"
              onClick={() => navigate(lobbyCode ? buildJoinPath(lobbyCode, 'command') : '/join')}
            >
              Command
            </button>
            <button
              type="button"
              className="min-h-9 text-xs text-ask-muted transition-colors hover:text-ask-accent"
              onClick={() => navigate('/home')}
            >
              Mission entry
            </button>
          </nav>
        }
      >
        <div className="space-y-2 overflow-y-auto p-3">
          <HubNetworkPanel compact className="mb-3" />
          {lobbyCode && <LobbySharePanel code={lobbyCode} />}
          {authorizationError && (
            <Alert variant="critical" role="alert" title="Controller authorization required">
              {authorizationError}
            </Alert>
          )}
          {devices.length === 0 && (
            <EmptyState
              title="No devices connected"
              description={getHubOfflineMessage()}
              className="py-6"
            />
          )}
          {devices.map((device) => (
            <button
              key={device.deviceId}
              type="button"
              onClick={() => handleSelectDevice(device.deviceId)}
              className={[
                'ask-list-item min-h-11 p-3',
                selectedDeviceId === device.deviceId ? 'ask-list-item--selected' : '',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              <p className="font-mono text-xs text-ask-accent">{device.deviceId}</p>
              <p className="font-medium">{device.displayName}</p>
              <p className="text-xs text-ask-muted">
                {getDepartmentLabel(device.hospitalDepartment ?? 'clinical_immediate')}
              </p>
              <Badge variant="muted" className="mt-2 capitalize">
                {STATUS_LABELS[device.status]}
              </Badge>
            </button>
          ))}
        </div>
      </Panel>

        <main id="main-content" className="dashboard-main">
        {!selectedDevice && (
          <EmptyState
            title="Select a provider device"
            description="Choose a connected provider from the device list to configure scenarios or start a multi-role exercise."
            className="my-8"
          />
        )}

        {report && (
          <WitProviderReportPanel report={report} onClose={() => setReport(null)} />
        )}

        {!report && selectedDevice && isLive && activeScenario && activeSession && (
          <div>
            <PageHeader
              title="Live Monitor"
              description={`${selectedDevice.displayName} · Turn ${activeSession.current_turn} · Score ${activeSession.score}`}
              actions={
                <>
                  {canEndex && !showEndexConfirm && (
                    <Button variant="danger" onClick={() => setShowEndexConfirm(true)}>
                      ENDEX
                    </Button>
                  )}
                  {canGenerateReport && (
                    <Button variant="secondary" onClick={handleGenerateReport}>
                      Generate Learning Report
                    </Button>
                  )}
                </>
              }
              className="mb-4"
            />

            {showEndexConfirm && (
              <Alert variant="critical" role="alert" title="Confirm ENDEX" className="mb-4">
                <p className="mb-4">
                  This will immediately end the exercise for the provider. They will receive a
                  warning and be routed to after-action review. This action cannot be undone.
                </p>
                <div className="flex flex-wrap gap-3">
                  <Button variant="danger" onClick={handleEndex}>
                    End Exercise Now
                  </Button>
                  <Button variant="ghost" onClick={() => setShowEndexConfirm(false)}>
                    Cancel
                  </Button>
                </div>
              </Alert>
            )}

            <Card padding="md" className="mb-4">
              <SectionLabel accent className="mb-3">
                Contextual Timeline (Prompt → Update)
              </SectionLabel>
              <WitContextualTimeline
                feed={activeSession.feed}
                startTime={activeSession.start_time}
              />
            </Card>

            <div className="mb-4 grid gap-4 lg:grid-cols-2">
              <WitLiveProviderInputs feed={activeSession.feed} currentTurn={activeSession.current_turn} />
              <WitLiveFeed feed={activeSession.feed} />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <Card padding="md">
                <SectionLabel accent className="mb-3">
                  WIT: Actual Patient Stats
                </SectionLabel>
                <PatientStatusPanel patients={activeSession.patients} mode="wit" />
              </Card>
              <Card padding="md">
                <SectionLabel className="mb-3">Parsed Actions</SectionLabel>
                <div className="max-h-80 space-y-2 overflow-y-auto text-sm">
                  {activeSession.actions.length === 0 ? (
                    <p className="text-ask-muted italic">No parsed actions yet.</p>
                  ) : (
                    activeSession.actions.map((action) => (
                      <div key={action.turn_id} className="rounded-ask-sm border-l-2 border-ask-muted pl-3">
                        <p className="text-xs text-ask-muted">Turn {action.turn_id}</p>
                        <p className="text-ask-text/80">{action.raw_text}</p>
                        {action.recognized_actions.length > 0 ? (
                          <p className="text-xs text-ask-accent">
                            {action.recognized_actions.map((a) => a.label).join('; ')}
                          </p>
                        ) : (
                          <p className="text-xs text-ask-caution">
                            Assessment only / not mapped to doctrine action
                          </p>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </Card>
            </div>
          </div>
        )}

        {!report && selectedDevice && selectedDevice.status === 'completed' && !activeSession && (
          <Card padding="lg">
            <PageHeader title="Evolution Complete" className="mb-2" />
            <p className="text-sm leading-relaxed text-ask-muted">
              Session data is not available for this device. The WIT dashboard must be connected
              during the evolution to generate a learning report.
            </p>
          </Card>
        )}

        {!report && selectedDevice && selectedDevice.status === 'completed' && activeSession && activeScenario && (
          <Card variant="accent" padding="lg">
            <PageHeader title="Evolution Complete" className="mb-2" />
            <p className="mb-4 text-sm leading-relaxed text-ask-muted">
              {selectedDevice.displayName} finished {activeScenario.title}. Generate a learning
              report to debrief performance.
            </p>
            <Button onClick={handleGenerateReport}>Generate Learning Report</Button>
          </Card>
        )}

        {!report && selectedDevice && selectedDevice.status === 'in_simulation' && !activeSession && (
          <EmptyState
            title="Waiting for session sync"
            description="Provider is in simulation. Live data will appear when the session syncs."
            className="my-12"
          />
        )}

        {!report &&
          selectedDevice &&
          !isLive &&
          selectedDevice.status !== 'in_simulation' &&
          selectedDevice.status !== 'completed' && (
            <div>
              <WitExerciseControlBar
                activeExercise={activeExercise}
                selectedDevice={selectedDevice}
                canStart={canStartExercise}
                canDeploy={canDeployExercise}
                deployHint={deployHint}
                starting={startingExercise}
                deploying={deployingExercise}
                startError={startExerciseError}
                onStart={handleStartLobbyExercise}
                onDeploy={handleDeploy}
                onEndExercise={handleEndLobbyExercise}
              />
              <WitExercisePanel
                devices={devices}
                activeExercise={activeExercise}
                config={config}
                onExerciseStarted={() => {
                  setReport(null);
                  setStartExerciseError('');
                }}
              />
              <PageHeader
                title="Scenario Setup"
                description={`Configure scenario for ${selectedDevice.displayName} (${getDepartmentLabel(selectedDevice.hospitalDepartment)}). Status: ${STATUS_LABELS[selectedDevice.status]}`}
                className="mb-6"
              />
              <WitScenarioConfigPanel
                config={config}
                onChange={setConfig}
                targetDeviceLabel={`${selectedDevice.displayName} (${selectedDevice.deviceId})`}
                providerDepartment={selectedDevice.hospitalDepartment ?? 'clinical_immediate'}
                hideDeployButton
              />
              {selectedDevice.status === 'briefing' && (
                <Alert variant="info" className="mt-4" title="Scenario deployed">
                  Provider has the mission brief. They can begin when ready. Live data appears once
                  simulation starts.
                </Alert>
              )}
              {selectedDevice.status !== 'waiting' &&
                selectedDevice.status !== 'standby' &&
                selectedDevice.status !== 'briefing' && (
                <Alert variant="caution" className="mt-4" title="Device not ready">
                  Device is not in waiting state. Provider must return to lobby after completing an
                  evolution.
                </Alert>
              )}
            </div>
          )}
        </main>
      </DashboardBody>
    </PageShell>
  );
}
