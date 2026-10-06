import { io, type Socket } from 'socket.io-client';
import type { Scenario } from '@/types';
import type { HubHealthResponse } from '@/types/hub';
import type { DeploymentPayload, ProviderDevice, SessionSyncPayload } from '@/types/device';
import type { ProviderProfile } from '@/types/providerProfile';
import {
  DEFAULT_PROVIDER_PROFILE,
  normalizeHospitalDepartmentId,
} from '@/types/providerProfile';
import type { ScenarioConfiguration } from '@/types/witConfig';
import type {
  ExerciseDeploymentMeta,
  HandoffRequestPayload,
  SegmentNotificationPayload,
  StartExercisePayload,
} from '@/types/exercise';
import { assertHubAvailableForLobby } from '@/utils/hubMessages';
import { resolveHubUrl } from '@/utils/hubUrl';
import { normalizeLobbyCode } from '@/utils/lobbyCode';
import {
  getControllerCapability,
  getProviderCapability,
  saveControllerCapability,
  saveProviderCapability,
} from '@/utils/lobbyCapability';

const DISPLAY_NAME_KEY = 'asklepios_display_name';
const PROFILE_KEY = 'asklepios_provider_profile';

let socket: Socket | null = null;
let activeLobbyCode: string | null = null;
let witJoinHandler: (() => void) | null = null;
let commanderJoinHandler: (() => void) | null = null;
const providerReconnectHandlers = new Set<() => void>();
const hubAuthorizationHandlers = new Set<(message: string) => void>();


function reportHubAuthorizationError(error: unknown): void {
  const message = error instanceof Error ? error.message : String(error);
  for (const handler of hubAuthorizationHandlers) handler(message);
}

export function subscribeHubAuthorizationErrors(
  handler: (message: string) => void,
): () => void {
  hubAuthorizationHandlers.add(handler);
  return () => hubAuthorizationHandlers.delete(handler);
}

function emitAuthorized<TPayload extends object>(
  event: string,
  payloadFactory: () => TPayload,
): void {
  try {
    void emitWithAck<TPayload, { ok: boolean; error?: string }>(event, payloadFactory())
      .catch(reportHubAuthorizationError);
  } catch (error) {
    reportHubAuthorizationError(error);
  }
}

export function setActiveLobbyCode(code: string | null): void {
  activeLobbyCode = code ? normalizeLobbyCode(code) : null;
}

export function getActiveLobbyCode(): string | null {
  return activeLobbyCode;
}

function requireLobbyCode(): string {
  if (!activeLobbyCode) {
    throw new Error('Join an exercise lobby with a code before connecting.');
  }
  return activeLobbyCode;
}


function requireControllerCapability(): string {
  const lobbyCode = requireLobbyCode();
  const capability = getControllerCapability(lobbyCode);
  if (!capability) {
    throw new Error('This command console requires the secure controller link from the exercise host.');
  }
  return capability;
}

function withController<T extends object>(payload: T): T & { lobbyCode: string; controllerCapability: string } {
  return { ...payload, lobbyCode: requireLobbyCode(), controllerCapability: requireControllerCapability() };
}

function withProvider<T extends object>(deviceId: string, payload: T): T & { lobbyCode: string; providerCapability?: string } {
  const lobbyCode = requireLobbyCode();
  return {
    ...payload,
    lobbyCode,
    providerCapability: getProviderCapability(lobbyCode, deviceId) ?? undefined,
  };
}

function createSocket(): Socket {
  const hubUrl = resolveHubUrl();
  const useWebsocketOnly = import.meta.env.PROD && !import.meta.env.VITE_HUB_URL?.trim();

  const instance = io(hubUrl, {
    path: '/socket.io',
    transports: useWebsocketOnly ? ['websocket'] : ['websocket', 'polling'],
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 8000,
    timeout: 12_000,
    autoConnect: true,
  });

  instance.on('connect', () => {
    witJoinHandler?.();
    commanderJoinHandler?.();
    for (const handler of providerReconnectHandlers) {
      handler();
    }
  });

  return instance;
}

function getSocket(): Socket {
  if (!socket) {
    socket = createSocket();
  }
  return socket;
}

export function getHubUrl(): string {
  return resolveHubUrl();
}

export async function fetchHubHealth(): Promise<HubHealthResponse | null> {
  try {
    const response = await fetch(`${resolveHubUrl()}/api/health`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) return null;
    return (await response.json()) as HubHealthResponse;
  } catch {
    return null;
  }
}

