import { existsSync } from 'node:fs';
import { createServer } from 'node:http';
import type { AddressInfo } from 'node:net';
import { join } from 'node:path';
import cors from 'cors';
import express from 'express';
import { Server, type Socket } from 'socket.io';
import {
  capabilityDigest,
  generateCapability,
  generateLobbyCode,
  verifyCapability,
} from './hubSecurity.ts';

type DeviceStatus =
  | 'waiting'
  | 'standby'
  | 'briefing'
  | 'in_simulation'
  | 'handoff_ready'
  | 'completed'
  | 'offline';

type HospitalDepartmentId =
  | 'field_response_team'
  | 'triage'
  | 'clinical_immediate'
  | 'clinical_delayed'
  | 'clinical_minimal'
  | 'surgery'
  | 'radiology'
  | 'lab'
  | 'pharm'
  | 'emergency_ops_center'
  | 'medical_command_center'
  | 'patient_administration'
  | 'transport'
  | 'manpower_security'
  | 'decon'
  | 'logistics';

type ControllerRole = 'wit' | 'commander';
type SocketRole = ControllerRole | 'provider';
type AckPayload<T extends object = Record<string, never>> = T & { ok: boolean; error?: string };
type Ack<T extends object = Record<string, never>> = (response: AckPayload<T>) => void;

interface PublicProviderDevice {
  deviceId: string;
  displayName: string;
  providerName: string;
  hospitalDepartment: HospitalDepartmentId;
  status: DeviceStatus;
  connectedAt: number;
  lastSeen: number;
  exerciseId?: string;
  exerciseStartedAt?: number;
}

interface ProviderDeviceRecord extends PublicProviderDevice {
  capabilityDigest: string;
  socketId?: string;
  userAgent?: string;
}

interface ActiveExercise {
  exerciseId: string;
  templateId: string;
  title: string;
  startedAt: number;
  status: 'active' | 'completed';
  currentSegmentId: string;
  segmentIds: string[];
  segmentDepartments: HospitalDepartmentId[];
  participantDeviceIds: string[];
}

interface LobbyState {
  code: string;
  createdAt: number;
  lastActivityAt: number;
  controllerCapabilityDigest: string;
  devices: Map<string, ProviderDeviceRecord>;
  lastSessions: Map<string, { session: unknown; scenario: unknown; updatedAt: number }>;
  activeExercise: ActiveExercise | null;
}

interface ControllerPayload {
  lobbyCode?: string;
  controllerCapability?: string;
}

interface ProviderPayload {
  lobbyCode?: string;
  deviceId?: string;
  providerCapability?: string;
}

interface AuthorizationResult<T> {
  ok: true;
  value: T;
}

interface AuthorizationFailure {
  ok: false;
  error: string;
}

type Authorization<T> = AuthorizationResult<T> | AuthorizationFailure;

const LEGACY_DEPARTMENT_MAP: Record<string, HospitalDepartmentId> = {
  first_responder: 'field_response_team',
  urgent_care: 'clinical_immediate',
  emergency_department: 'clinical_immediate',
  clinical_inpatient: 'clinical_delayed',
  laboratory: 'lab',
  pharmacy: 'pharm',
  mcc_ucc: 'medical_command_center',
};

const VALID_DEVICE_STATUSES = new Set<DeviceStatus>([
  'waiting',
  'standby',
  'briefing',
  'in_simulation',
  'handoff_ready',
  'completed',
  'offline',
]);

const HUB_STARTED_AT = Date.now();
const HUB_VERSION = '0.4.0';
const IS_PRODUCTION = process.env.NODE_ENV === 'production';
const MAX_LOBBIES = positiveIntegerEnv('ASKLEPIOS_MAX_LOBBIES', 500, 1, 10_000);
const MAX_DEVICES_PER_LOBBY = positiveIntegerEnv('ASKLEPIOS_MAX_DEVICES_PER_LOBBY', 100, 1, 1_000);
const LOBBY_TTL_MS = positiveIntegerEnv('ASKLEPIOS_LOBBY_TTL_MS', 8 * 60 * 60 * 1000, 60_000, 7 * 24 * 60 * 60 * 1000);
const CREATE_RATE_LIMIT = positiveIntegerEnv('ASKLEPIOS_LOBBY_CREATE_RATE_LIMIT', 10, 1, 1_000);
const CREATE_RATE_WINDOW_MS = 60_000;

