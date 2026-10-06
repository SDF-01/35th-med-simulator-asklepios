import { useMemo, useState } from 'react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { SectionLabel } from '@/components/ui/PageHeader';
import { EXERCISE_TEMPLATES, getEntrySegment, searchExerciseTemplates } from '@/content/exercises';
import { buildExerciseStartPayload, getDepartmentsInExercise } from '@/engines/exerciseEngine';
import { resolveBaseScenarioId } from '@/engines/scenarioResolver';
import { endActiveExercise, startExercise } from '@/services/networkHub';
import type { ActiveExerciseState } from '@/types/exercise';
import type { ProviderDevice } from '@/types/device';
import { getDepartmentLabel, type HospitalDepartmentId } from '@/types/providerProfile';
import type { ScenarioConfiguration } from '@/types/witConfig';

interface WitExercisePanelProps {
  devices: ProviderDevice[];
  activeExercise: ActiveExerciseState | null;
  config: ScenarioConfiguration;
  onExerciseStarted: () => void;
}

export function WitExercisePanel({
  devices,
  activeExercise,
  config,
  onExerciseStarted,
}: WitExercisePanelProps) {
  const [selectedTemplateId, setSelectedTemplateId] = useState(EXERCISE_TEMPLATES[0]?.id ?? '');
  const [catalogSearch, setCatalogSearch] = useState('');
  const [entryDeviceId, setEntryDeviceId] = useState<string>('');
  const [status, setStatus] = useState<'idle' | 'starting' | 'error'>('idle');
  const [error, setError] = useState('');

  const filteredTemplates = useMemo(
    () =>
      searchExerciseTemplates({
        categoryId: config.scenarioSelection.categoryId,
        eventTypeId: config.scenarioSelection.eventTypeId,
        query: catalogSearch,
      }),
    [catalogSearch, config.scenarioSelection.categoryId, config.scenarioSelection.eventTypeId],
  );

  const template =
    EXERCISE_TEMPLATES.find((t) => t.id === selectedTemplateId) ?? filteredTemplates[0];
  const entrySegment = template ? getEntrySegment(template) : undefined;

  const eligibleEntryDevices = useMemo(() => {
    if (!entrySegment) return [];
    return devices.filter(
      (d) =>
        d.hospitalDepartment === entrySegment.department &&
        (d.status === 'waiting' || d.status === 'standby'),
    );
  }, [devices, entrySegment]);

  const standbyByDepartment = useMemo(() => {
    if (!template) return [];
    const departments = getDepartmentsInExercise(template);
    return departments.map((dept: HospitalDepartmentId) => ({
      department: dept,
      label: getDepartmentLabel(dept),
      count: devices.filter(
        (d) => d.hospitalDepartment === dept && (d.status === 'waiting' || d.status === 'standby'),
      ).length,
    }));
  }, [devices, template]);

  async function handleStartExercise() {
    if (!template || !entryDeviceId) return;

    setStatus('starting');
    setError('');

    try {
      const entryDevice = devices.find((d) => d.deviceId === entryDeviceId);
      if (!entryDevice) throw new Error('Entry device not found');

      const deployConfig = {
        ...config,
        scenarioSelection: template.scenarioSelection,
        baseScenarioId: resolveBaseScenarioId(
          template.scenarioSelection,
          entryDevice.hospitalDepartment,
        ),
      };

      const payload = buildExerciseStartPayload(
        template.id,
        entryDeviceId,
        entryDevice.providerName,
        entryDevice.hospitalDepartment,
        deployConfig,
      );

      const result = await startExercise(payload);
      if (!result.ok) throw new Error(result.error ?? 'Failed to start exercise');

      onExerciseStarted();
      setStatus('idle');
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Could not start exercise');
    }
  }

  function handleEndExercise() {
    endActiveExercise();
    onExerciseStarted();
  }

  if (activeExercise && activeExercise.templateId !== 'ad_hoc') {
    return (
      <Card padding="lg" className="mb-6">
        <SectionLabel accent className="mb-1">
          Active exercise
        </SectionLabel>
        <h3 className="mb-2 text-lg font-semibold text-ask-text">{activeExercise.title}</h3>
        <p className="mb-4 text-sm text-ask-muted">
          Exercise ID {activeExercise.exerciseId} · Started{' '}
          {new Date(activeExercise.startedAt).toLocaleTimeString()} ·{' '}
          {activeExercise.participantDeviceIds.length} device(s) linked
        </p>
        <Alert variant="info" className="mb-4" title="Chain-of-care in progress">
          Standby providers see a running timer until their segment is handed off. When a segment
          completes, the active provider selects the next response office.
        </Alert>
        <Button variant="danger" onClick={handleEndExercise}>
          End exercise for all participants
        </Button>
      </Card>
    );
  }

  return (
    <Card padding="lg" className="mb-6">
      <SectionLabel accent className="mb-1">
        Multi-role exercises
      </SectionLabel>
      <h3 className="mb-2 text-lg font-semibold text-ask-text">Start chain-of-care evolution</h3>
      <p className="mb-4 text-sm leading-relaxed text-ask-muted">
        Deploy a coordinated exercise across Home Station Medical Response offices. Non-entry
        departments enter standby with a timer until they receive a handoff notification.
      </p>

      <div className="mb-4">
        <label htmlFor="catalog-search" className="mb-1 block text-sm font-medium text-ask-text">
          Exercise catalog code
        </label>
        <Input
          id="catalog-search"
          value={catalogSearch}
          onChange={(e) => setCatalogSearch(e.target.value.toUpperCase())}
          placeholder="Search 6-character code or title"
          className="font-mono tracking-widest"
        />
      </div>

      <div className="mb-4">
        <label htmlFor="exercise-template" className="mb-1 block text-sm font-medium text-ask-text">
          Exercise template ({filteredTemplates.length})
        </label>
        <select
          id="exercise-template"
          value={template?.id ?? ''}
          onChange={(e) => {
            setSelectedTemplateId(e.target.value);
            setEntryDeviceId('');
          }}
          className="w-full rounded-ask-md border border-ask-border bg-ask-surface px-3 py-2 text-sm text-ask-text"
        >
          {filteredTemplates.map((item) => (
            <option key={item.id} value={item.id}>
              {item.catalogId}: {item.title}
            </option>
          ))}
        </select>
        {template && (
          <>
            <p className="exercise-code mt-3 text-center text-lg">{template.catalogId.split('').join(' ')}</p>
            <p className="mt-2 text-xs leading-relaxed text-ask-muted">{template.description}</p>
            <p className="mt-1 text-xs text-ask-muted">
              {template.chainArchetype} · {template.difficulty} · ~{template.estimatedMinutes} min ·{' '}
              {template.minProviders}+ providers
            </p>
          </>
        )}
      </div>

      {template && (
        <div className="mb-4 rounded-ask-md border border-ask-border/60 bg-ask-surface/30 p-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ask-accent">
            Segment chain
          </p>
          <ol className="space-y-1 text-sm text-ask-text-dim">
            {template.segments.map((segment, index) => (
              <li key={segment.id}>
                {index + 1}. {getDepartmentLabel(segment.department)}: {segment.label}
                {segment.isEntryPoint ? ' (entry)' : ''}
                {segment.isTerminal ? ' (final)' : ''}
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="mb-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ask-muted">
          Standby readiness
        </p>
        <ul className="grid gap-1 text-sm text-ask-text-dim sm:grid-cols-2">
          {standbyByDepartment.map((row) => (
            <li key={row.department}>
              {row.label}: {row.count} device(s)
            </li>
          ))}
        </ul>
      </div>

      {entrySegment && (
        <div className="mb-4">
          <label htmlFor="entry-device" className="mb-1 block text-sm font-medium text-ask-text">
            Entry device: {getDepartmentLabel(entrySegment.department)}
          </label>
          <select
            id="entry-device"
            value={entryDeviceId}
            onChange={(e) => setEntryDeviceId(e.target.value)}
            className="w-full rounded-ask-md border border-ask-border bg-ask-surface px-3 py-2 text-sm text-ask-text"
          >
            <option value="">Select provider device...</option>
            {eligibleEntryDevices.map((device) => (
              <option key={device.deviceId} value={device.deviceId}>
                {device.displayName} ({device.deviceId})
              </option>
            ))}
          </select>
          {eligibleEntryDevices.length === 0 && (
            <p className="mt-2 text-xs text-ask-caution">
              No {getDepartmentLabel(entrySegment.department)} device is waiting on the network.
            </p>
          )}
        </div>
      )}

      {status === 'error' && (
        <Alert variant="critical" className="mb-4" role="alert" title="Could not start">
          {error}
        </Alert>
      )}

      <Button
        onClick={handleStartExercise}
        disabled={!entryDeviceId || status === 'starting' || eligibleEntryDevices.length === 0}
      >
        {status === 'starting' ? 'Starting exercise...' : 'Start exercise'}
      </Button>
    </Card>
  );
}
