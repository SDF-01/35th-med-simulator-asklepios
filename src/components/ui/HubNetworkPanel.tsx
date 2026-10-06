import { Badge } from '@/components/ui/Badge';
import { useHubStatus } from '@/hooks/useHubStatus';
import { getHubDisplayUrl } from '@/utils/hubUrl';

interface HubNetworkPanelProps {
  compact?: boolean;
  className?: string;
}

export function HubNetworkPanel({ compact = false, className = '' }: HubNetworkPanelProps) {
  const { connection, health } = useHubStatus();

  const variant =
    connection === 'online' ? 'success' : connection === 'offline' ? 'critical' : 'muted';
  const label =
    connection === 'online'
      ? 'Hub online'
      : connection === 'offline'
        ? 'Hub offline'
        : 'Connecting…';

  if (compact) {
    return (
      <div className={`hub-network-panel hub-network-panel--compact ${className}`.trim()}>
        <Badge variant={variant}>{label}</Badge>
        {connection === 'online' && health && (
          <span className="text-xs text-ask-muted">{health.devices} device(s) on network</span>
        )}
      </div>
    );
  }

  return (
    <div className={`hub-network-panel ${className}`.trim()}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={variant}>{label}</Badge>
        {health && (
          <span className="text-xs text-ask-muted">
            Hub v{health.version} · {health.devices} device(s)
            {health.activeExercise ? ` · Exercise: ${health.activeExercise.title}` : ''}
          </span>
        )}
      </div>
      <p className="mt-2 font-mono text-xs text-ask-muted break-all">{getHubDisplayUrl()}</p>
      {connection === 'online' && (
        <p className="mt-1 text-xs text-ask-muted">
          Providers, WIT, and command reconnect automatically if the link drops.
        </p>
      )}
    </div>
  );
}
