const LOBBY_CODE_KEY = 'asklepios_lobby_code';

export function normalizeLobbyCode(raw: string): string {
  return raw.trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
}

export function isValidLobbyCode(code: string): boolean {
  const normalized = normalizeLobbyCode(code);
  return normalized.length >= 4 && normalized.length <= 8;
}

export function saveLobbyCode(code: string): void {
  const normalized = normalizeLobbyCode(code);
  if (!normalized) return;
  localStorage.setItem(LOBBY_CODE_KEY, normalized);
}

export function getSavedLobbyCode(): string | null {
  const raw = localStorage.getItem(LOBBY_CODE_KEY);
  if (!raw) return null;
  const normalized = normalizeLobbyCode(raw);
  return normalized || null;
}

export function clearLobbyCode(): void {
  localStorage.removeItem(LOBBY_CODE_KEY);
}

export type LobbyJoinRole = 'provider' | 'wit' | 'command';

export function buildJoinPath(code: string, role?: LobbyJoinRole): string {
  const normalized = normalizeLobbyCode(code);
  if (!role) return `/join/${encodeURIComponent(normalized)}`;
  return `/join/${encodeURIComponent(normalized)}/${role}`;
}

export function buildJoinUrl(code: string, role: LobbyJoinRole = 'provider'): string {
  if (typeof window === 'undefined') return buildJoinPath(code, role);
  return `${window.location.origin}${buildJoinPath(code, role)}`;
}
