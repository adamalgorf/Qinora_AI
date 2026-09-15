import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type AiInsightBannerProps = {
  icon: LucideIcon;
  heading: string;
  body: ReactNode;
  action?: ReactNode;
};

export function AiInsightBanner({ icon: Icon, heading, body, action }: AiInsightBannerProps) {
  return (
    <div className="ai-banner">
      <div className="ai-banner-icon">
        <Icon aria-hidden="true" size={20} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="ai-banner-heading break-words">{heading}</p>
        <div className="ai-banner-body break-words">{body}</div>
        {action ? <div className="mt-3 flex flex-wrap gap-2">{action}</div> : null}
      </div>
    </div>
  );
}
