import type { ReactNode } from "react";

type PageShellProps = {
  title: string;
  subtitle?: string;
  showStatusPill?: boolean;
  children: ReactNode;
};

const dateFormatter = new Intl.DateTimeFormat("sv-SE", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function PageShell({ title, subtitle, showStatusPill = true, children }: PageShellProps) {
  return (
    <section>
      <header className="page-shell-header">
        <h1 title={subtitle ? `${title} — ${subtitle}` : title}>
          {subtitle ? `${title} — ${subtitle}` : title}
        </h1>
        <div className="page-shell-header-right">
          {showStatusPill ? (
            <span className="status-pill-live hidden sm:inline-flex">Systemet i drift</span>
          ) : null}
          <span className="hidden whitespace-nowrap text-[13px] text-muted-foreground md:inline">
            Idag: {dateFormatter.format(new Date())}
          </span>
        </div>
      </header>
      <div className="page-shell-content">{children}</div>
    </section>
  );
}
