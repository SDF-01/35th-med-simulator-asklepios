import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { SectionLabel } from '@/components/ui/PageHeader';
import {
  PRACTICE_HISTORY_LIMIT,
  usePracticeHistoryStore,
  type PracticeHistoryEntry,
} from '@/store/practiceHistoryStore';

function formatCompletedAt(timestamp: number): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(timestamp));
  } catch {
    return new Date(timestamp).toLocaleString();
  }
}

function PracticeHistoryRow({ entry }: { entry: PracticeHistoryEntry }) {
  return (
    <li className="border-b border-ask-border/60 py-3 last:border-b-0 last:pb-0 first:pt-0">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ask-text">{entry.scenarioTitle}</p>
          <p className="mt-0.5 text-xs text-ask-muted">{formatCompletedAt(entry.completedAt)}</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Badge variant={entry.mode === 'solo' ? 'accent' : 'muted'}>
            {entry.mode === 'solo' ? 'Solo' : 'Exercise'}
          </Badge>
          <Badge variant={entry.passed ? 'success' : 'critical'}>
            {entry.passed ? 'PASS' : 'NEEDS WORK'}
          </Badge>
          <span className="font-mono text-sm tabular-nums">{entry.score}/100</span>
        </div>
      </div>
      <p className="mt-1 text-xs text-ask-text-dim">{entry.patientOutcome}</p>
    </li>
  );
}

/**
 * Local browser history of completed AAR / practice sessions (training only).
 */
export function PracticeHistoryPanel({ className = '' }: { className?: string }) {
  const entries = usePracticeHistoryStore((s) => s.entries);
  const clearHistory = usePracticeHistoryStore((s) => s.clearHistory);

  function handleClear() {
    if (entries.length === 0) return;
    const confirmed = window.confirm(
      'Clear all saved practice history on this device? This cannot be undone.',
    );
    if (confirmed) clearHistory();
  }

  return (
    <Card as="section" padding="md" className={className} aria-labelledby="practice-history-heading">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <SectionLabel id="practice-history-heading" accent>
          Past practices
        </SectionLabel>
        {entries.length > 0 && (
          <Button type="button" variant="ghost" size="sm" onClick={handleClear}>
            Clear history
          </Button>
        )}
      </div>
      <p className="mb-4 text-xs leading-relaxed text-ask-muted">
        Up to {PRACTICE_HISTORY_LIMIT} completed reviews stay on this device only. Training
        simulation records; not shared with a hub.
      </p>

      {entries.length === 0 ? (
        <EmptyState
          title="No past practices yet"
          description="Finish a solo run through after-action review to save a summary here."
        />
      ) : (
        <ul className="m-0 list-none p-0">
          {entries.map((entry) => (
            <PracticeHistoryRow key={entry.id} entry={entry} />
          ))}
        </ul>
      )}
    </Card>
  );
}
