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
    <div className="timeline-list">
      {items.map((item) => (
        <div className="timeline-item" key={item.id}>
          <div className="flex items-center gap-2 text-[11px] font-semibold">
            <span className="text-muted-foreground/90">{item.timestamp}</span>
            <span className="text-primary">{item.tag}</span>
          </div>
          <p className="m-0 text-[13px] font-normal text-muted-foreground">{item.description}</p>
        </div>
      ))}
    </div>
  );
}
