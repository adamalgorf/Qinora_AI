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
        <h1>{subtitle ? `${title} — ${subtitle}` : title}</h1>
        <div className="page-shell-header-right">
          {showStatusPill ? <span className="status-pill-live">Systemet i drift</span> : null}
          <span className="text-[13px] text-muted-foreground">
            Idag: {dateFormatter.format(new Date())}
          </span>
        </div>
      </header>
      <div className="page-shell-content">{children}</div>
    </section>
  );
}
