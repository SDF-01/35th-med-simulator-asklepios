import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Alert } from '@/components/ui/Alert';
import { AppChrome } from '@/components/ui/AppChrome';
import { Badge } from '@/components/ui/Badge';
import { CasualtySelector } from '@/components/simulation/CasualtySelector';
import { PatientInteractionFeed } from '@/components/simulation/PatientInteractionFeed';
import { PatientStatusPanel } from '@/components/simulation/PatientStatusPanel';
import { ProviderActionBar } from '@/components/simulation/ProviderActionBar';
import { ProviderActionDock, type ProviderDockTab } from '@/components/simulation/ProviderActionDock';
import { ProviderBodyInjuryMap } from '@/components/simulation/ProviderBodyInjuryMap';
import { ProviderSupplyPanel } from '@/components/simulation/ProviderSupplyPanel';
import { ProviderVitalsBanner } from '@/components/simulation/ProviderVitalsBanner';
import { ProviderVitalsStrip } from '@/components/simulation/ProviderVitalsStrip';
import { PageShell } from '@/components/ui/PageShell';
import { useDevice } from '@/context/DeviceContext';
import { MobileAppShell } from '@/components/mobile/MobileAppShell';
import { MobileHeader } from '@/components/mobile/MobileHeader';
import { getOrCreateDeviceId, onEndExercise } from '@/services/networkHub';
import { getBackTarget } from '@/utils/navigationBack';
import { useSimulationStore } from '@/store/simulationStore';

