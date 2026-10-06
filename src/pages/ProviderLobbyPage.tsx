import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert } from '@/components/ui/Alert';
import { AppChrome } from '@/components/ui/AppChrome';
import { Badge, StatusDot } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input, Select } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { PageHeader, SectionLabel } from '@/components/ui/PageHeader';
import { PageShell } from '@/components/ui/PageShell';
import { useDevice } from '@/context/DeviceContext';
import { HubSetupAlert } from '@/components/ui/HubSetupAlert';
import { MobileAppShell } from '@/components/mobile/MobileAppShell';
import { MobileHeader } from '@/components/mobile/MobileHeader';
import { useHubStatus } from '@/hooks/useHubStatus';
import { useLobbyCode } from '@/hooks/useLobbyCode';
import {
  getOrCreateDeviceId,
  getSavedProviderProfile,
  onExerciseUpdate,
  onProviderConnectionReplaced,
  onProviderDeployment,
  onSegmentNotification,
  registerProviderDevice,
  setProviderStatus,
  subscribeHubReconnect,
  updateProviderProfile,
} from '@/services/networkHub';
import type { ActiveExerciseState, SegmentNotificationPayload } from '@/types/exercise';
import type { DeviceStatus } from '@/types/device';
import {
  DEFAULT_PROVIDER_PROFILE,
  RESPONSE_OFFICE_GROUPS,
  getDepartmentLabel,
  getDepartmentOption,
  type ProviderProfile,
} from '@/types/providerProfile';
import { useSimulationStore } from '@/store/simulationStore';

