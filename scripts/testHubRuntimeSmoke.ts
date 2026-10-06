import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { performance } from 'node:perf_hooks';
import { io as connectClient, type Socket } from 'socket.io-client';

process.env.ASKLEPIOS_HUB_DISABLE_LISTEN = '1';
process.env.ASKLEPIOS_CORS_ORIGIN = 'http://127.0.0.1';
process.env.NODE_ENV = 'test';

interface AckResponse {
  ok?: boolean;
  error?: string;
  [key: string]: unknown;
}

function argument(name: string, fallback: string): string {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function percentile(sorted: readonly number[], fraction: number): number {
  if (sorted.length === 0) return Number.POSITIVE_INFINITY;
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * fraction) - 1));
  return sorted[index] ?? Number.POSITIVE_INFINITY;
}

function emitAck<T extends AckResponse>(socket: Socket, event: string, payload: unknown, timeoutMs = 4_000): Promise<T> {
  return new Promise((resolvePromise, rejectPromise) => {
    const timer = setTimeout(() => rejectPromise(new Error(`ack timeout:${event}`)), timeoutMs);
    socket.emit(event, payload, (response: T) => {
      clearTimeout(timer);
      resolvePromise(response);
    });
  });
}

function emitAckWithoutPayload<T extends AckResponse>(socket: Socket, event: string, timeoutMs = 4_000): Promise<T> {
  return new Promise((resolvePromise, rejectPromise) => {
    const timer = setTimeout(() => rejectPromise(new Error(`ack timeout:${event}`)), timeoutMs);
    socket.emit(event, (response: T) => {
      clearTimeout(timer);
      resolvePromise(response);
    });
  });
}

function emitMalformedAcknowledgement(socket: Socket, event: string, payload: unknown): void {
  const rawSocket = socket as unknown as { emit: (...args: unknown[]) => boolean };
  rawSocket.emit(event, payload, 'not-an-acknowledgement');
}

function waitForEvent<T>(socket: Socket, event: string, timeoutMs = 4_000): Promise<T> {
  return new Promise((resolvePromise, rejectPromise) => {
    const timer = setTimeout(() => rejectPromise(new Error(`event timeout:${event}`)), timeoutMs);
    socket.once(event, (payload: T) => {
      clearTimeout(timer);
      resolvePromise(payload);
    });
  });
}

async function openSocket(baseUrl: string): Promise<Socket> {
  const socket = connectClient(baseUrl, {
    path: '/socket.io',
    transports: ['websocket'],
    forceNew: true,
    reconnection: false,
    timeout: 4_000,
  });
  await new Promise<void>((resolvePromise, rejectPromise) => {
    const timer = setTimeout(() => rejectPromise(new Error('socket connect timeout')), 4_000);
    socket.once('connect', () => {
      clearTimeout(timer);
      resolvePromise();
    });
    socket.once('connect_error', (error) => {
      clearTimeout(timer);
      rejectPromise(error);
    });
  });
  return socket;
}

