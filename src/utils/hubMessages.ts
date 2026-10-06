import { hasExternalHubUrl, resolveHubUrl } from '@/utils/hubUrl';

export type HubSetupIssue = 'ok' | 'dev' | 'unreachable';

export function getHubSetupIssue(connection: 'connecting' | 'online' | 'offline'): HubSetupIssue {
  if (import.meta.env.DEV) return 'dev';
  if (connection === 'online') return 'ok';
  return 'unreachable';
}

export function getHubOfflineMessage(): string {
  if (import.meta.env.DEV) {
    return 'Start the exercise hub with npm run dev, then create or join a lobby.';
  }

  if (hasExternalHubUrl()) {
    const hubUrl = import.meta.env.VITE_HUB_URL;
    return `Cannot reach the hub at ${hubUrl}. Confirm that service is running.`;
  }

  return 'Cannot reach the exercise hub on this site. Redeploy the Vercel project (api/hub must be included) or run npm run dev on your laptop for local Wi‑Fi exercises.';
}

export function getHubSetupSteps(): string[] {
  if (import.meta.env.DEV) {
    return ['Run npm run dev on your machine.', 'Open /host and create an exercise.'];
  }

  return [
    'Redeploy project-asklepios on Vercel so api/hub.ts is live (same URL as the app, no second host).',
    'Ensure Vercel Fluid compute is enabled (default on newer projects) for WebSocket support.',
    'Reload /host and tap Create exercise again.',
    'Optional: for field exercises without cloud deploy, run npm run dev on the WIT laptop and share your LAN URL (e.g. http://192.168.1.10:5183/join).',
    'Optional: only set VITE_HUB_URL if you host the hub on a different domain than the SPA.',
  ];
}

export function assertHubAvailableForLobby(): void {
  // Lobby creation is validated at runtime via /api/health and Socket.IO connect.
}

export function getHubDisplayLabel(): string {
  return resolveHubUrl();
}
