import { useEffect, useState } from 'react';
import {
  fetchHubHealth,
  getHubUrl,
  subscribeHubConnection,
  type HubConnectionState,
} from '@/services/networkHub';
import type { HubHealthResponse } from '@/types/hub';

export interface HubStatus {
  connection: HubConnectionState;
  hubUrl: string;
  health: HubHealthResponse | null;
}

export function useHubStatus(pollMs = 30_000): HubStatus {
  const [connection, setConnection] = useState<HubConnectionState>('connecting');
  const [health, setHealth] = useState<HubHealthResponse | null>(null);

  useEffect(() => subscribeHubConnection(setConnection), []);

  useEffect(() => {
    let cancelled = false;

    async function loadHealth() {
      if (connection !== 'online') {
        if (!cancelled) setHealth(null);
        return;
      }
      const result = await fetchHubHealth();
      if (!cancelled) setHealth(result);
    }

    loadHealth();
    const interval = setInterval(loadHealth, pollMs);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [connection, pollMs]);

  return {
    connection,
    hubUrl: getHubUrl(),
    health,
  };
}
