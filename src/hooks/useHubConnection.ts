import { useEffect, useState } from 'react';
import { subscribeHubConnection, type HubConnectionState } from '@/services/networkHub';

export function useHubConnection(): HubConnectionState {
  const [state, setState] = useState<HubConnectionState>('connecting');

  useEffect(() => subscribeHubConnection(setState), []);

  return state;
}
