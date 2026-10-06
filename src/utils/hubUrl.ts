/** Hub origin used by Socket.IO and REST health checks. */
export function resolveHubUrl(): string {
  const configured = import.meta.env.VITE_HUB_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, '');
  }

  // Local dev: Vite proxies /socket.io and /api to the hub on port 3021.
  // Production: hub is served from the same Vercel deployment via api/hub.ts.
  return window.location.origin;
}

/** Optional override when the hub runs on a different host than the SPA. */
export function hasExternalHubUrl(): boolean {
  return Boolean(import.meta.env.VITE_HUB_URL?.trim());
}

export function getHubDisplayUrl(): string {
  return resolveHubUrl();
}