function positiveIntegerEnv(name: string, fallback: number, minimum: number, maximum: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const value = Number(raw);
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${name} must be an integer between ${minimum} and ${maximum}.`);
  }
  return value;
}

function normalizeDepartment(id?: string): HospitalDepartmentId {
  if (!id) return 'clinical_immediate';
  if (Object.prototype.hasOwnProperty.call(LEGACY_DEPARTMENT_MAP, id)) {
    return LEGACY_DEPARTMENT_MAP[id];
  }
  return id as HospitalDepartmentId;
}

function normalizeLobbyCode(raw?: string): string {
  return (raw ?? '').trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
}

function boundedText(value: unknown, fallback: string, maximum = 120): string {
  if (typeof value !== 'string') return fallback;
  const normalized = value.trim().replace(/[\u0000-\u001f\u007f]/g, ' ');
  return normalized.slice(0, maximum) || fallback;
}

function validDeviceId(value: unknown): value is string {
  return typeof value === 'string' && /^DEV-[A-Z0-9]{4,32}$/.test(value);
}

function buildCorsOrigins(): { origins: string[]; option: true | string[] } {
  const raw = process.env.ASKLEPIOS_CORS_ORIGIN?.trim();
  if (IS_PRODUCTION && (!raw || raw === '*')) {
    throw new Error('ASKLEPIOS_CORS_ORIGIN must list explicit origins in production. Wildcard CORS is prohibited.');
  }
  const origins = (raw || '*')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
  if (origins.length === 0) throw new Error('ASKLEPIOS_CORS_ORIGIN resolved to an empty origin set.');
  return { origins, option: origins.length === 1 && origins[0] === '*' ? true : origins };
}

const { origins: corsOrigins, option: corsOriginOption } = buildCorsOrigins();
const app = express();
app.disable('x-powered-by');
app.use(
  cors({
    origin: corsOriginOption,
    methods: ['GET', 'POST', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Accept', 'X-Asklepios-Controller-Capability'],
  }),
);
app.use(express.json({ limit: '2mb', strict: true }));

const httpServer = createServer(app);
const io = new Server(httpServer, {
  cors: {
    origin: corsOriginOption,
    methods: ['GET', 'POST'],
  },
  pingInterval: 20_000,
  pingTimeout: 25_000,
  connectTimeout: 20_000,
  maxHttpBufferSize: 2e6,
  serveClient: false,
});

const lobbies = new Map<string, LobbyState>();
const lobbyCreationBuckets = new Map<string, { windowStartedAt: number; count: number }>();
const securityCounters = {
  controllerAuthorizationRejected: 0,
  providerAuthorizationRejected: 0,
  providerTakeoverRejected: 0,
  staleProviderSocketRejected: 0,
  malformedAcknowledgementIgnored: 0,
  lobbyCreateRateLimited: 0,
};

function resolveAcknowledgement(payloadOrAcknowledgement: unknown, acknowledgement?: unknown): unknown {
  return acknowledgement === undefined ? payloadOrAcknowledgement : acknowledgement;
}

function acknowledge<T extends object>(candidate: unknown, response: AckPayload<T>): void {
  if (typeof candidate === 'function') {
    (candidate as Ack<T>)(response);
    return;
  }
  if (candidate !== undefined) securityCounters.malformedAcknowledgementIgnored += 1;
}

function witRoom(code: string): string {
  return `lobby:${code}:wit`;
}

function commanderRoom(code: string): string {
  return `lobby:${code}:commander`;
}

function deviceRoom(code: string, deviceId: string): string {
  return `lobby:${code}:device:${deviceId}`;
}

function touchLobby(lobby: LobbyState): void {
  lobby.lastActivityAt = Date.now();
}

function publicDevice(record: ProviderDeviceRecord): PublicProviderDevice {
  return {
    deviceId: record.deviceId,
    displayName: record.displayName,
    providerName: record.providerName,
    hospitalDepartment: record.hospitalDepartment,
    status: record.status,
    connectedAt: record.connectedAt,
    lastSeen: record.lastSeen,
    exerciseId: record.exerciseId,
    exerciseStartedAt: record.exerciseStartedAt,
  };
}

function listDevices(lobby: LobbyState): PublicProviderDevice[] {
  return [...lobby.devices.values()]
    .filter((device) => device.status !== 'offline')
    .sort((left, right) => left.connectedAt - right.connectedAt)
    .map(publicDevice);
}

function totalDeviceCount(): number {
  let count = 0;
  for (const lobby of lobbies.values()) count += listDevices(lobby).length;
  return count;
}

function createLobby(): { lobby: LobbyState; controllerCapability: string } {
  if (lobbies.size >= MAX_LOBBIES) throw new Error('Exercise lobby capacity reached.');
  for (let attempt = 0; attempt < 32; attempt += 1) {
    const code = generateLobbyCode();
    if (lobbies.has(code)) continue;
    const controllerCapability = generateCapability();
    const now = Date.now();
    const lobby: LobbyState = {
      code,
      createdAt: now,
      lastActivityAt: now,
      controllerCapabilityDigest: capabilityDigest(controllerCapability),
      devices: new Map(),
      lastSessions: new Map(),
      activeExercise: null,
    };
    lobbies.set(code, lobby);
    return { lobby, controllerCapability };
  }
  throw new Error('Could not generate a unique lobby code.');
}

function getLobby(code?: string): LobbyState | undefined {
  const normalized = normalizeLobbyCode(code);
  if (!normalized) return undefined;
  return lobbies.get(normalized);
}

function requireLobby(code?: string): Authorization<LobbyState> {
  const lobby = getLobby(code);
  if (!lobby) return { ok: false, error: 'Exercise lobby not found. Check the join code.' };
  return { ok: true, value: lobby };
}

function authorizeController(
  socket: Socket,
  payload: ControllerPayload,
  allowedRoles: readonly ControllerRole[] = ['wit', 'commander'],
): Authorization<LobbyState> {
  const lobbyResult = requireLobby(payload?.lobbyCode);
  if (!lobbyResult.ok) return lobbyResult;
  const lobby = lobbyResult.value;
  if (!verifyCapability(payload?.controllerCapability, lobby.controllerCapabilityDigest)) {
    securityCounters.controllerAuthorizationRejected += 1;
    return { ok: false, error: 'Controller authorization failed. Open the secure host link again.' };
  }
  const socketLobby = socket.data.lobbyCode as string | undefined;
  const socketRole = socket.data.role as SocketRole | undefined;
  if (socketLobby !== lobby.code || !socketRole || !allowedRoles.includes(socketRole as ControllerRole)) {
    securityCounters.controllerAuthorizationRejected += 1;
    return { ok: false, error: 'This socket has not joined an authorized controller console.' };
  }
  touchLobby(lobby);
  return { ok: true, value: lobby };
}

function authorizeProvider(socket: Socket, payload: ProviderPayload): Authorization<{ lobby: LobbyState; device: ProviderDeviceRecord }> {
  const lobbyResult = requireLobby(payload?.lobbyCode);
  if (!lobbyResult.ok) return lobbyResult;
  const lobby = lobbyResult.value;
  if (!validDeviceId(payload?.deviceId)) {
    securityCounters.providerAuthorizationRejected += 1;
    return { ok: false, error: 'Provider device identity is invalid.' };
  }
  const device = lobby.devices.get(payload.deviceId);
  if (!device || !verifyCapability(payload?.providerCapability, device.capabilityDigest)) {
    securityCounters.providerAuthorizationRejected += 1;
    return { ok: false, error: 'Provider authorization failed. Rejoin the exercise lobby.' };
  }
  if (device.socketId !== socket.id) {
    securityCounters.staleProviderSocketRejected += 1;
    return { ok: false, error: 'This provider connection is stale. Use the newest connected session.' };
  }
  if (
    socket.data.role !== 'provider' ||
    socket.data.lobbyCode !== lobby.code ||
    socket.data.deviceId !== device.deviceId
  ) {
    securityCounters.providerAuthorizationRejected += 1;
    return { ok: false, error: 'Provider socket binding is invalid.' };
  }
  touchLobby(lobby);
  return { ok: true, value: { lobby, device } };
}

function bindControllerSocket(socket: Socket, lobby: LobbyState, role: ControllerRole): void {
  socket.data.lobbyCode = lobby.code;
  socket.data.role = role;
  socket.join(role === 'wit' ? witRoom(lobby.code) : commanderRoom(lobby.code));
}

function bindProviderSocket(socket: Socket, lobby: LobbyState, device: ProviderDeviceRecord): void {
  socket.data.lobbyCode = lobby.code;
  socket.data.deviceId = device.deviceId;
  socket.data.role = 'provider';
  socket.join(deviceRoom(lobby.code, device.deviceId));
}

function registerProvider(
  socket: Socket,
  lobby: LobbyState,
  payload: {
    deviceId: string;
    displayName: string;
    providerName?: string;
    hospitalDepartment?: HospitalDepartmentId;
    userAgent?: string;
    providerCapability?: string;
  },
): Authorization<{ device: ProviderDeviceRecord; issuedCapability?: string }> {
  if (!validDeviceId(payload.deviceId)) return { ok: false, error: 'A valid provider device ID is required.' };
  const existing = lobby.devices.get(payload.deviceId);
  let issuedCapability: string | undefined;
  let digest: string;

  if (existing) {
    if (!verifyCapability(payload.providerCapability, existing.capabilityDigest)) {
      securityCounters.providerTakeoverRejected += 1;
      return { ok: false, error: 'This provider identity already exists. Rejoin from the original device session.' };
    }
    // Rotate the capability at every authenticated registration. This makes
    // the newest socket the only session able to reconnect and prevents two
    // browser tabs from repeatedly replacing each other with one stale token.
    issuedCapability = generateCapability();
    digest = capabilityDigest(issuedCapability);
  } else {
    if (lobby.devices.size >= MAX_DEVICES_PER_LOBBY) {
      return { ok: false, error: 'This exercise lobby has reached its provider capacity.' };
    }
    issuedCapability = generateCapability();
    digest = capabilityDigest(issuedCapability);
  }

  const displayName = boundedText(payload.displayName, `Provider ${payload.deviceId.slice(-4)}`, 80);
  const providerName = boundedText(payload.providerName, existing?.providerName ?? displayName, 80);
  const now = Date.now();
  const priorSocketId = existing?.socketId;
  const record: ProviderDeviceRecord = {
    deviceId: payload.deviceId,
    displayName,
    providerName,
    hospitalDepartment: normalizeDepartment(payload.hospitalDepartment ?? existing?.hospitalDepartment),
    status:
      existing && ['in_simulation', 'briefing', 'handoff_ready', 'standby', 'completed'].includes(existing.status)
        ? existing.status
        : 'waiting',
    connectedAt: existing?.connectedAt ?? now,
    lastSeen: now,
    exerciseId: existing?.exerciseId,
    exerciseStartedAt: existing?.exerciseStartedAt,
    capabilityDigest: digest,
    socketId: socket.id,
    userAgent: boundedText(payload.userAgent, existing?.userAgent ?? '', 256) || undefined,
  };
  lobby.devices.set(record.deviceId, record);
  bindProviderSocket(socket, lobby, record);

  if (priorSocketId && priorSocketId !== socket.id) {
    const staleSocket = io.sockets.sockets.get(priorSocketId);
    staleSocket?.emit('provider:connection-replaced', {
      message: 'A newer authenticated connection replaced this provider session.',
    });
    staleSocket?.disconnect(true);
  }

  if (lobby.activeExercise) {
    setDeviceStandbyForExercise(record, lobby.activeExercise);
    lobby.devices.set(record.deviceId, record);
  }
  touchLobby(lobby);
  return { ok: true, value: { device: record, issuedCapability } };
}

function broadcastDevices(lobby: LobbyState): void {
  const devices = listDevices(lobby);
  io.to(witRoom(lobby.code)).emit('devices:update', devices);
  io.to(commanderRoom(lobby.code)).emit('devices:update', devices);
}

function broadcastExerciseUpdate(lobby: LobbyState): void {
  const exercise = lobby.activeExercise;
  io.to(witRoom(lobby.code)).emit('exercise:update', { exercise });
  io.to(commanderRoom(lobby.code)).emit('exercise:update', { exercise });
  for (const device of lobby.devices.values()) {
    io.to(deviceRoom(lobby.code, device.deviceId)).emit('exercise:update', {
      exercise,
      device: publicDevice(device),
    });
  }
}

function sendLobbySnapshot(socket: Socket, lobby: LobbyState): void {
  socket.emit('devices:update', listDevices(lobby));
  socket.emit('exercise:update', { exercise: lobby.activeExercise });
  for (const [deviceId, cached] of lobby.lastSessions) {
    socket.emit('session:update', {
      deviceId,
      session: cached.session,
      scenario: cached.scenario,
    });
  }
}

function clearExerciseParticipation(device: ProviderDeviceRecord): void {
  device.exerciseId = undefined;
  device.exerciseStartedAt = undefined;
}

function setDeviceStandbyForExercise(device: ProviderDeviceRecord, exercise: ActiveExercise): void {
  if (!exercise.segmentDepartments.includes(device.hospitalDepartment) || device.status === 'offline') return;
  device.exerciseId = exercise.exerciseId;
  device.exerciseStartedAt = exercise.startedAt;
  if (device.status === 'waiting') device.status = 'standby';
  if (!exercise.participantDeviceIds.includes(device.deviceId)) {
    exercise.participantDeviceIds.push(device.deviceId);
  }
}

function deployToDeviceRoom(
  lobby: LobbyState,
  deviceId: string,
  payload: { scenario: unknown; scenarioConfig: unknown; exerciseMeta?: unknown },
): boolean {
  const device = lobby.devices.get(deviceId);
  if (!device || device.status === 'offline') return false;
  device.status = 'briefing';
  device.lastSeen = Date.now();
  lobby.devices.set(deviceId, device);
  io.to(deviceRoom(lobby.code, deviceId)).emit('provider:deployment', payload);
  touchLobby(lobby);
  broadcastDevices(lobby);
  return true;
}

function lobbySummary(lobby: LobbyState) {
  return {
    code: lobby.code,
    createdAt: lobby.createdAt,
    deviceCount: listDevices(lobby).length,
    activeExercise: lobby.activeExercise
      ? {
          exerciseId: lobby.activeExercise.exerciseId,
          title: lobby.activeExercise.title,
          status: lobby.activeExercise.status,
          participantCount: lobby.activeExercise.participantDeviceIds.length,
        }
      : null,
  };
}

function requestKey(req: express.Request): string {
  return req.ip || req.socket.remoteAddress || 'unknown';
}

function consumeLobbyCreateBudget(key: string): boolean {
  const now = Date.now();
  const current = lobbyCreationBuckets.get(key);
  if (!current || now - current.windowStartedAt >= CREATE_RATE_WINDOW_MS) {
    lobbyCreationBuckets.set(key, { windowStartedAt: now, count: 1 });
    return true;
  }
  if (current.count >= CREATE_RATE_LIMIT) {
    securityCounters.lobbyCreateRateLimited += 1;
    return false;
  }
  current.count += 1;
  return true;
}

function controllerCapabilityFromRequest(req: express.Request): string | undefined {
  const value = req.header('x-asklepios-controller-capability');
  return value?.trim() || undefined;
}

app.get('/api/health', (_req, res) => {
  const activeExercises = [...lobbies.values()].filter((lobby) => lobby.activeExercise).length;
  res.json({
    ok: true,
    service: 'asklepios-hub',
    version: HUB_VERSION,
    uptimeSeconds: Math.floor((Date.now() - HUB_STARTED_AT) / 1000),
    lobbies: lobbies.size,
    devices: totalDeviceCount(),
    activeExercises,
    activeExercise: null,
    intendedUse: 'healthcare_simulation_training',
    clinicalDecisionSupport: false,
    directPatientCare: false,
  });
});

// Optional same-origin SPA: serve Vite `dist` when present (single Render service).
// API routes above stay authoritative. Socket.IO attaches to httpServer, not Express.
const DIST_DIR = join(process.cwd(), 'dist');
const DIST_INDEX = join(DIST_DIR, 'index.html');
const serveSpaFromDist = existsSync(DIST_INDEX);

if (!serveSpaFromDist) {
  app.get('/', (_req, res) => {
    res.json({
      ok: true,
      service: 'asklepios-hub',
      version: HUB_VERSION,
      health: '/api/health',
      lobbies: '/api/lobbies',
    });
  });
}

app.post('/api/lobbies', (req, res) => {
  if (!consumeLobbyCreateBudget(requestKey(req))) {
    res.status(429).json({ ok: false, error: 'Too many lobby creation requests. Try again shortly.' });
    return;
  }
  try {
    const { lobby, controllerCapability } = createLobby();
    res.status(201).json({ ok: true, ...lobbySummary(lobby), controllerCapability });
  } catch (error) {
    res.status(503).json({
      ok: false,
      error: error instanceof Error ? error.message : 'Could not create exercise lobby',
    });
  }
});

app.get('/api/lobbies/:code', (req, res) => {
  const lobby = getLobby(req.params.code);
  if (!lobby) {
    res.status(404).json({ ok: false, error: 'Exercise lobby not found' });
    return;
  }
  res.json({ ok: true, ...lobbySummary(lobby) });
});

app.get('/api/devices', (req, res) => {
  const code = normalizeLobbyCode(String(req.query.lobby ?? ''));
  if (!code) {
    res.status(400).json({ ok: false, error: 'lobby query parameter required' });
    return;
  }
  const lobby = getLobby(code);
  if (!lobby) {
    res.status(404).json({ ok: false, error: 'Exercise lobby not found' });
    return;
  }
  if (!verifyCapability(controllerCapabilityFromRequest(req), lobby.controllerCapabilityDigest)) {
    securityCounters.controllerAuthorizationRejected += 1;
    res.status(403).json({ ok: false, error: 'Controller authorization required' });
    return;
  }
  res.json(listDevices(lobby));
});

io.on('connection', (socket) => {
  socket.on('hub:ping', (payloadOrAcknowledgement?: unknown, callback?: Ack<{ ts: number }>) => {
    const acknowledgement = resolveAcknowledgement(payloadOrAcknowledgement, callback);
    acknowledge(acknowledgement, { ok: true, ts: Date.now() });
  });

  socket.on(
    'lobby:create',
    (
      payloadOrAcknowledgement?: unknown,
      callback?: Ack<{ code?: string; createdAt?: number; controllerCapability?: string }>,
    ) => {
      const acknowledgement = resolveAcknowledgement(payloadOrAcknowledgement, callback);
      try {
        const { lobby, controllerCapability } = createLobby();
        acknowledge(acknowledgement, { ok: true, code: lobby.code, createdAt: lobby.createdAt, controllerCapability });
      } catch (error) {
        acknowledge(acknowledgement, { ok: false, error: error instanceof Error ? error.message : 'Could not create exercise lobby' });
      }
    },
  );

  socket.on(
    'provider:register',
    (
      payload: {
        lobbyCode: string;
        deviceId: string;
        displayName: string;
        providerName?: string;
        hospitalDepartment?: HospitalDepartmentId;
        userAgent?: string;
        providerCapability?: string;
      },
      callback?: Ack<{ device?: PublicProviderDevice; providerCapability?: string }>,
    ) => {
      const lobbyResult = requireLobby(payload?.lobbyCode);
      if (!lobbyResult.ok) {
        acknowledge(callback, { ok: false, error: lobbyResult.error });
        return;
      }
      const registered = registerProvider(socket, lobbyResult.value, payload);
      if (!registered.ok) {
        acknowledge(callback, { ok: false, error: registered.error });
        return;
      }
      const { device, issuedCapability } = registered.value;
      const publicRecord = publicDevice(device);
      socket.emit('provider:registered', publicRecord);
      if (lobbyResult.value.activeExercise) {
        socket.emit('exercise:update', { exercise: lobbyResult.value.activeExercise });
      }
      broadcastDevices(lobbyResult.value);
      acknowledge(callback, { ok: true, device: publicRecord, providerCapability: issuedCapability });
    },
  );

  socket.on(
    'provider:update-name',
    (payload: ProviderPayload & { displayName: string }, callback?: Ack<{ device?: PublicProviderDevice }>) => {
      const auth = authorizeProvider(socket, payload);
      if (!auth.ok) {
        acknowledge(callback, { ok: false, error: auth.error });
        return;
      }
      const { lobby, device } = auth.value;
      const trimmed = boundedText(payload.displayName, '', 80);
      if (!trimmed) {
        acknowledge(callback, { ok: false, error: 'Display name cannot be empty' });
        return;
      }
      device.displayName = trimmed;
      device.providerName = trimmed;
      device.lastSeen = Date.now();
      lobby.devices.set(device.deviceId, device);
      broadcastDevices(lobby);
      acknowledge(callback, { ok: true, device: publicDevice(device) });
    },
  );

  socket.on(
    'provider:update-profile',
    (
      payload: ProviderPayload & { providerName: string; hospitalDepartment: HospitalDepartmentId },
      callback?: Ack<{ device?: PublicProviderDevice }>,
    ) => {
      const auth = authorizeProvider(socket, payload);
      if (!auth.ok) {
        acknowledge(callback, { ok: false, error: auth.error });
        return;
      }
      const { lobby, device } = auth.value;
      const name = boundedText(payload.providerName, '', 80);
      if (!name) {
        acknowledge(callback, { ok: false, error: 'Provider name is required' });
        return;
      }
      device.providerName = name;
      device.displayName = name;
      device.hospitalDepartment = normalizeDepartment(payload.hospitalDepartment ?? device.hospitalDepartment);
      device.lastSeen = Date.now();
      lobby.devices.set(device.deviceId, device);
      broadcastDevices(lobby);
      acknowledge(callback, { ok: true, device: publicDevice(device) });
    },
  );

  function joinController(
    role: ControllerRole,
    payload: ControllerPayload,
    callback?: Ack,
  ): void {
    const lobbyResult = requireLobby(payload?.lobbyCode);
    if (!lobbyResult.ok) {
      acknowledge(callback, { ok: false, error: lobbyResult.error });
      return;
    }
    const lobby = lobbyResult.value;
    if (!verifyCapability(payload?.controllerCapability, lobby.controllerCapabilityDigest)) {
      securityCounters.controllerAuthorizationRejected += 1;
      acknowledge(callback, { ok: false, error: 'Controller authorization failed. Use the secure link created by the host.' });
      return;
    }
    bindControllerSocket(socket, lobby, role);
    touchLobby(lobby);
    sendLobbySnapshot(socket, lobby);
    acknowledge(callback, { ok: true });
  }

  socket.on('wit:join', (payload: ControllerPayload, callback?: Ack) => joinController('wit', payload, callback));
  socket.on('commander:join', (payload: ControllerPayload, callback?: Ack) => joinController('commander', payload, callback));

  socket.on('wit:request-session', (payload: ControllerPayload & { deviceId: string }, callback?: Ack) => {
    const auth = authorizeController(socket, payload);
    if (!auth.ok) {
      acknowledge(callback, { ok: false, error: auth.error });
      return;
    }
    const cached = auth.value.lastSessions.get(payload.deviceId);
    if (!cached) {
      acknowledge(callback, { ok: false, error: 'No session has been synchronized for this provider.' });
      return;
    }
    socket.emit('session:update', {
      deviceId: payload.deviceId,
      session: cached.session,
      scenario: cached.scenario,
    });
    acknowledge(callback, { ok: true });
  });

  socket.on(
    'wit:deploy',
    (
      payload: ControllerPayload & {
        deviceId: string;
        scenario: unknown;
        scenarioConfig: unknown;
        exerciseMeta?: unknown;
      },
      callback?: Ack,
    ) => {
      const auth = authorizeController(socket, payload, ['wit']);
      if (!auth.ok) {
        acknowledge(callback, { ok: false, error: auth.error });
        return;
      }
      const deployed = deployToDeviceRoom(auth.value, payload.deviceId, {
        scenario: payload.scenario,
        scenarioConfig: payload.scenarioConfig,
        exerciseMeta: payload.exerciseMeta,
      });
      acknowledge(callback, { ok: deployed, error: deployed ? undefined : 'Target provider is unavailable.' });
    },
  );

  socket.on(
    'wit:start-exercise',
    (
      payload: ControllerPayload & {
        exerciseId: string;
        templateId: string;
        title: string;
        startedAt: number;
        segments: { id: string; department: HospitalDepartmentId }[];
        entrySegmentId: string;
        entryDeviceId: string;
        firstDeployment: { scenario: unknown; scenarioConfig: unknown; exerciseMeta: unknown };
      },
      callback?: Ack,
    ) => {
      const auth = authorizeController(socket, payload, ['wit']);
      if (!auth.ok) {
        acknowledge(callback, { ok: false, error: auth.error });
        return;
      }
      if (!payload?.exerciseId || !payload.entryDeviceId || !Array.isArray(payload.segments)) {
        acknowledge(callback, { ok: false, error: 'Invalid exercise payload' });
        return;
      }
      const lobby = auth.value;
      if (lobby.activeExercise) {
        acknowledge(callback, { ok: false, error: 'Exercise already active. End it before starting again.' });
        return;
      }
      const entryDevice = lobby.devices.get(payload.entryDeviceId);
      if (!entryDevice || entryDevice.status === 'offline') {
        acknowledge(callback, { ok: false, error: 'Entry device not found or offline in this exercise lobby' });
        return;
      }
      lobby.activeExercise = {
        exerciseId: boundedText(payload.exerciseId, `EX-${Date.now().toString(36).toUpperCase()}`, 120),
        templateId: boundedText(payload.templateId, 'unknown', 120),
        title: boundedText(payload.title, 'Healthcare simulation exercise', 160),
        startedAt: Number.isFinite(payload.startedAt) ? payload.startedAt : Date.now(),
        status: 'active',
        currentSegmentId: boundedText(payload.entrySegmentId, 'entry', 120),
        segmentIds: payload.segments.map((segment) => boundedText(segment.id, 'segment', 120)),
        segmentDepartments: payload.segments.map((segment) => normalizeDepartment(segment.department)),
        participantDeviceIds: [],
      };
      for (const device of lobby.devices.values()) {
        if (device.deviceId !== payload.entryDeviceId) setDeviceStandbyForExercise(device, lobby.activeExercise);
      }
      const deployed = deployToDeviceRoom(lobby, payload.entryDeviceId, payload.firstDeployment);
      if (!deployed) {
        lobby.activeExercise = null;
        acknowledge(callback, { ok: false, error: 'Entry deployment failed.' });
        return;
      }
      if (!lobby.activeExercise.participantDeviceIds.includes(payload.entryDeviceId)) {
        lobby.activeExercise.participantDeviceIds.push(payload.entryDeviceId);
      }
      entryDevice.exerciseId = lobby.activeExercise.exerciseId;
      entryDevice.exerciseStartedAt = lobby.activeExercise.startedAt;
      lobby.devices.set(entryDevice.deviceId, entryDevice);
      broadcastExerciseUpdate(lobby);
      acknowledge(callback, { ok: true });
    },
  );

  socket.on(
    'wit:arm-exercise',
    (payload: ControllerPayload & { title?: string }, callback?: Ack<{ exerciseId?: string }>) => {
      const auth = authorizeController(socket, payload, ['wit']);
      if (!auth.ok) {
        acknowledge(callback, { ok: false, error: auth.error });
        return;
      }
      const lobby = auth.value;
      if (lobby.activeExercise) {
        acknowledge(callback, { ok: false, error: 'Exercise already active. End it before starting again.' });
        return;
      }
      const readyDevices = [...lobby.devices.values()].filter((device) => device.status === 'waiting');
      if (readyDevices.length === 0) {
        acknowledge(callback, { ok: false, error: 'No provider devices are waiting in the lobby.' });
        return;
      }
      const exerciseId = `ADHOC-${Date.now().toString(36).toUpperCase()}`;
      lobby.activeExercise = {
        exerciseId,
        templateId: 'ad_hoc',
        title: boundedText(payload.title, 'Training evolution', 160),
        startedAt: Date.now(),
        status: 'active',
        currentSegmentId: 'ad_hoc_entry',
        segmentIds: ['ad_hoc_entry'],
        segmentDepartments: [...new Set(readyDevices.map((device) => device.hospitalDepartment))],
        participantDeviceIds: [],
      };
      for (const device of readyDevices) setDeviceStandbyForExercise(device, lobby.activeExercise);
      touchLobby(lobby);
      broadcastDevices(lobby);
      broadcastExerciseUpdate(lobby);
      acknowledge(callback, { ok: true, exerciseId });
    },
  );

  socket.on(
    'provider:execute-handoff',
    (
      payload: ProviderPayload & {
        fromDeviceId: string;
        exerciseId: string;
        targetDepartment: HospitalDepartmentId;
        patientSnapshot: unknown;
        targetDeployment: { scenario: unknown; scenarioConfig: unknown; exerciseMeta: unknown };
      },
      callback?: Ack<{ targetDeviceId?: string }>,
    ) => {
      const auth = authorizeProvider(socket, { ...payload, deviceId: payload.fromDeviceId });
      if (!auth.ok) {
        acknowledge(callback, { ok: false, error: auth.error });
        return;
      }
      const { lobby, device: fromDevice } = auth.value;
      if (!lobby.activeExercise || lobby.activeExercise.exerciseId !== payload.exerciseId) {
        acknowledge(callback, { ok: false, error: 'No active exercise matches this handoff' });
        return;
      }
      const targetDevice = [...lobby.devices.values()].find(
        (candidate) =>
          candidate.deviceId !== fromDevice.deviceId &&
          candidate.hospitalDepartment === payload.targetDepartment &&
          candidate.status === 'standby' &&
          candidate.exerciseId === payload.exerciseId,
      );
      if (!targetDevice) {
        acknowledge(callback, { ok: false, error: `No ${payload.targetDepartment} provider is available in standby.` });
        return;
      }
      const meta = payload.targetDeployment.exerciseMeta as { segmentId?: string; segmentLabel?: string } | undefined;
      if (meta?.segmentId) lobby.activeExercise.currentSegmentId = meta.segmentId;
      if (!deployToDeviceRoom(lobby, targetDevice.deviceId, payload.targetDeployment)) {
        acknowledge(callback, { ok: false, error: 'Target provider became unavailable.' });
        return;
      }
      io.to(deviceRoom(lobby.code, targetDevice.deviceId)).emit('provider:segment-notification', {
        exerciseId: payload.exerciseId,
        templateTitle: lobby.activeExercise.title,
        segmentLabel: meta?.segmentLabel ?? meta?.segmentId ?? 'Next segment',
        fromProviderName: fromDevice.providerName,
        fromDepartment: fromDevice.hospitalDepartment,
        message: `${fromDevice.providerName} (${fromDevice.hospitalDepartment}) is handing off a simulated patient to your station.`,
      });
      fromDevice.status = 'standby';
      fromDevice.lastSeen = Date.now();
      targetDevice.exerciseId = payload.exerciseId;
      targetDevice.exerciseStartedAt = lobby.activeExercise.startedAt;
      lobby.devices.set(fromDevice.deviceId, fromDevice);
      lobby.devices.set(targetDevice.deviceId, targetDevice);
      broadcastDevices(lobby);
      broadcastExerciseUpdate(lobby);
      acknowledge(callback, { ok: true, targetDeviceId: targetDevice.deviceId });
    },
  );

  socket.on('wit:end-exercise', (payload: ControllerPayload, callback?: Ack) => {
    const auth = authorizeController(socket, payload, ['wit']);
    if (!auth.ok) {
      acknowledge(callback, { ok: false, error: auth.error });
      return;
    }
    const lobby = auth.value;
    lobby.activeExercise = null;
    for (const device of lobby.devices.values()) {
      if (device.status === 'standby' || device.status === 'handoff_ready') {
        device.status = 'waiting';
        clearExerciseParticipation(device);
      }
    }
    touchLobby(lobby);
    broadcastDevices(lobby);
    broadcastExerciseUpdate(lobby);
    acknowledge(callback, { ok: true });
  });

  socket.on('provider:return-standby', (payload: ProviderPayload, callback?: Ack) => {
    const auth = authorizeProvider(socket, payload);
    if (!auth.ok) {
      acknowledge(callback, { ok: false, error: auth.error });
      return;
    }
    const { lobby, device } = auth.value;
    if (lobby.activeExercise && device.exerciseId === lobby.activeExercise.exerciseId) {
      device.status = 'standby';
    } else {
      device.status = 'waiting';
      clearExerciseParticipation(device);
    }
    device.lastSeen = Date.now();
    lobby.devices.set(device.deviceId, device);
    broadcastDevices(lobby);
    acknowledge(callback, { ok: true });
  });

  socket.on('provider:status', (payload: ProviderPayload & { status: DeviceStatus }, callback?: Ack) => {
    const auth = authorizeProvider(socket, payload);
    if (!auth.ok) {
      acknowledge(callback, { ok: false, error: auth.error });
      return;
    }
    if (!VALID_DEVICE_STATUSES.has(payload.status) || payload.status === 'offline') {
      acknowledge(callback, { ok: false, error: 'Provider status transition is invalid.' });
      return;
    }
    const { lobby, device } = auth.value;
    device.status = payload.status;
    device.lastSeen = Date.now();
    lobby.devices.set(device.deviceId, device);
    broadcastDevices(lobby);
    acknowledge(callback, { ok: true });
  });

  socket.on('wit:endex', (payload: ControllerPayload & { deviceId: string }, callback?: Ack) => {
    const auth = authorizeController(socket, payload, ['wit']);
    if (!auth.ok) {
      acknowledge(callback, { ok: false, error: auth.error });
      return;
    }
    const device = auth.value.devices.get(payload.deviceId);
    if (!device) {
      acknowledge(callback, { ok: false, error: 'Provider device not found.' });
      return;
    }
    io.to(deviceRoom(auth.value.code, payload.deviceId)).emit('provider:endex', {
      message: 'WIT ENDEX: The evaluator has ended this simulation exercise. After-action review will follow.',
    });
    acknowledge(callback, { ok: true });
  });

  socket.on(
    'session:sync',
    (payload: ProviderPayload & { session: unknown; scenario: unknown }, callback?: Ack) => {
      const auth = authorizeProvider(socket, payload);
      if (!auth.ok) {
        acknowledge(callback, { ok: false, error: auth.error });
        return;
      }
      const { lobby, device } = auth.value;
      lobby.lastSessions.set(device.deviceId, {
        session: payload.session,
        scenario: payload.scenario,
        updatedAt: Date.now(),
      });
      const update = { deviceId: device.deviceId, session: payload.session, scenario: payload.scenario };
      io.to(witRoom(lobby.code)).emit('session:update', update);
      io.to(commanderRoom(lobby.code)).emit('session:update', update);
      acknowledge(callback, { ok: true });
    },
  );

  socket.on('disconnect', () => {
    const deviceId = socket.data.deviceId as string | undefined;
    const lobbyCode = socket.data.lobbyCode as string | undefined;
    if (!deviceId || !lobbyCode || socket.data.role !== 'provider') return;
    const lobby = getLobby(lobbyCode);
    const device = lobby?.devices.get(deviceId);
    if (!lobby || !device || device.socketId !== socket.id) return;
    if (device.status === 'waiting') {
      lobby.devices.delete(deviceId);
      lobby.lastSessions.delete(deviceId);
    } else {
      device.status = 'offline';
      device.socketId = undefined;
      lobby.devices.set(deviceId, device);
    }
    touchLobby(lobby);
    broadcastDevices(lobby);
  });
});

function cleanupExpiredLobbies(): void {
  const now = Date.now();
  for (const [code, lobby] of lobbies) {
    if (now - lobby.lastActivityAt < LOBBY_TTL_MS) continue;
    for (const device of lobby.devices.values()) {
      if (device.socketId) io.sockets.sockets.get(device.socketId)?.disconnect(true);
    }
    lobbies.delete(code);
  }
  for (const [key, bucket] of lobbyCreationBuckets) {
    if (now - bucket.windowStartedAt > CREATE_RATE_WINDOW_MS * 2) lobbyCreationBuckets.delete(key);
  }
}

const cleanupTimer = setInterval(cleanupExpiredLobbies, Math.min(60_000, Math.max(10_000, LOBBY_TTL_MS / 4)));
cleanupTimer.unref();
httpServer.on('close', () => clearInterval(cleanupTimer));

if (serveSpaFromDist) {
  app.use(
    express.static(DIST_DIR, {
      index: false,
      fallthrough: true,
      // Avoid caching index.html so deploys pick up new asset hashes quickly.
      setHeaders(res, filePath) {
        if (filePath.endsWith('index.html')) {
          res.setHeader('Cache-Control', 'no-cache');
        }
      },
    }),
  );
  app.get(/^(?!\/api\/|\/socket\.io(?:\/|$)).*/, (req, res, next) => {
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      next();
      return;
    }
    res.sendFile(DIST_INDEX, (error) => {
      if (error) next(error);
    });
  });
}

const PORT = Number(process.env.PORT ?? process.env.ASKLEPIOS_HUB_PORT ?? 3021);

export function hubRuntimeSnapshot() {
  return {
    version: HUB_VERSION,
    lobbies: lobbies.size,
    devices: totalDeviceCount(),
    securityCounters: { ...securityCounters },
    corsOrigins: [...corsOrigins],
  };
}

export function listeningPort(): number | null {
  const address = httpServer.address();
  return address && typeof address !== 'string' ? (address as AddressInfo).port : null;
}

export { app, httpServer, io };

if (!process.env.VERCEL && process.env.ASKLEPIOS_HUB_DISABLE_LISTEN !== '1') {
  httpServer.listen(PORT, '0.0.0.0', () => {
    const port = listeningPort() ?? PORT;
    console.log(`Asklepios network hub v${HUB_VERSION} listening on http://0.0.0.0:${port}`);
    console.log(corsOriginOption === true ? 'CORS: development wildcard' : `CORS: ${corsOrigins.join(', ')}`);
  });
}