function formatTimer(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function ProviderLobbyPage() {
  const navigate = useNavigate();
  const { formFactor } = useDevice();
  const isMobile = formFactor === 'mobile';
  const { connection } = useHubStatus();
  const lobbyCode = useLobbyCode({ redirectIfMissing: true });
  const setDeviceId = useSimulationStore((s) => s.setDeviceId);
  const loadDeployment = useSimulationStore((s) => s.loadDeployment);
  const [deviceId] = useState(getOrCreateDeviceId());
  const [profile, setProfile] = useState<ProviderProfile>(() => getSavedProviderProfile());
  const [connected, setConnected] = useState(false);
  const [deviceStatus, setDeviceStatus] = useState<DeviceStatus>('waiting');
  const [activeExercise, setActiveExercise] = useState<ActiveExerciseState | null>(null);
  const [exerciseStartedAt, setExerciseStartedAt] = useState<number | null>(null);
  const [standbyElapsed, setStandbyElapsed] = useState(0);
  const [segmentAlert, setSegmentAlert] = useState<SegmentNotificationPayload | null>(null);
  const [profileStatus, setProfileStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>(
    'idle',
  );
  const [profileError, setProfileError] = useState('');
  const [connectionReplacementNotice, setConnectionReplacementNotice] = useState('');

  useEffect(() => {
    if (!lobbyCode) return;
    setDeviceId(deviceId);

    const initialProfile = getSavedProviderProfile();
    const toRegister = {
      ...DEFAULT_PROVIDER_PROFILE,
      ...initialProfile,
      fullName: initialProfile.fullName.trim() || `Provider ${deviceId.slice(-4)}`,
    };

    function connectProvider() {
      setProviderStatus(deviceId, 'waiting');
      registerProviderDevice(toRegister)
        .then((device) => {
          setConnected(true);
          setDeviceStatus(device.status);
          setExerciseStartedAt(device.exerciseStartedAt ?? null);
          setProfile({
            fullName: device.providerName,
            hospitalDepartment: device.hospitalDepartment,
          });
        })
        .catch(() => setConnected(false));
    }

    const unsubReconnect = subscribeHubReconnect(connectProvider);

    const unsubDeploy = onProviderDeployment(({ scenario, scenarioConfig, exerciseMeta }) => {
      loadDeployment(scenario, scenarioConfig, exerciseMeta);
      setProviderStatus(deviceId, 'briefing');
      setDeviceStatus('briefing');
      setSegmentAlert(null);
      navigate('/provider/brief');
    });

    const unsubExercise = onExerciseUpdate(({ exercise, device }) => {
      setActiveExercise(exercise);
      if (device?.deviceId === deviceId) {
        setDeviceStatus(device.status);
        setExerciseStartedAt(device.exerciseStartedAt ?? exercise?.startedAt ?? null);
      }
    });

    const unsubNotify = onSegmentNotification((payload) => {
      setSegmentAlert(payload);
    });

    const unsubReplacement = onProviderConnectionReplaced((payload) => {
      setConnected(false);
      setConnectionReplacementNotice(
        payload.message ?? 'This provider session was replaced by a newly authorized connection.',
      );
    });

    return () => {
      unsubReconnect();
      unsubDeploy();
      unsubExercise();
      unsubNotify();
      unsubReplacement();
    };
  }, [deviceId, lobbyCode, setDeviceId, loadDeployment, navigate]);

  useEffect(() => {
    if (deviceStatus !== 'standby' || !exerciseStartedAt) return;
    const tick = () => setStandbyElapsed(Math.floor((Date.now() - exerciseStartedAt) / 1000));
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [deviceStatus, exerciseStartedAt]);

  async function handleSaveProfile() {
    setProfileStatus('saving');
    setProfileError('');

    try {
      const device = await updateProviderProfile(profile);
      setProfile({
        fullName: device.providerName,
        hospitalDepartment: device.hospitalDepartment,
      });
      setDeviceStatus(device.status);
      setProfileStatus('saved');
      setTimeout(() => setProfileStatus('idle'), 2000);
    } catch (err) {
      setProfileStatus('error');
      setProfileError(err instanceof Error ? err.message : 'Failed to save profile');
    }
  }

  const selectedDept = getDepartmentOption(profile.hospitalDepartment);
  const isStandby = deviceStatus === 'standby';
  const hubIssue = connection === 'online' ? 'ok' : import.meta.env.DEV ? 'dev' : 'offline';

  const lobbyContent = (
    <div className="lobby-stagger flex flex-col gap-4">
      {hubIssue !== 'ok' && hubIssue !== 'dev' && (
        <HubSetupAlert connection={connection} />
      )}

      {connectionReplacementNotice && (
        <Alert
          variant="caution"
          role="alert"
          title="Provider connection replaced"
        >
          {connectionReplacementNotice} Reopen the provider link on this device to reconnect.
        </Alert>
      )}

      {segmentAlert && (
        <Alert variant="success" title="Your segment is starting">
          {segmentAlert.message}
        </Alert>
      )}

      {isStandby && exerciseStartedAt ? (
        <div className="standby-hero">
          <p className="standby-hero__pulse">
            <StatusDot status="active" />
            Exercise live
          </p>
          <p className="text-sm text-ask-text-dim">
            {activeExercise?.title ?? 'Exercise'} · {getDepartmentLabel(profile.hospitalDepartment)}
          </p>
          <p className="standby-hero__timer" aria-live="polite">
            {formatTimer(standbyElapsed)}
          </p>
          <p className="mt-3 text-sm text-ask-muted">
            Stand by. You will be notified when a patient reaches your station.
          </p>
        </div>
      ) : (
        lobbyCode && (
          <Card padding="md" variant="accent" className="text-center exercise-code-card">
            <p className="text-xs uppercase tracking-widest text-ask-muted">Exercise code</p>
            <p className="exercise-code mt-2 text-2xl">{lobbyCode.split('').join(' ')}</p>
            <p className="mt-3 text-sm text-ask-muted">
              {connected ? 'Waiting for host to start…' : 'Connecting…'}
            </p>
          </Card>
        )
      )}

      <Card as="section" padding="lg">
        <SectionLabel accent className="mb-3">
          Your profile
        </SectionLabel>
        <div className="mb-4">
          <Label htmlFor="provider-name">Full name</Label>
          <Input
            id="provider-name"
            value={profile.fullName}
            onChange={(e) => {
              setProfile((prev) => ({ ...prev, fullName: e.target.value }));
              setProfileStatus('idle');
              setProfileError('');
            }}
            placeholder="Capt Jane Smith"
            autoComplete="name"
          />
        </div>
        <Button
          type="button"
          onClick={handleSaveProfile}
          disabled={profileStatus === 'saving' || !profile.fullName.trim()}
          className="w-full"
          size={isMobile ? 'lg' : 'md'}
        >
          {profileStatus === 'saving' ? 'Saving…' : 'Save & join lobby'}
        </Button>
        {profileStatus === 'saved' && (
          <Alert variant="success" className="mt-3" title="Saved">
            Profile updated.
          </Alert>
        )}
        {profileStatus === 'error' && (
          <Alert variant="critical" className="mt-3" title="Error">
            {profileError || 'Could not save profile.'}
          </Alert>
        )}

        <details className="profile-step mt-4">
          <summary>Response office (optional)</summary>
          <div className="profile-step__body">
            <Label htmlFor="response-office">Department</Label>
            <Select
              id="response-office"
              value={profile.hospitalDepartment}
              onChange={(e) => {
                setProfile((prev) => ({
                  ...prev,
                  hospitalDepartment: e.target.value as ProviderProfile['hospitalDepartment'],
                }));
                setProfileStatus('idle');
              }}
              className="mt-2"
            >
              {RESPONSE_OFFICE_GROUPS.map((group) => (
                <optgroup key={group.label} label={group.label}>
                  {group.options.map((office) => (
                    <option key={office.id} value={office.id}>
                      {office.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
            {selectedDept && (
              <p className="mt-2 text-xs text-ask-muted">{selectedDept.description}</p>
            )}
          </div>
        </details>
      </Card>

      <Card variant="accent" padding="md">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={isStandby ? 'delayed' : connected ? 'minimal' : 'muted'}>
            {isStandby ? 'Exercise live' : connected ? 'In lobby' : 'Offline'}
          </Badge>
          {connected && <StatusDot status="active" label="Connected" />}
        </div>
        <p className="mt-2 font-mono text-xs text-ask-muted">{deviceId}</p>
      </Card>
    </div>
  );

  if (isMobile) {
    return (
      <MobileAppShell
        header={
          <MobileHeader
            title={isStandby ? 'Exercise live' : 'In lobby'}
            subtitle={lobbyCode ?? undefined}
            backTo="/join"
          />
        }
      >
        <div className="mobile-page-pad">{lobbyContent}</div>
      </MobileAppShell>
    );
  }

  return (
    <PageShell>
      <AppChrome role="provider" title="Device registration" />
      <div className="mx-auto w-full max-w-lg flex-1 px-4 py-6 sm:px-6">
        <PageHeader
          eyebrow="Provider (Mobile)"
          title={isStandby ? 'Exercise live' : 'In lobby'}
          description={
            isStandby
              ? 'The host started the exercise. You will be notified when a patient reaches your station.'
              : connected
                ? 'Waiting for the host to start the exercise. Save your profile so WIT sees your role.'
                : 'Connecting to the exercise lobby…'
          }
          className="mb-6"
        />

        <main id="main-content" className="pb-8">{lobbyContent}</main>
      </div>
    </PageShell>
  );
}
