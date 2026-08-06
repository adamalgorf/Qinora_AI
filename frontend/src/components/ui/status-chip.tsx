import { cn } from "@/lib/utils";

type StatusTone = "neutral" | "positive" | "warning" | "destructive";

const TONE_CLASSES: Record<StatusTone, string> = {
  neutral: "bg-info/10 text-info",
  positive: "bg-accent/10 text-accent",
  warning: "bg-warning/10 text-warning",
  destructive: "bg-destructive/10 text-destructive",
};

const TONE_DOT: Record<StatusTone, string> = {
  neutral: "bg-info",
  positive: "bg-accent",
  warning: "bg-warning",
  destructive: "bg-destructive",
};

// Every status across requests/quotes/shipments/invoices/inbox, grouped by
// what it means to an operator - never improvise a new hue per screen.
const STATUS_TONE: Record<string, StatusTone> = {
  // in progress / neutral
  draft: "neutral",
  sent: "neutral",
  viewed: "neutral",
  parsing: "neutral",
  quote_sent: "neutral",
  booked: "neutral",
  in_transit: "neutral",
  revision_requested: "neutral",
  pending: "neutral",
  transport_request: "neutral",
  invoice: "neutral",
  // resolved / positive
  parsed: "positive",
  quoted: "positive",
  accepted: "positive",
  delivered: "positive",
  revised: "positive",
  converted: "positive",
  approved: "positive",
  invoice_approved: "positive",
  // needs a human
  needs_clarification: "warning",
  needs_review: "warning",
  manual_review: "warning",
  // terminal / negative
  rejected: "destructive",
  expired: "destructive",
  cancelled: "destructive",
  disputed: "destructive",
  invoice_disputed: "destructive",
};

type StatusChipProps = {
  status: string;
  className?: string;
};

export function StatusChip({ status, className }: StatusChipProps) {
  const tone = STATUS_TONE[status] ?? "neutral";

  return (
    <span
      className={cn(
        "inline-flex w-fit items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium",
        TONE_CLASSES[tone],
        className,
      )}
    >
      <span aria-hidden="true" className={cn("size-1.5 rounded-full", TONE_DOT[tone])} />
      {status}
    </span>
  );
}
