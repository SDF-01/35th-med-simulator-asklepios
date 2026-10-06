import type { FeedEntry } from '@/types';

import { Card } from '@/components/ui/Card';

import { EmptyState } from '@/components/ui/EmptyState';



function formatTime(timestamp: number, startTime: number): string {

  const sec = Math.max(0, Math.floor((timestamp - startTime) / 1000));

  const m = Math.floor(sec / 60);

  const s = sec % 60;

  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;

}



interface WitContextualTimelineProps {

  feed: FeedEntry[];

  startTime: number;

}



export function WitContextualTimeline({ feed, startTime }: WitContextualTimelineProps) {

  const contextual = feed.filter(

    (entry) =>

      entry.trigger_prompt ||

      entry.type === 'user' ||

      entry.type === 'evaluation' ||

      entry.type === 'alert',

  );



  if (contextual.length === 0) {

    return (

      <EmptyState

        title="Waiting for interaction"

        description="Contextual timeline will appear as the provider interacts with the scenario."

        className="py-8"

      />

    );

  }



  return (

    <div

      className="max-h-96 space-y-3 overflow-y-auto"

      role="log"

      aria-live="polite"

      aria-label="Contextual timeline"

    >

      {contextual.slice(-30).map((entry) => (

        <Card key={entry.id} padding="sm" className="bg-ask-bg/40">

          <div className="mb-1 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wider text-ask-muted">

            <time dateTime={new Date(entry.timestamp).toISOString()}>

              {formatTime(entry.timestamp, startTime)}

            </time>

            {entry.turn !== undefined && <span>Turn {entry.turn}</span>}

            {entry.patient_id && <span>{entry.patient_id}</span>}

            <span className="text-ask-accent">{entry.type}</span>

          </div>

          {entry.trigger_prompt && entry.type !== 'user' && (

            <p className="mb-2 border-l-2 border-ask-muted pl-2 text-xs text-ask-muted">

              In response to: &quot;{entry.trigger_prompt}&quot;

            </p>

          )}

          <p className="leading-relaxed text-ask-text/90">{entry.content}</p>

        </Card>

      ))}

    </div>

  );

}


