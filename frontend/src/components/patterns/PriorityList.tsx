import type { ReactNode } from "react";

type PriorityListItemProps = {
  eyebrow?: string;
  title: string;
  detail?: string;
  tag?: ReactNode;
  onClick?: () => void;
};

export function PriorityListItem({ eyebrow, title, detail, tag, onClick }: PriorityListItemProps) {
  const Tag = onClick ? "button" : "div";

  return (
    <Tag className="priority-row" onClick={onClick} type={onClick ? "button" : undefined}>
      <div className="priority-row-meta">
        {eyebrow ? <p className="priority-row-id">{eyebrow}</p> : null}
        <p className="priority-row-title">{title}</p>
        {detail ? <p className="priority-row-detail">{detail}</p> : null}
      </div>
      {tag}
    </Tag>
  );
}

export function PriorityList({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-3">{children}</div>;
}
