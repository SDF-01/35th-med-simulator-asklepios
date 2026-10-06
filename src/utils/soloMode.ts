const SOLO_MODE_KEY = 'asklepios_solo_mode';

let memorySolo = false;

/** True when practicing alone without a live exercise hub. */
export function isSoloMode(): boolean {
  if (memorySolo) return true;
  if (typeof sessionStorage === 'undefined') return false;
  return sessionStorage.getItem(SOLO_MODE_KEY) === '1';
}

export function enableSoloMode(): void {
  memorySolo = true;
  if (typeof sessionStorage !== 'undefined') {
    sessionStorage.setItem(SOLO_MODE_KEY, '1');
  }
}

export function disableSoloMode(): void {
  memorySolo = false;
  if (typeof sessionStorage !== 'undefined') {
    sessionStorage.removeItem(SOLO_MODE_KEY);
  }
}
