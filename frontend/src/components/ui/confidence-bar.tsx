import { cn } from "@/lib/utils";

type ConfidenceBarProps = {
  value: number;
  className?: string;
};

/** 0-100 confidence bar per the explainable-AI pattern: never a silent number alone. */
export function ConfidenceBar({ value, className }: ConfidenceBarProps) {
  const percent = Math.round(value * 100);
  const tone = percent < 65 ? "bg-warning" : "bg-accent";

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${percent}%` }} />
      </div>
      <span className="font-mono text-xs tabular-nums text-muted-foreground">{percent}%</span>
    </div>
  );
}
