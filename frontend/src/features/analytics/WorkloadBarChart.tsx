type WorkloadRow = { weekday: string; ai: number; manual: number };

export function WorkloadBarChart({ rows }: { rows: WorkloadRow[] }) {
  const max = Math.max(1, ...rows.map((r) => r.ai + r.manual));

  return (
    <div className="flex flex-col gap-3">
      {rows.map((row) => {
        const total = row.ai + row.manual;
        const aiPercent = (row.ai / max) * 100;
        const manualPercent = (row.manual / max) * 100;
        return (
          <div className="flex items-center gap-4" key={row.weekday}>
            <span className="w-20 text-xs text-muted-foreground">{row.weekday}</span>
            <div className="flex h-4 flex-1 gap-1">
              <div
                className="rounded-l-sm bg-primary"
                style={{ width: `${aiPercent}%` }}
                title={`AI: ${row.ai}`}
              />
              <div
                className="rounded-r-sm bg-muted-foreground"
                style={{ width: `${manualPercent}%` }}
                title={`Manuell: ${row.manual}`}
              />
            </div>
            <span className="w-14 text-right text-xs font-semibold">{total}st</span>
          </div>
        );
      })}
      <div className="mt-2 flex items-center gap-6 text-xs text-muted-foreground">
        <span className="flex items-center gap-2">
          <span className="size-3 rounded-sm bg-primary" /> Automatiskt av Qinora AI
        </span>
        <span className="flex items-center gap-2">
          <span className="size-3 rounded-sm bg-muted-foreground" /> Manuell operatörshantering
        </span>
      </div>
    </div>
  );
}
