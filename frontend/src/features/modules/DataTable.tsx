import { useEffect, useRef } from "react";

type DataTableProps<T extends Record<string, unknown>> = {
  rows: T[] | undefined;
  columns: Array<{
    key: keyof T;
    label: string;
    render?: (value: T[keyof T], row: T) => string;
  }>;
  highlightId?: string;
  loading: boolean;
};

export function DataTable<T extends Record<string, unknown>>({
  rows,
  columns,
  highlightId,
  loading,
}: DataTableProps<T>) {
  const highlightedRowRef = useRef<HTMLTableRowElement | null>(null);

  useEffect(() => {
    if (!highlightId || !highlightedRowRef.current) {
      return;
    }

    highlightedRowRef.current.scrollIntoView({
      block: "center",
      behavior: "smooth",
    });
  }, [highlightId, rows]);

  if (loading) {
    return <p className="muted">Syncing with backend...</p>;
  }

  if (!rows?.length) {
    return <p className="muted">No records yet.</p>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={String(column.key)}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const rowKey = String(row.id ?? index);
            const publicId = String(row.public_id ?? "");
            const isHighlighted = Boolean(
              highlightId && (rowKey === highlightId || publicId === highlightId),
            );

            return (
              <tr
                aria-current={isHighlighted ? "true" : undefined}
                className={isHighlighted ? "highlight-row" : undefined}
                key={rowKey}
                ref={isHighlighted ? highlightedRowRef : undefined}
              >
                {columns.map((column) => {
                  const value = row[column.key];
                  return (
                    <td key={String(column.key)}>
                      {column.render ? column.render(value, row) : String(value ?? "")}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