function formatTimer(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function ProviderSimulationPage() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const backTarget = getBackTarget(pathname);
  const { formFactor } = useDevice();
  const isMobile = formFactor === 'mobile';
  const scenario = useSimulationStore((s) => s.scenario);
  const scenarioConfig = useSimulationStore((s) => s.scenarioConfig);
  const session = useSimulationStore((s) => s.session);
  const aar = useSimulationStore((s) => s.aar);
  const deviceId = useSimulationStore((s) => s.deviceId);
  const endexWarning = useSimulationStore((s) => s.endexWarning);
  const casualtyViewMode = useSimulationStore((s) => s.casualtyViewMode);
  const setDeviceId = useSimulationStore((s) => s.setDeviceId);
  const submitAction = useSimulationStore((s) => s.submitAction);
  const setActivePatientId = useSimulationStore((s) => s.setActivePatientId);
  const setCasualtyViewMode = useSimulationStore((s) => s.setCasualtyViewMode);
  const forceEndFromWit = useSimulationStore((s) => s.forceEndFromWit);
  const pendingHandoff = useSimulationStore((s) => s.pendingHandoff);
  const [elapsed, setElapsed] = useState(0);
  const [dockTab, setDockTab] = useState<ProviderDockTab>('treat');
  const [showDesktopClinical, setShowDesktopClinical] = useState(false);
  const [showDesktopSupply, setShowDesktopSupply] = useState(false);
  const [showDesktopObservations, setShowDesktopObservations] = useState(false);

  useEffect(() => {
    if (!deviceId) setDeviceId(getOrCreateDeviceId());
  }, [deviceId, setDeviceId]);

  useEffect(() => {
    const unsub = onEndExercise(() => forceEndFromWit());
    return unsub;
  }, [forceEndFromWit]);

  useEffect(() => {
    if (!session || session.status !== 'active') return;
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - session.start_time) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [session]);

  useEffect(() => {
    if (pendingHandoff) navigate('/provider/handoff');
  }, [pendingHandoff, navigate]);

  useEffect(() => {
    if (aar) navigate('/provider/aar');
  }, [aar, navigate]);

  if (!scenario || !session) {
    return (
      <PageShell variant="fullscreen">
        <AppChrome role="provider" title="Simulation" />
        <main id="main-content" className="flex flex-1 items-center justify-center p-4">
          <Alert title="No session">No active session. Return to the lobby or wait for WIT deploy.</Alert>
        </main>
      </PageShell>
    );
  }

  const isActive = session.status === 'active';
  const activePatient =
    session.patients.find((p) => p.patient_id === session.active_patient_id) ??
    session.patients[0];
  const activeScenarioPatient =
    scenario.patients.find((p) => p.patient_id === activePatient?.patient_id) ??
    scenario.patients[0];
  const showFocusedClinical =
    activePatient && activeScenarioPatient && casualtyViewMode === 'focused';

  const dockPanel =
    dockTab === 'monitor' && showFocusedClinical ? (
      <>
        <ProviderVitalsBanner patient={activePatient} hideTiles />
        <ProviderBodyInjuryMap
          scenarioPatient={activeScenarioPatient}
          patientState={activePatient}
          sessionStartTime={session.start_time}
        />
        {activePatient && (
          <div className="mt-3 border-t border-ask-border pt-3">
            <PatientStatusPanel patients={[activePatient]} mode="provider" />
          </div>
        )}
      </>
    ) : dockTab === 'supply' ? (
      <ProviderSupplyPanel
        supplyLevel={scenarioConfig.supply}
        inventory={session.supply_inventory}
        statusNote={session.supply_status_note}
        compact
      />
    ) : null;

  const simBody = (
    <div className="provider-sim-frame">
      {endexWarning && (
        <Alert variant="critical" role="alert" title="ENDEX" className="shrink-0 rounded-none border-x-0">
          {endexWarning}
        </Alert>
      )}

      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-ask-border/80 bg-ask-surface/90 px-3 py-2 backdrop-blur-md">
        <Badge variant="muted">Turn {session.current_turn}</Badge>
        <span className="font-mono text-sm tabular-nums text-ask-accent" aria-live="polite">
          {formatTimer(elapsed)}
        </span>
      </div>

      {showFocusedClinical && activePatient && (
        <ProviderVitalsStrip patient={activePatient} />
      )}

      <CasualtySelector
        patients={session.patients}
        activePatientId={session.active_patient_id}
        viewMode={casualtyViewMode}
        onSelectPatient={setActivePatientId}
        onViewModeChange={setCasualtyViewMode}
      />

      {showFocusedClinical && !isMobile && (
        <div className="shrink-0 border-b border-ask-border/80">
          <button
            type="button"
            onClick={() => setShowDesktopClinical((v) => !v)}
            aria-expanded={showDesktopClinical}
            className="flex w-full items-center justify-between px-3 py-2 text-left font-mono text-[10px] uppercase tracking-widest text-ask-muted hover:bg-ask-surface-raised/50"
          >
            <span>Clinical picture (vitals & injury map)</span>
            <span className="text-ask-accent">{showDesktopClinical ? 'Hide' : 'Show'}</span>
          </button>
          {showDesktopClinical && (
            <div className="max-h-[58vh] overflow-y-auto">
              <ProviderVitalsBanner patient={activePatient} hideTiles />
              <ProviderBodyInjuryMap
                scenarioPatient={activeScenarioPatient}
                patientState={activePatient}
                sessionStartTime={session.start_time}
              />
            </div>
          )}
        </div>
      )}

      <main id="main-content" className="min-h-0 flex-1 overflow-hidden p-3">
        <PatientInteractionFeed
          feed={session.feed}
          activePatientId={session.active_patient_id}
          viewMode={casualtyViewMode}
        />
      </main>

      <ProviderActionBar onSubmit={submitAction} disabled={!isActive} />

      {isMobile ? (
        <ProviderActionDock activeTab={dockTab} onTabChange={setDockTab} panelContent={dockPanel} />
      ) : (
        <footer className="shrink-0 border-t border-ask-border bg-ask-surface/95 backdrop-blur-md">
          <button
            type="button"
            onClick={() => setShowDesktopSupply((v) => !v)}
            aria-expanded={showDesktopSupply}
            className="flex w-full items-center justify-between border-b border-ask-border/60 px-3 py-2 text-sm hover:bg-ask-surface-raised/40"
          >
            <span>Supplies</span>
            <span className="text-ask-accent">{showDesktopSupply ? 'Hide' : 'Show'}</span>
          </button>
          {showDesktopSupply && (
            <div className="max-h-32 overflow-y-auto px-3 py-2">
              <ProviderSupplyPanel
                supplyLevel={scenarioConfig.supply}
                inventory={session.supply_inventory}
                statusNote={session.supply_status_note}
                compact
              />
            </div>
          )}
          <button
            type="button"
            onClick={() => setShowDesktopObservations((v) => !v)}
            aria-expanded={showDesktopObservations}
            className="flex w-full items-center justify-between px-3 py-2 text-sm hover:bg-ask-surface-raised/40"
          >
            <span>Observations (unconfirmed)</span>
            <span className="text-ask-accent">{showDesktopObservations ? 'Hide' : 'Show'}</span>
          </button>
          {showDesktopObservations && activePatient && (
            <div className="max-h-32 overflow-y-auto border-t border-ask-border/60 px-3 py-2">
              <PatientStatusPanel patients={[activePatient]} mode="provider" />
            </div>
          )}
        </footer>
      )}
    </div>
  );

  if (isMobile) {
    return (
      <MobileAppShell
        showTabBar={false}
        header={
          <MobileHeader
            title={scenario.title}
            backTo={backTarget?.to ?? '/join'}
            backLabel={backTarget?.label}
          />
        }
        className="mobile-sim-shell"
      >
        {simBody}
      </MobileAppShell>
    );
  }

  return (
    <PageShell variant="fullscreen">
      <AppChrome role="provider" title={scenario.title} />
      {simBody}
    </PageShell>
  );
}
