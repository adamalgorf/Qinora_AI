import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type PriorityListItemProps = {
  eyebrow?: string;
  title: string;
  detail?: string;
  tag?: ReactNode;
  active?: boolean;
  onClick?: () => void;
};

export function PriorityListItem({
  eyebrow,
  title,
  detail,
  tag,
  active,
  onClick,
}: PriorityListItemProps) {
  const Tag = onClick ? "button" : "div";

  return (
    <Tag
      className={cn("priority-row", active && "priority-row-active")}
      onClick={onClick}
      type={onClick ? "button" : undefined}
    >
      <div className="priority-row-meta min-w-0">
        {eyebrow ? <p className="priority-row-id break-words">{eyebrow}</p> : null}
        <p className="priority-row-title break-words">{title}</p>
        {detail ? <p className="priority-row-detail break-words">{detail}</p> : null}
      </div>
      {tag ? <div className="shrink-0">{tag}</div> : null}
    </Tag>
  );
}

export function PriorityList({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-3">{children}</div>;
}
