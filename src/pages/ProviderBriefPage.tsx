import { useNavigate } from 'react-router-dom';
import { Alert } from '@/components/ui/Alert';
import { AppChrome } from '@/components/ui/AppChrome';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { PageHeader, SectionLabel } from '@/components/ui/PageHeader';
import { PageShell } from '@/components/ui/PageShell';
import { ProviderSupplyPanel } from '@/components/simulation/ProviderSupplyPanel';
import { sectionLabels } from '@/content/scenarioSeeds';
import { DYNAMIC_TRIAGE_OPTIONS, TRIAGE_LABELS } from '@/engines/casualtyTriageEngine';
import { buildSupplyInventory, getSupplyLimitsSummary } from '@/engines/supplyEngine';
import { SUPPLY_OPTIONS } from '@/types/witConfig';
import { setProviderStatus } from '@/services/networkHub';
import { useSimulationStore } from '@/store/simulationStore';
import { isSoloMode } from '@/utils/soloMode';

export function ProviderBriefPage() {
  const navigate = useNavigate();
  const scenario = useSimulationStore((s) => s.scenario);
  const scenarioConfig = useSimulationStore((s) => s.scenarioConfig);
  const deviceId = useSimulationStore((s) => s.deviceId);
  const startSession = useSimulationStore((s) => s.startSession);

  if (!scenario) {
    return (
      <PageShell>
        <AppChrome role="provider" title="Mission brief" />
        <main id="main-content" className="flex flex-1 items-center justify-center px-4 py-12">
          <Alert title="No scenario">
            {isSoloMode()
              ? 'No scenario loaded. Return to Solo practice and start a scenario.'
              : 'No scenario loaded. Wait for WIT to deploy.'}
          </Alert>
        </main>
      </PageShell>
    );
  }

  function beginSimulation() {
    startSession();
    if (deviceId) setProviderStatus(deviceId, 'in_simulation');
    navigate('/provider/simulation');
  }

  const { casualties } = scenarioConfig;
  const dynamicTriageLabel =
    DYNAMIC_TRIAGE_OPTIONS.find((o) => o.id === casualties.dynamicTriage)?.label ??
    casualties.dynamicTriage;
  const inventory = buildSupplyInventory(scenarioConfig.supply, casualties.total);
  const supplyNote = getSupplyLimitsSummary(scenarioConfig.supply, inventory);
  const supplyLabel =
    SUPPLY_OPTIONS.find((o) => o.id === scenarioConfig.supply)?.label ?? scenarioConfig.supply;

  return (
    <PageShell>
      <AppChrome role="provider" title="Mission brief" />
      <div className="mx-auto w-full max-w-lg flex-1 px-4 py-6 sm:px-6">
        <main id="main-content" className="pb-8">
          <PageHeader eyebrow="Mission Brief" title={scenario.title} className="mb-6" />

          <Card as="section" padding="md" className="mb-4">
            <p className="mb-4 text-sm leading-relaxed">{scenario.operational_context.narrative}</p>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-xs uppercase text-ask-muted">Section</dt>
                <dd>{sectionLabels[scenario.target_section]}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-ask-muted">Casualties</dt>
                <dd className="font-mono">{casualties.total}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-ask-muted">Treatment window</dt>
                <dd className="font-mono">{scenarioConfig.constraints.treatment_time_minutes} min</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-ask-muted">Supply</dt>
                <dd>{supplyLabel}</dd>
              </div>
            </dl>
          </Card>

          <div className="mb-4">
            <ProviderSupplyPanel
              supplyLevel={scenarioConfig.supply}
              inventory={inventory}
              statusNote={supplyNote}
            />
          </div>

          <Card as="section" padding="md" className="mb-4">
            <SectionLabel accent className="mb-3">
              Triage Load
            </SectionLabel>
            <dl className="grid grid-cols-3 gap-3">
              {(Object.keys(TRIAGE_LABELS) as Array<keyof typeof TRIAGE_LABELS>).map((key) => (
                <div key={key}>
                  <dt className="text-xs text-ask-muted">{TRIAGE_LABELS[key]}</dt>
                  <dd className="font-mono text-lg">{casualties.triage[key]}</dd>
                </div>
              ))}
            </dl>
            {casualties.dynamicTriage !== 'static' && (
              <Alert variant="caution" className="mt-4" title="Dynamic triage">
                {dynamicTriageLabel}. Expect category changes during the evolution.
              </Alert>
            )}
          </Card>

          {scenarioConfig.dispositionRequirements && (
            <Alert variant="caution" className="mb-4" title="Requirements">
              {scenarioConfig.dispositionRequirements}
            </Alert>
          )}

          <p className="mb-6 text-xs leading-relaxed text-ask-muted">
            You are at the bedside. Assess through examination and orders. Supplies are limited.
          </p>

          <Button onClick={beginSimulation} size="lg" className="w-full">
            Begin Evolution
          </Button>
        </main>
      </div>
    </PageShell>
  );
}
