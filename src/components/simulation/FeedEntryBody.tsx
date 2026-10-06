interface FeedEntryBodyProps {
  content: string;
  heading?: string;
  bullets?: string[];
}

export function FeedEntryBody({ content, heading, bullets }: FeedEntryBodyProps) {
  const trimmed = content.trim();
  const hasBullets = bullets && bullets.length > 0;

  return (
    <div className="feed-entry__content">
      {heading ? <p className="feed-entry__heading">{heading}</p> : null}
      {trimmed ? <p className="feed-entry__body">{trimmed}</p> : null}
      {hasBullets ? (
        <ul className="feed-entry__bullets">
          {bullets.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
