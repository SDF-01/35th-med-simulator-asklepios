import { buildJoinPath, normalizeLobbyCode, type LobbyJoinRole } from '@/utils/lobbyCode';

const CONTROLLER_PREFIX = 'asklepios_controller_capability:';
const PROVIDER_PREFIX = 'asklepios_provider_capability:';
const FRAGMENT_KEY = 'asklepios-control';

function safeSessionStorage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

function key(prefix: string, code: string, suffix = ''): string {
  const normalized = normalizeLobbyCode(code);
  return `${prefix}${normalized}${suffix ? `:${suffix}` : ''}`;
}

export function saveControllerCapability(code: string, capability: string): void {
  if (!capability) return;
  safeSessionStorage()?.setItem(key(CONTROLLER_PREFIX, code), capability);
}

export function getControllerCapability(code: string): string | null {
  return safeSessionStorage()?.getItem(key(CONTROLLER_PREFIX, code)) ?? null;
}

export function clearControllerCapability(code: string): void {
  safeSessionStorage()?.removeItem(key(CONTROLLER_PREFIX, code));
}

export function saveProviderCapability(code: string, deviceId: string, capability: string): void {
  if (!capability) return;
  safeSessionStorage()?.setItem(key(PROVIDER_PREFIX, code, deviceId), capability);
}

export function getProviderCapability(code: string, deviceId: string): string | null {
  return safeSessionStorage()?.getItem(key(PROVIDER_PREFIX, code, deviceId)) ?? null;
}

export function clearProviderCapability(code: string, deviceId: string): void {
  safeSessionStorage()?.removeItem(key(PROVIDER_PREFIX, code, deviceId));
}

export function buildSecureControllerUrl(
  code: string,
  role: Extract<LobbyJoinRole, 'wit' | 'command'>,
  capability: string,
): string {
  const path = buildJoinPath(code, role);
  const fragment = new URLSearchParams({ [FRAGMENT_KEY]: capability }).toString();
  if (typeof window === 'undefined') return `${path}#${fragment}`;
  return `${window.location.origin}${path}#${fragment}`;
}

export function importControllerCapabilityFromFragment(code: string): boolean {
  if (typeof window === 'undefined' || !window.location.hash) return false;
  const raw = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash;
  const params = new URLSearchParams(raw);
  const capability = params.get(FRAGMENT_KEY);
  if (!capability) return false;
  saveControllerCapability(code, capability);
  params.delete(FRAGMENT_KEY);
  const remaining = params.toString();
  const replacement = `${window.location.pathname}${window.location.search}${remaining ? `#${remaining}` : ''}`;
  window.history.replaceState(window.history.state, document.title, replacement);
  return true;
}
