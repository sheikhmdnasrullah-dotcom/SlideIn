"use client";

import { cn } from "@/lib/utils";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { LoadingState } from "./states";

/**
 * DataTable: the shared table contract for every section.
 *
 * Columns are declared once and reused by the row renderer, the empty state
 * and the loading skeleton, so a table can never render three different
 * shapes for the same data.
 */
export interface Column<T> {
  key: string;
  header: string;
  align?: "left" | "right" | "center";
  width?: string;
  render: (row: T) => React.ReactNode;
}

export function DataTable<T>({
  columns,
  rows,
  keyOf,
  loading = false,
  loadingRows = 5,
  empty,
  onRowClick,
  rowHref,
  footer,
  className,
}: {
  columns: Column<T>[];
  rows: T[];
  keyOf: (row: T) => string;
  loading?: boolean;
  loadingRows?: number;
  empty?: React.ReactNode;
  onRowClick?: (row: T) => void;
  rowHref?: (row: T) => string;
  footer?: React.ReactNode;
  className?: string;
}) {
  if (loading) {
    return (
      <div className={cn("px-4 py-3", className)}>
        <LoadingState rows={loadingRows} />
      </div>
    );
  }

  if (rows.length === 0) {
    return <div className={cn("px-4 py-6", className)}>{empty}</div>;
  }

  return (
    <>
      <Table className={className}>
        <THead>
          <TR className="hover:bg-transparent">
            {columns.map((column) => (
              <TH key={column.key} align={column.align} style={{ width: column.width }}>
                {column.header}
              </TH>
            ))}
          </TR>
        </THead>
        <TBody>
          {rows.map((row) => {
            const key = keyOf(row);
            return (
              <TR
                key={key}
                data-selected={false}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={cn((onRowClick || rowHref) && "cursor-pointer")}
              >
                {columns.map((column) => (
                  <TD key={column.key} align={column.align}>
                    {column.render(row)}
                  </TD>
                ))}
              </TR>
            );
          })}
        </TBody>
      </Table>
      {footer}
    </>
  );
}