export function pingHub(): Promise<boolean> {
  const s = getSocket();
  if (!s.connected) {
    return Promise.resolve(false);
  }

  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(false), 5000);
    s.emit('hub:ping', (response: { ok?: boolean }) => {
      clearTimeout(timer);
      resolve(Boolean(response?.ok));
    });
  });
}

export function subscribeHubReconnect(handler: () => void): () => void {
  providerReconnectHandlers.add(handler);
  const s = getSocket();
  if (s.connected) {
    handler();
  }
  return () => {
    providerReconnectHandlers.delete(handler);
  };
}

export function getOrCreateDeviceId(): string {
  const key = 'asklepios_device_id';
  let id = localStorage.getItem(key);
  if (!id) {
    const bytes = new Uint8Array(6);
    globalThis.crypto.getRandomValues(bytes);
    id = `DEV-${Array.from(bytes, (value) => value.toString(36).padStart(2, '0')).join('').slice(0, 8).toUpperCase()}`;
    localStorage.setItem(key, id);
  }
  return id;
}

export function getSavedDisplayName(): string {
  return localStorage.getItem(DISPLAY_NAME_KEY) ?? '';
}

export function saveDisplayName(name: string): void {
  localStorage.setItem(DISPLAY_NAME_KEY, name);
}

export function getSavedProviderProfile(): ProviderProfile {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (!raw) {
      return {
        ...DEFAULT_PROVIDER_PROFILE,
        fullName: getSavedDisplayName(),
      };
    }
    const parsed = JSON.parse(raw) as ProviderProfile;
    return {
      ...DEFAULT_PROVIDER_PROFILE,
      ...parsed,
      hospitalDepartment: normalizeHospitalDepartmentId(parsed.hospitalDepartment),
    };
  } catch {
    return {
      ...DEFAULT_PROVIDER_PROFILE,
      fullName: getSavedDisplayName(),
    };
  }
}

export function saveProviderProfile(profile: ProviderProfile): void {
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  if (profile.fullName.trim()) {
    saveDisplayName(profile.fullName.trim());
  }
}

function emitWithAck<TPayload, TResponse>(
  event: string,
  payload: TPayload,
  timeoutMs = 8000,
): Promise<TResponse> {
  const s = getSocket();

  return new Promise((resolve, reject) => {
    if (!s.connected) {
      reject(new Error('Not connected to exercise hub'));
      return;
    }

    const timer = setTimeout(() => reject(new Error('Network hub did not respond')), timeoutMs);

    s.emit(event, payload, (response: TResponse & { ok?: boolean; error?: string }) => {
      clearTimeout(timer);
      if (response && 'ok' in response && response.ok === false) {
        reject(new Error(response.error ?? 'Request failed'));
        return;
      }
      resolve(response);
    });
  });
}

