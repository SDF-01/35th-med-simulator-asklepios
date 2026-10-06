import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PracticeHistoryPanel } from '@/components/practice/PracticeHistoryPanel';
import { Alert } from '@/components/ui/Alert';
import { AppChrome } from '@/components/ui/AppChrome';
import { Card } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { PageShell } from '@/components/ui/PageShell';
import { WitScenarioConfigPanel } from '@/components/wit/WitScenarioConfigPanel';
import { isCasualtyConfigValid } from '@/engines/casualtyTriageEngine';
import { isScenarioPlayable } from '@/engines/scenarioResolver';
import { useSimulationStore } from '@/store/simulationStore';
import { DEFAULT_SCENARIO_CONFIG, type ScenarioConfiguration } from '@/types/witConfig';
import { enableSoloMode } from '@/utils/soloMode';

/**
 * Offline single-device practice: configure a scenario locally, then run the
 * existing provider brief → simulation → AAR flow without a hub lobby.
 * Multi-role handoff chains are out of scope for solo v1.
 */
export function SoloPracticePage() {
  const navigate = useNavigate();
  const deployConfiguredScenario = useSimulationStore((s) => s.deployConfiguredScenario);
  const [config, setConfig] = useState<ScenarioConfiguration>({ ...DEFAULT_SCENARIO_CONFIG });

  const canStart =
    isScenarioPlayable(config.baseScenarioId) && isCasualtyConfigValid(config.casualties);

  function handleStart() {
    if (!canStart) return;
    enableSoloMode();
    deployConfiguredScenario(config);
    navigate('/provider/brief');
  }

  return (
    <PageShell>
      <AppChrome role="provider" title="Solo practice" />
      <div className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 sm:px-6">
        <PageHeader
          eyebrow="Solo practice"
          title="Practice without a lobby"
          description="Pick a scenario on this device. No exercise code or hub connection is required. Multi-role handoff chains are not included in solo mode yet."
          className="mb-6"
        />

        <Alert variant="info" className="mb-6" title="Training simulation only">
          This mode runs entirely in your browser for individual practice. It is not networked
          multiplayer and is not for operational or clinical use.
        </Alert>

        <Card padding="md" className="mb-4">
          <WitScenarioConfigPanel
            config={config}
            onChange={setConfig}
            onDeploy={handleStart}
            deployDisabled={!canStart}
            deployButtonLabel="Start solo practice"
          />
        </Card>

        <PracticeHistoryPanel className="mb-8" />
      </div>
    </PageShell>
  );
}
