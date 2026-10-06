import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert } from '@/components/ui/Alert';
import { AppChrome } from '@/components/ui/AppChrome';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { PageHeader, SectionLabel } from '@/components/ui/PageHeader';
import { PageShell } from '@/components/ui/PageShell';
import { buildHandoffDeployment, listHandoffTargetLabels } from '@/engines/exerciseEngine';
import {
  executeHandoff,
  getOrCreateDeviceId,
  returnToStandby,
} from '@/services/networkHub';
import { useSimulationStore } from '@/store/simulationStore';
import type { HospitalDepartmentId } from '@/types/providerProfile';
import { getDepartmentLabel } from '@/types/providerProfile';

function formatTimer(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function ProviderHandoffPage() {
  const navigate = useNavigate();
  const deviceId = useSimulationStore((s) => s.deviceId);
  const exerciseMeta = useSimulationStore((s) => s.exerciseMeta);
  const pendingHandoff = useSimulationStore((s) => s.pendingHandoff);
  const scenarioConfig = useSimulationStore((s) => s.scenarioConfig);
  const clearForStandby = useSimulationStore((s) => s.clearForStandby);
  const [selectedDepartment, setSelectedDepartment] = useState<HospitalDepartmentId | null>(null);
  const [status, setStatus] = useState<'idle' | 'submitting' | 'error'>('idle');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!pendingHandoff || !exerciseMeta) {
      navigate('/provider', { replace: true });
    }
  }, [pendingHandoff, exerciseMeta, navigate]);

  if (!pendingHandoff || !exerciseMeta) {
    return null;
  }

  const targets = listHandoffTargetLabels(exerciseMeta.templateId, exerciseMeta.segmentId);

  async function handleHandoff() {
    if (!selectedDepartment || !pendingHandoff || !exerciseMeta) return;

    setStatus('submitting');
    setError('');

    try {
      const targetDeployment = buildHandoffDeployment(
        exerciseMeta.templateId,
        exerciseMeta.segmentId,
        selectedDepartment,
        exerciseMeta.exerciseId,
        exerciseMeta.exerciseStartedAt,
        pendingHandoff,
        getDepartmentLabel(selectedDepartment),
        scenarioConfig,
      );

      await executeHandoff({
        fromDeviceId: deviceId ?? getOrCreateDeviceId(),
        exerciseId: exerciseMeta.exerciseId,
        targetDepartment: selectedDepartment,
        patientSnapshot: pendingHandoff,
        targetDeployment,
      });

      clearForStandby();
      await returnToStandby(deviceId ?? getOrCreateDeviceId());
      navigate('/provider', { replace: true });
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Handoff failed');
    }
  }

  return (
    <PageShell>
      <AppChrome role="provider" title="Patient handoff" />
      <div className="mx-auto w-full max-w-lg flex-1 px-4 py-6 sm:px-6">
        <PageHeader
          eyebrow={`${exerciseMeta.templateTitle} · Segment complete`}
          title="Select handoff destination"
          description="Your segment objectives are met. Choose the next response office to receive this patient."
          className="mb-6"
        />

        <main id="main-content" className="flex flex-col gap-4 pb-8">
          <Card padding="md">
            <SectionLabel accent className="mb-2">
              Handoff summary
            </SectionLabel>
            <p className="text-sm leading-relaxed text-ask-text-dim">{pendingHandoff.presentationSummary}</p>
            <dl className="mt-4 space-y-2 text-sm">
              <div>
                <dt className="text-ask-muted">Vitals</dt>
                <dd>{pendingHandoff.vitalsSummary}</dd>
              </div>
              <div>
                <dt className="text-ask-muted">Injuries / findings</dt>
                <dd>{pendingHandoff.injuriesSummary}</dd>
              </div>
              <div>
                <dt className="text-ask-muted">Care completed</dt>
                <dd>{pendingHandoff.completedCareSummary.join('; ')}</dd>
              </div>
            </dl>
          </Card>

          <Card as="section" padding="lg" aria-labelledby="handoff-targets">
            <SectionLabel className="mb-3">Next response office</SectionLabel>
            <div className="flex flex-col gap-2">
              {targets.map((target) => (
                <button
                  key={target.id}
                  type="button"
                  onClick={() => setSelectedDepartment(target.id)}
                  className={[
                    'rounded-ask-md border px-4 py-3 text-left transition-colors',
                    selectedDepartment === target.id
                      ? 'border-ask-accent bg-ask-accent-wash text-ask-text'
                      : 'border-ask-border bg-ask-surface/40 text-ask-text-dim hover:border-ask-accent/50',
                  ].join(' ')}
                >
                  <span className="font-medium">{target.label}</span>
                  <span className="mt-1 block text-xs text-ask-muted">
                    Standby providers in this office will be notified when you confirm.
                  </span>
                </button>
              ))}
            </div>

            {status === 'error' && (
              <Alert variant="critical" className="mt-4" role="alert" title="Handoff failed">
                {error}
              </Alert>
            )}

            <Button
              type="button"
              className="mt-5 w-full"
              disabled={!selectedDepartment || status === 'submitting'}
              onClick={handleHandoff}
            >
              {status === 'submitting' ? 'Sending handoff...' : 'Confirm handoff'}
            </Button>
          </Card>

          <p className="text-center text-xs text-ask-muted">
            Exercise elapsed: {formatTimer(Math.floor((Date.now() - exerciseMeta.exerciseStartedAt) / 1000))}
          </p>
        </main>
      </div>
    </PageShell>
  );
}