export async function createExerciseLobby(): Promise<{ code: string; createdAt: number; controllerCapability: string }> {
  assertHubAvailableForLobby();

  try {
    const response = await fetch(`${resolveHubUrl()}/api/lobbies`, {
      method: 'POST',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) {
      throw new Error('Could not create exercise lobby');
    }
    const data = (await response.json()) as { ok: boolean; code?: string; createdAt?: number; controllerCapability?: string };
    if (!data.ok || !data.code || !data.controllerCapability) {
      throw new Error('Could not create exercise lobby');
    }
    saveControllerCapability(data.code, data.controllerCapability);
    return { code: data.code, createdAt: data.createdAt ?? Date.now(), controllerCapability: data.controllerCapability };
  } catch {
    return emitWithAck<Record<string, never>, { ok: boolean; code?: string; createdAt?: number; controllerCapability?: string }>(
      'lobby:create',
      {},
    ).then((res) => {
      if (!res.code || !res.controllerCapability) throw new Error('Could not create exercise lobby');
      saveControllerCapability(res.code, res.controllerCapability);
      return { code: res.code, createdAt: res.createdAt ?? Date.now(), controllerCapability: res.controllerCapability };
    });
  }
}

export async function validateExerciseLobby(code: string): Promise<boolean> {
  const normalized = normalizeLobbyCode(code);
  if (!normalized) return false;
  try {
    const response = await fetch(`${resolveHubUrl()}/api/lobbies/${encodeURIComponent(normalized)}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) return false;
    const data = (await response.json()) as { ok?: boolean };
    return Boolean(data.ok);
  } catch {
    return false;
  }
}

export function registerProviderDevice(profile: ProviderProfile): Promise<ProviderDevice> {
  const deviceId = getOrCreateDeviceId();
  const name = profile.fullName.trim() || getSavedDisplayName() || `Provider ${deviceId.slice(-4)}`;

  return emitWithAck<
    {
      deviceId: string;
      displayName: string;
      providerName: string;
      hospitalDepartment: ProviderProfile['hospitalDepartment'];
      userAgent: string;
      providerCapability?: string;
    },
    { ok: boolean; device: ProviderDevice; providerCapability?: string }
  >('provider:register', withProvider(deviceId, {
    deviceId,
    displayName: name,
    providerName: name,
    hospitalDepartment: profile.hospitalDepartment,
    userAgent: navigator.userAgent,
  })).then((res) => {
    saveProviderProfile({ fullName: name, hospitalDepartment: profile.hospitalDepartment });
    if (res.providerCapability) {
      saveProviderCapability(requireLobbyCode(), deviceId, res.providerCapability);
    }
    return res.device;
  });
}

export function updateProviderProfile(profile: ProviderProfile): Promise<ProviderDevice> {
  const deviceId = getOrCreateDeviceId();
  const trimmed = profile.fullName.trim();

  if (!trimmed) {
    return Promise.reject(new Error('Enter your name first'));
  }

  return emitWithAck<
    {
      deviceId: string;
      providerName: string;
      hospitalDepartment: ProviderProfile['hospitalDepartment'];
    },
    { ok: boolean; device: ProviderDevice }
  >('provider:update-profile', withProvider(deviceId, {
    deviceId,
    providerName: trimmed,
    hospitalDepartment: profile.hospitalDepartment,
  })).then((res) => {
    saveProviderProfile(profile);
    return res.device;
  });
}

export function updateProviderDisplayName(displayName: string): Promise<ProviderDevice> {
  const deviceId = getOrCreateDeviceId();
  const trimmed = displayName.trim();

  if (!trimmed) {
    return Promise.reject(new Error('Enter a display name first'));
  }

  return emitWithAck<
    { deviceId: string; displayName: string },
    { ok: boolean; device: ProviderDevice }
  >('provider:update-name', withProvider(deviceId, { deviceId, displayName: trimmed })).then((res) => {
    saveDisplayName(trimmed);
    return res.device;
  });
}

export function joinWitDashboard(
  onDevices: (devices: ProviderDevice[]) => void,
  onAuthorizationError?: (message: string) => void,
): () => void {
  const s = getSocket();
  const join = () => {
    if (!activeLobbyCode) return;
    const controllerCapability = getControllerCapability(activeLobbyCode);
    if (!controllerCapability) {
      onAuthorizationError?.('Open the secure controller link created by the exercise host.');
      return;
    }
    s.emit(
      'wit:join',
      { lobbyCode: activeLobbyCode, controllerCapability },
      (response: { ok?: boolean; error?: string }) => {
        if (!response?.ok) {
          onAuthorizationError?.(response?.error ?? 'Controller authorization failed.');
        } else {
          onAuthorizationError?.('');
        }
      },
    );
  };

  join();
  s.on('devices:update', onDevices);
  witJoinHandler = join;

  return () => {
    s.off('devices:update', onDevices);
    if (witJoinHandler === join) witJoinHandler = null;
  };
}

export function deployToDevice(payload: DeploymentPayload): void {
  emitAuthorized('wit:deploy', () => withController(payload));
}

export function armLobbyExercise(
  title?: string,
): Promise<{ ok: boolean; error?: string; exerciseId?: string }> {
  return emitWithAck<{ title?: string }, { ok: boolean; error?: string; exerciseId?: string }>(
    'wit:arm-exercise',
    withController({ title }),
  );
}

export function startExercise(payload: StartExercisePayload): Promise<{ ok: boolean; error?: string }> {
  return emitWithAck<StartExercisePayload, { ok: boolean; error?: string }>(
    'wit:start-exercise',
    withController(payload),
  );
}

export function executeHandoff(
  payload: HandoffRequestPayload,
): Promise<{ ok: boolean; targetDeviceId?: string; error?: string }> {
  return emitWithAck<
    HandoffRequestPayload,
    { ok: boolean; targetDeviceId?: string; error?: string }
  >('provider:execute-handoff', withProvider(payload.fromDeviceId, payload));
}

export function endActiveExercise(): void {
  emitAuthorized('wit:end-exercise', () => withController({}));
}

export function returnToStandby(deviceId: string): Promise<{ ok: boolean; error?: string }> {
  return emitWithAck<{ deviceId: string }, { ok: boolean; error?: string }>(
    'provider:return-standby',
    withProvider(deviceId, { deviceId }),
  );
}

export function onExerciseUpdate(
  handler: (payload: import('@/types/exercise').ExerciseUpdatePayload) => void,
): () => void {
  const s = getSocket();
  s.on('exercise:update', handler);
  return () => s.off('exercise:update', handler);
}

export function onSegmentNotification(
  handler: (payload: SegmentNotificationPayload) => void,
): () => void {
  const s = getSocket();
  s.on('provider:segment-notification', handler);
  return () => s.off('provider:segment-notification', handler);
}

export function onProviderDeployment(
  handler: (payload: {
    scenario: Scenario;
    scenarioConfig: ScenarioConfiguration;
    exerciseMeta?: ExerciseDeploymentMeta;
  }) => void,
): () => void {
  const s = getSocket();
  s.on('provider:deployment', handler);
  return () => s.off('provider:deployment', handler);
}

export function setProviderStatus(deviceId: string, status: ProviderDevice['status']): void {
  emitAuthorized('provider:status', () => withProvider(deviceId, { deviceId, status }));
}

export function requestDeviceSession(deviceId: string): void {
  emitAuthorized('wit:request-session', () => withController({ deviceId }));
}

export function syncSession(payload: SessionSyncPayload): void {
  emitAuthorized('session:sync', () => withProvider(payload.deviceId, payload));
}

export function onSessionUpdate(handler: (payload: SessionSyncPayload) => void): () => void {
  const s = getSocket();
  s.on('session:update', handler);
  return () => s.off('session:update', handler);
}

export function endExercise(deviceId: string): void {
  emitAuthorized('wit:endex', () => withController({ deviceId }));
}

export function onProviderConnectionReplaced(
  handler: (payload: { message?: string }) => void,
): () => void {
  const s = getSocket();
  s.on('provider:connection-replaced', handler);
  return () => s.off('provider:connection-replaced', handler);
}

export function onEndExercise(handler: (payload: { message: string }) => void): () => void {
  const s = getSocket();
  s.on('provider:endex', handler);
  return () => s.off('provider:endex', handler);
}

export function joinCommandRoom(
  onDevices: (devices: ProviderDevice[]) => void,
  onAuthorizationError?: (message: string) => void,
): () => void {
  const s = getSocket();
  const join = () => {
    if (!activeLobbyCode) return;
    const controllerCapability = getControllerCapability(activeLobbyCode);
    if (!controllerCapability) {
      onAuthorizationError?.('Open the secure command link created by the exercise host.');
      return;
    }
    s.emit(
      'commander:join',
      { lobbyCode: activeLobbyCode, controllerCapability },
      (response: { ok?: boolean; error?: string }) => {
        if (!response?.ok) {
          onAuthorizationError?.(response?.error ?? 'Controller authorization failed.');
        } else {
          onAuthorizationError?.('');
        }
      },
    );
  };

  join();
  s.on('devices:update', onDevices);
  commanderJoinHandler = join;

  return () => {
    s.off('devices:update', onDevices);
    if (commanderJoinHandler === join) commanderJoinHandler = null;
  };
}

export type HubConnectionState = 'connecting' | 'online' | 'offline';

function resolveHubState(socketInstance: Socket): HubConnectionState {
  if (socketInstance.connected) return 'online';
  if (socketInstance.active) return 'connecting';
  return 'offline';
}

export function subscribeHubConnection(handler: (state: HubConnectionState) => void): () => void {
  const s = getSocket();

  const onConnect = () => handler('online');
  const onDisconnect = () => handler('offline');
  const onConnectError = () => handler('offline');
  const onReconnectAttempt = () => handler('connecting');

  handler(resolveHubState(s));
  s.on('connect', onConnect);
  s.on('disconnect', onDisconnect);
  s.on('connect_error', onConnectError);
  s.io.on('reconnect_attempt', onReconnectAttempt);

  return () => {
    s.off('connect', onConnect);
    s.off('disconnect', onDisconnect);
    s.off('connect_error', onConnectError);
    s.io.off('reconnect_attempt', onReconnectAttempt);
  };
}
