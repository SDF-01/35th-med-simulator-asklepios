import type { FeedEntry } from '@/types';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { SectionLabel } from '@/components/ui/PageHeader';

interface WitLiveProviderInputsProps {
  feed: FeedEntry[];
  currentTurn: number;
}

export function WitLiveProviderInputs({ feed, currentTurn }: WitLiveProviderInputsProps) {
  const userEntries = feed.filter((entry) => entry.type === 'user');

  return (
    <Card as="section" padding="md" aria-labelledby="wit-provider-inputs-title">
      <div className="mb-3 flex items-center justify-between gap-2">
        <SectionLabel accent id="wit-provider-inputs-title">
          Live Provider Inputs
        </SectionLabel>
        <Badge variant="muted">Turn {currentTurn}</Badge>
      </div>
      {userEntries.length === 0 ? (
        <p className="text-sm italic text-ask-muted">Waiting for provider text input...</p>
      ) : (
        <div className="max-h-80 space-y-3 overflow-y-auto">
          {userEntries.map((entry, index) => (
            <blockquote
              key={entry.id}
              className="rounded-ask-sm border-l-2 border-ask-accent bg-ask-bg/60 py-2 pl-3"
            >
              <p className="mb-1 text-[10px] uppercase tracking-widest text-ask-muted">
                Input {index + 1}
              </p>
              <p className="text-sm leading-relaxed text-ask-text">{entry.content}</p>
            </blockquote>
          ))}
        </div>
      )}
    </Card>
  );
}

interface WitLiveFeedProps {
  feed: FeedEntry[];
}

export function WitLiveFeed({ feed }: WitLiveFeedProps) {
  return (
    <Card as="section" padding="md" aria-labelledby="wit-scenario-feed-title">
      <SectionLabel id="wit-scenario-feed-title" className="mb-3">
        Scenario Feed
      </SectionLabel>
      <div className="max-h-80 space-y-2 overflow-y-auto text-sm" role="log" aria-live="polite">
        {feed.slice(-20).map((entry) => (
          <p key={entry.id} className="leading-relaxed text-ask-text/90">
            <span
              className={`text-xs uppercase ${entry.type === 'user' ? 'text-ask-accent' : 'text-ask-muted'}`}
            >
              {entry.type}:{' '}
            </span>
            {entry.content}
          </p>
        ))}
      </div>
    </Card>
  );
}
