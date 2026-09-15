export type TimelineFeedItem = {
  id: string;
  timestamp: string;
  tag: string;
  description: string;
};

export function TimelineFeed({ items }: { items: TimelineFeedItem[] }) {
  if (!items.length) {
    return <p className="text-sm text-muted-foreground">Inga händelser ännu.</p>;
  }

  return (
    <div className="timeline-list min-w-0 w-full">
      {items.map((item) => (
        <div className="timeline-item min-w-0" key={item.id}>
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] font-semibold">
            <span className="shrink-0 text-muted-foreground/90">{item.timestamp}</span>
            <span className="break-words text-primary">{item.tag}</span>
          </div>
          <p className="m-0 min-w-0 break-words text-[13px] font-normal text-muted-foreground">
            {item.description}
          </p>
        </div>
      ))}
    </div>
  );
}
