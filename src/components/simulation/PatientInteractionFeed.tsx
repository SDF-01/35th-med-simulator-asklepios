import { useEffect, useRef } from 'react';
import type { FeedEntry } from '@/types';
import { filterProviderFeed } from '@/utils/feedFilters';
import { FeedEntryBody } from '@/components/simulation/FeedEntryBody';

const FEED_CLASS: Record<FeedEntry['type'], string> = {
  system: 'feed-entry feed-entry--system',
  user: 'feed-entry feed-entry--user',
  patient: 'feed-entry feed-entry--patient',
  alert: 'feed-entry feed-entry--alert',
  evaluation: 'feed-entry feed-entry--evaluation',
  response: 'feed-entry feed-entry--response',
};

const FEED_LABEL: Record<FeedEntry['type'], string> = {
  system: 'System',
  user: 'You',
  patient: 'Patient',
  alert: 'Alert',
  evaluation: 'Eval',
  response: 'Response',
};

interface PatientInteractionFeedProps {
  feed: FeedEntry[];
  activePatientId?: string;
  viewMode?: 'focused' | 'all';
}

export function PatientInteractionFeed({
  feed,
  activePatientId,
  viewMode = 'focused',
}: PatientInteractionFeedProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const visibleFeed = filterProviderFeed(feed).filter((entry) => {
    if (viewMode === 'all') return true;
    if (!activePatientId) return true;
    if (!entry.patient_id) return true;
    return entry.patient_id === activePatientId;
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [visibleFeed]);

  return (
    <div
      className="flex h-full flex-col overflow-y-auto pr-1"
      role="log"
      aria-live="polite"
      aria-relevant="additions"
      aria-label="Patient interaction feed"
    >
      {visibleFeed.length === 0 && (
        <p className="py-8 text-center text-sm italic text-ask-muted">
          Begin your assessment. Enter observations or orders below.
        </p>
      )}
      <div className="space-y-2.5">
        {visibleFeed.map((entry) => (
          <article key={entry.id} className={FEED_CLASS[entry.type]}>
            <p className="feed-entry__label">
              {entry.patient_id && viewMode === 'all' ? `${entry.patient_id} · ` : ''}
              {FEED_LABEL[entry.type]}
            </p>
            <FeedEntryBody content={entry.content} heading={entry.heading} bullets={entry.bullets} />
          </article>
        ))}
      </div>
      <div ref={bottomRef} />
    </div>
  );
}
