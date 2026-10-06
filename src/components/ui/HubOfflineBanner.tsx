import { useHubConnection } from '@/hooks/useHubConnection';
import { getHubOfflineMessage } from '@/utils/hubMessages';

export function HubOfflineBanner() {
  const hubState = useHubConnection();

  if (hubState === 'online') {
    return null;
  }

  const isConnecting = hubState === 'connecting';

  return (
    <div
      role="status"
      className={`shrink-0 border-b px-4 py-2.5 text-sm leading-relaxed ${
        isConnecting
          ? 'border-ask-border bg-ask-surface text-ask-muted'
          : 'border-ask-critical/35 bg-ask-critical/10 text-ask-text-dim'
      }`}
    >
      <p className="font-medium text-ask-text">
        {isConnecting ? 'Connecting to exercise hub…' : 'Exercise hub offline'}
      </p>
      {!isConnecting && <p className="mt-1 text-xs text-ask-muted">{getHubOfflineMessage()}</p>}
    </div>
  );
}
