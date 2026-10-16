import Link from "next/link";

import { cn } from "@/lib/utils";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { LoadingState } from "./states";

/**
 * DataTable: the shared table contract for every section.
 *
 * Columns are declared once and reused by the row renderer, the empty state
 * and the loading skeleton, so a table can never render three different
 * shapes for the same data.
 *
 * A server component: column render functions run on the server, so pages
 * pass closures freely. When `rowHref` is set, the first cell links to it;
 * remaining cells (including action buttons) stay untouched, which keeps
 * the HTML valid where a row-level anchor would not.
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
            const href = rowHref?.(row);
            return (
              <TR key={key}>
                {columns.map((column, index) => (
                  <TD key={column.key} align={column.align}>
                    {index === 0 && href ? (
                      <Link
                        href={href}
                        className="decoration-flame-ring decoration-1 underline-offset-4 hover:underline"
                      >
                        {column.render(row)}
                      </Link>
                    ) : (
                      column.render(row)
                    )}
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
