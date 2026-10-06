import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import type { ProviderDevice } from '@/types/device';
import { getDepartmentLabel } from '@/types/providerProfile';

interface LobbyPlayerRosterProps {
  players: ProviderDevice[];
  className?: string;
}

export function LobbyPlayerRoster({ players, className = '' }: LobbyPlayerRosterProps) {
  return (
    <Card padding="md" className={className}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-ask-text">Players in lobby</h2>
        <Badge variant={players.length > 0 ? 'success' : 'muted'}>{players.length}</Badge>
      </div>

      {players.length === 0 ? (
        <EmptyState
          title="Waiting for players"
          description="Providers join by entering your exercise code on their phones."
          className="py-6"
        />
      ) : (
        <ul className="space-y-2">
          {players.map((player) => (
            <li
              key={player.deviceId}
              className="flex items-center justify-between gap-3 rounded-md border border-ask-border px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate font-medium">{player.displayName}</p>
                <p className="truncate text-xs text-ask-muted">
                  {getDepartmentLabel(player.hospitalDepartment ?? 'clinical_immediate')}
                </p>
              </div>
              <Badge variant="muted" className="shrink-0 capitalize">
                {player.status === 'waiting' ? 'Ready' : player.status.replace('_', ' ')}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
