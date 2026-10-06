import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { SectionLabel } from '@/components/ui/PageHeader';
import type { ActiveExerciseState } from '@/types/exercise';
import type { ProviderDevice } from '@/types/device';

interface WitExerciseControlBarProps {
  activeExercise: ActiveExerciseState | null;
  selectedDevice: ProviderDevice | null;
  canStart: boolean;
  canDeploy: boolean;
  deployHint?: string;
  starting: boolean;
  deploying: boolean;
  startError?: string;
  onStart: () => void;
  onDeploy: () => void;
  onEndExercise?: () => void;
}

export function WitExerciseControlBar({
  activeExercise,
  selectedDevice,
  canStart,
  canDeploy,
  deployHint,
  starting,
  deploying,
  startError,
  onStart,
  onDeploy,
  onEndExercise,
}: WitExerciseControlBarProps) {
  const deviceReady =
    selectedDevice &&
    (selectedDevice.status === 'waiting' || selectedDevice.status === 'standby');

  return (
    <Card padding="lg" className="mb-6 border-ask-accent/30">
      <SectionLabel accent className="mb-1">
        Exercise control
      </SectionLabel>
      <h3 className="mb-2 text-lg font-semibold text-ask-text">Start, then deploy</h3>
      <p className="mb-4 text-sm leading-relaxed text-ask-muted">
        Step 1: Start the exercise so providers enter standby. Step 2: Deploy the configured scenario
        to the selected device.
      </p>

      {activeExercise ? (
        <Alert variant="success" className="mb-4" title="Exercise started">
          {activeExercise.title} · ID {activeExercise.exerciseId} ·{' '}
          {new Date(activeExercise.startedAt).toLocaleTimeString()}
        </Alert>
      ) : (
        <Alert variant="info" className="mb-4" title="Exercise not started">
          Providers are in the lobby. Start the exercise before deploying a scenario.
        </Alert>
      )}

      {startError && (
        <Alert variant="critical" className="mb-4" role="alert" title="Could not start">
          {startError}
        </Alert>
      )}

      {selectedDevice && !deviceReady && (
        <Alert variant="caution" className="mb-4" title="Device not deployable">
          {selectedDevice.displayName} is {selectedDevice.status.replace(/_/g, ' ')}. Select a
          waiting or standby device, or reset after the prior evolution.
        </Alert>
      )}

      <div className="flex flex-wrap gap-3">
        <Button
          variant="secondary"
          onClick={onStart}
          disabled={!canStart || starting || Boolean(activeExercise)}
        >
          {starting ? 'Starting…' : activeExercise ? 'Exercise started' : 'Start exercise'}
        </Button>
        <Button onClick={onDeploy} disabled={!canDeploy || deploying}>
          {deploying ? 'Deploying…' : 'Deploy exercise'}
        </Button>
        {activeExercise && onEndExercise && (
          <Button variant="ghost" onClick={onEndExercise}>
            End exercise
          </Button>
        )}
      </div>

      {deployHint && (
        <p className="mt-3 text-xs text-ask-muted">{deployHint}</p>
      )}
    </Card>
  );
}
