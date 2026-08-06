import { useEffect, useRef } from "react";

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

type DataTableProps<T extends Record<string, unknown>> = {
  rows: T[] | undefined;
  columns: Array<{
    key: keyof T;
    /** Overrides the React key when two columns share the same data `key`. */
    id?: string;
    label: string;
    render?: (value: T[keyof T], row: T) => string;
  }>;
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
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    );
  }

  if (!rows?.length) {
    return <p className="text-sm text-muted-foreground">No records yet.</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          {columns.map((column) => (
            <TableHead key={column.id ?? String(column.key)}>{column.label}</TableHead>
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
              className={cn(isHighlighted && "bg-accent/40", onRowClick && "cursor-pointer")}
              key={rowKey}
              ref={isHighlighted ? highlightedRowRef : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((column) => {
                const value = row[column.key];
                return (
                  <TableCell key={column.id ?? String(column.key)}>
                    {column.render ? column.render(value, row) : String(value ?? "")}
                  </TableCell>
                );
              })}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
