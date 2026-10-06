import type { FeedEntry } from '@/types';

/** Entries visible to the provider mobile UI */
export function filterProviderFeed(feed: FeedEntry[]): FeedEntry[] {
  return feed.filter((entry) => {
    if (entry.audience === 'wit') return false;
    if (entry.type === 'evaluation') return false;
    if (entry.content.includes('WIT rule')) return false;
    return true;
  });
}

/** Entries for WIT live contextual timeline */
export function filterWitContextFeed(feed: FeedEntry[]): FeedEntry[] {
  return feed.filter(
    (entry) =>
      entry.type !== 'evaluation' ||
      entry.audience === 'wit' ||
      entry.trigger_prompt !== undefined,
  );
}