async function main(): Promise<number> {
  const repo = resolve(argument('--repo', '.'));
  const output = resolve(repo, argument('--json-output', 'reports/hub-runtime-smoke.json'));
  const errors: string[] = [];
  const assertions: Record<string, boolean> = {};
  const sockets: Socket[] = [];

  function check(condition: boolean, name: string): void {
    assertions[name] = condition;
    if (!condition) errors.push(name);
  }

  const { httpServer, io, hubRuntimeSnapshot, listeningPort } = await import('../server/index.ts');
  try {
    await new Promise<void>((resolvePromise, rejectPromise) => {
      httpServer.once('error', rejectPromise);
      httpServer.listen(0, '127.0.0.1', () => resolvePromise());
    });
    const port = listeningPort();
    if (!port) throw new Error('hub did not expose a listening port');
    const baseUrl = `http://127.0.0.1:${port}`;

    const healthResponse = await fetch(`${baseUrl}/api/health`);
    const health = await healthResponse.json() as Record<string, unknown>;
    check(healthResponse.ok && health.ok === true, 'health_endpoint_passes');
    check(health.directPatientCare === false, 'health_endpoint_preserves_direct_care_boundary');
    check(health.clinicalDecisionSupport === false, 'health_endpoint_preserves_cds_boundary');

    const createResponse = await fetch(`${baseUrl}/api/lobbies`, { method: 'POST' });
    const created = await createResponse.json() as Record<string, unknown>;
    const code = typeof created.code === 'string' ? created.code : '';
    const controllerCapability = typeof created.controllerCapability === 'string' ? created.controllerCapability : '';
    check(createResponse.status === 201 && code.length === 6, 'lobby_created');
    check(controllerCapability.length >= 40, 'controller_capability_issued_once');

    const unauthenticatedDevices = await fetch(`${baseUrl}/api/devices?lobby=${encodeURIComponent(code)}`);
    check(unauthenticatedDevices.status === 403, 'device_inventory_rejects_missing_controller_capability');
    const authenticatedDevices = await fetch(`${baseUrl}/api/devices?lobby=${encodeURIComponent(code)}`, {
      headers: { 'x-asklepios-controller-capability': controllerCapability },
    });
    check(authenticatedDevices.status === 200, 'device_inventory_accepts_valid_controller_capability');

    const invalidController = await openSocket(baseUrl);
    sockets.push(invalidController);
    const invalidJoin = await emitAck<AckResponse>(invalidController, 'wit:join', {
      lobbyCode: code,
      controllerCapability: 'invalid-controller-capability',
    });
    check(invalidJoin.ok === false, 'invalid_controller_rejected');

    const controller = await openSocket(baseUrl);
    sockets.push(controller);
    const controllerJoin = await emitAck<AckResponse>(controller, 'wit:join', {
      lobbyCode: code,
      controllerCapability,
    });
    check(controllerJoin.ok === true, 'valid_controller_accepted');

    const providerOne = await openSocket(baseUrl);
    sockets.push(providerOne);
    const providerDeviceId = 'DEV-SMOKE001';
    const providerRegistration = await emitAck<AckResponse>(providerOne, 'provider:register', {
      lobbyCode: code,
      deviceId: providerDeviceId,
      displayName: 'Simulation Provider',
      providerName: 'Simulation Provider',
      hospitalDepartment: 'clinical_immediate',
      userAgent: 'hub-runtime-smoke',
    });
    const providerCapability = typeof providerRegistration.providerCapability === 'string'
      ? providerRegistration.providerCapability
      : '';
    check(providerRegistration.ok === true, 'new_provider_registered');
    check(providerCapability.length >= 40, 'provider_capability_issued_once');
    const publicDevice = providerRegistration.device as Record<string, unknown> | undefined;
    check(Boolean(publicDevice) && !('socketId' in (publicDevice ?? {})), 'public_device_hides_socket_id');
    check(Boolean(publicDevice) && !('capabilityDigest' in (publicDevice ?? {})), 'public_device_hides_capability_digest');
    check(Boolean(publicDevice) && !('userAgent' in (publicDevice ?? {})), 'public_device_hides_user_agent');

    const takeover = await openSocket(baseUrl);
    sockets.push(takeover);
    const takeoverResponse = await emitAck<AckResponse>(takeover, 'provider:register', {
      lobbyCode: code,
      deviceId: providerDeviceId,
      displayName: 'Attacker',
      providerName: 'Attacker',
      hospitalDepartment: 'clinical_immediate',
    });
    check(takeoverResponse.ok === false, 'provider_identity_takeover_rejected');

    const replacedEvent = waitForEvent<Record<string, unknown>>(providerOne, 'provider:connection-replaced');
    const providerTwo = await openSocket(baseUrl);
    sockets.push(providerTwo);
    const reconnectResponse = await emitAck<AckResponse>(providerTwo, 'provider:register', {
      lobbyCode: code,
      deviceId: providerDeviceId,
      displayName: 'Simulation Provider',
      providerName: 'Simulation Provider',
      hospitalDepartment: 'clinical_immediate',
      providerCapability,
    });
    const rotatedProviderCapability = typeof reconnectResponse.providerCapability === 'string'
      ? reconnectResponse.providerCapability
      : '';
    check(reconnectResponse.ok === true, 'capability_authorized_provider_reconnect_accepted');
    check(rotatedProviderCapability.length >= 40 && rotatedProviderCapability !== providerCapability, 'provider_capability_rotated_on_reconnect');
    const replacementNotice = await replacedEvent;
    check(typeof replacementNotice.message === 'string', 'stale_provider_notified_of_replacement');
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 25));
    check(providerOne.disconnected, 'stale_provider_socket_disconnected');

    const forgedProviderUpdate = await emitAck<AckResponse>(takeover, 'provider:update-name', {
      lobbyCode: code,
      deviceId: providerDeviceId,
      providerCapability: 'forged-provider-capability',
      displayName: 'Forged Name',
    });
    check(forgedProviderUpdate.ok === false, 'forged_provider_capability_rejected');

    const validProviderUpdate = await emitAck<AckResponse>(providerTwo, 'provider:update-name', {
      lobbyCode: code,
      deviceId: providerDeviceId,
      providerCapability: rotatedProviderCapability,
      displayName: 'Authorized Provider',
    });
    check(validProviderUpdate.ok === true, 'current_provider_socket_can_update_profile');

    const noPayloadPong = await emitAckWithoutPayload<AckResponse>(controller, 'hub:ping');
    check(noPayloadPong.ok === true, 'hub_ping_without_payload_ack_passes');

    const payloadPong = await emitAck<AckResponse>(controller, 'hub:ping', { probe: 'payload-and-ack' });
    check(payloadPong.ok === true, 'hub_ping_with_payload_ack_passes');

    const malformedBefore = hubRuntimeSnapshot().securityCounters.malformedAcknowledgementIgnored;
    emitMalformedAcknowledgement(controller, 'hub:ping', { probe: 'malformed-acknowledgement' });
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 25));
    const healthAfterMalformedAck = await fetch(`${baseUrl}/api/health`);
    check(healthAfterMalformedAck.ok, 'hub_survives_malformed_acknowledgement');
    const malformedAfter = hubRuntimeSnapshot().securityCounters.malformedAcknowledgementIgnored;
    check(malformedAfter === malformedBefore + 1, 'malformed_acknowledgement_is_audited');

    const pings: number[] = [];
    for (let index = 0; index < 40; index += 1) {
      const started = performance.now();
      const pong = await emitAck<AckResponse>(controller, 'hub:ping', {});
      pings.push(performance.now() - started);
      if (pong.ok !== true) errors.push('hub ping failed');
    }
    pings.sort((left, right) => left - right);
    const responseTime = {
      samples: pings.length,
      p50_ms: percentile(pings, 0.50),
      p95_ms: percentile(pings, 0.95),
      p99_ms: percentile(pings, 0.99),
      max_ms: pings.at(-1) ?? null,
      engineering_budget_p99_ms: 250,
    };
    check(responseTime.p99_ms <= responseTime.engineering_budget_p99_ms, 'hub_round_trip_engineering_budget_met');

    const snapshot = hubRuntimeSnapshot();
    check(snapshot.securityCounters.controllerAuthorizationRejected >= 1, 'controller_rejection_audited');
    check(snapshot.securityCounters.providerTakeoverRejected >= 1, 'provider_takeover_rejection_audited');

    const classification = errors.length === 0 ? 'PASS' : 'FAIL';
    const report = {
      schema_version: '1.0.0',
      classification,
      status: classification,
      assertions,
      response_time: responseTime,
      runtime_snapshot: snapshot,
      healthcare_simulation_training: 'PERMITTED_WITHIN_VALIDATED_SCOPE',
      direct_patient_care: 'PROHIBITED',
      clinical_decision_support: 'PROHIBITED',
      errors: [...new Set(errors)].sort(),
    };
    mkdirSync(dirname(output), { recursive: true });
    writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
    console.log(JSON.stringify(report, null, 2));
    return classification === 'PASS' ? 0 : 3;
  } catch (error) {
    const report = {
      schema_version: '1.0.0',
      classification: 'INTERNAL_ERROR',
      status: 'INTERNAL_ERROR',
      assertions,
      direct_patient_care: 'PROHIBITED',
      clinical_decision_support: 'PROHIBITED',
      errors: [...new Set([...errors, `${error instanceof Error ? error.name : 'Error'}:${error instanceof Error ? error.message : String(error)}`])].sort(),
    };
    mkdirSync(dirname(output), { recursive: true });
    writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
    console.error(JSON.stringify(report, null, 2));
    return 4;
  } finally {
    for (const socket of sockets) socket.disconnect();
    await new Promise<void>((resolvePromise) => io.close(() => resolvePromise()));
    if (httpServer.listening) {
      await new Promise<void>((resolvePromise) => httpServer.close(() => resolvePromise()));
    }
  }
}

process.exitCode = await main();
