import { useEffect, useRef, type ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

type DataTableColumn<T extends Record<string, unknown>> = {
  key: keyof T;
  /** Overrides the React key when two columns share the same data `key`. */
  id?: string;
  label: string;
  render?: (value: T[keyof T], row: T) => ReactNode;
  /** Mono font for IDs and other character-for-character data. */
  mono?: boolean;
  /** Numeric columns are right-aligned, tabular-nums, mono per the type spec. */
  align?: "left" | "right";
};

type DataTableProps<T extends Record<string, unknown>> = {
  rows: T[] | undefined;
  columns: Array<DataTableColumn<T>>;
  highlightId?: string;
  loading: boolean;
  onRowClick?: (row: T) => void;
};

export function DataTable<T extends Record<string, unknown>>({
  rows,
  columns,
  highlightId,
  loading,
  onRowClick,
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
    return (
      <div className="grid gap-2">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  }

  if (!rows?.length) {
    return <p className="text-sm text-muted-foreground">No records yet.</p>;
  }

  return (
    <div className="max-h-[560px] overflow-auto rounded-md border border-border/40">
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-card">
          <TableRow>
            {columns.map((column) => (
              <TableHead
                className={cn(column.align === "right" && "text-right")}
                key={column.id ?? String(column.key)}
              >
                {column.label}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => {
            const rowKey = String(row.id ?? index);
            const publicId = String(row.public_id ?? "");
            const isHighlighted = Boolean(
              highlightId && (rowKey === highlightId || publicId === highlightId),
            );

            return (
              <TableRow
                aria-current={isHighlighted ? "true" : undefined}
                className={cn(
                  "h-12",
                  isHighlighted && "bg-accent/40",
                  onRowClick && "cursor-pointer",
                )}
                key={rowKey}
                ref={isHighlighted ? highlightedRowRef : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                {columns.map((column) => {
                  const value = row[column.key];
                  return (
                    <TableCell
                      className={cn(
                        column.mono && "font-mono",
                        column.align === "right" && "text-right tabular-nums",
                      )}
                      key={column.id ?? String(column.key)}
                    >
                      {column.render ? column.render(value, row) : String(value ?? "")}
                    </TableCell>
                  );
                })}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
