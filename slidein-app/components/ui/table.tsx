import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The table primitives. Header row 12/500 muted on #FDFDFD at 44px;
 * body rows breathe at 64px with 6% hairline dividers, no vertical lines,
 * no zebra; hover is #FAFAFA over 150ms. Numbers right-aligned tabular.
 */

export function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div data-slot="table-card" className="w-full overflow-x-auto">
      <table
        data-slot="table"
        className={cn("w-full border-collapse text-left text-sm", className)}
        {...props}
      />
    </div>
  );
}

export function THead({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-head"
      className={cn("border-b border-rule bg-table-header", className)}
      {...props}
    />
  );
}

export function TBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("divide-y divide-rule-soft", className)}
      {...props}
    />
  );
}

export function TR({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "transition-colors duration-[150ms] hover:bg-surface-2 data-[selected=true]:bg-flame-wash",
        className,
      )}
      {...props}
    />
  );
}

export function TH({
  className,
  align = "left",
  ...props
}: React.ComponentProps<"th"> & { align?: "left" | "right" | "center" }) {
  return (
    <th
      data-slot="table-header-cell"
      className={cn(
        "h-11 px-6 align-middle font-label whitespace-nowrap text-ink-muted",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className,
      )}
      {...props}
    />
  );
}

export function TD({
  className,
  align = "left",
  ...props
}: React.ComponentProps<"td"> & { align?: "left" | "right" | "center" }) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "px-6 py-3 align-middle text-ink-muted",
        align === "right" && "text-right font-value tabular-nums",
        align === "center" && "text-center",
        className,
      )}
      {...props}
    />
  );
}
