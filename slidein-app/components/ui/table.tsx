import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The table primitives. Same contract as workspace-app: hairline rows inside
 * a Surface, tabular numerals for every numeric column, no per-row cards.
 */

export function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div className="w-full overflow-x-auto">
      <table
        className={cn("w-full border-collapse text-left text-[0.8125rem]", className)}
        {...props}
      />
    </div>
  );
}

export function THead({ className, ...props }: React.ComponentProps<"thead">) {
  return <thead className={cn("border-b border-rule", className)} {...props} />;
}

export function TBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return <tbody className={cn("divide-y divide-rule", className)} {...props} />;
}

export function TR({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      className={cn(
        "transition-colors hover:bg-surface-2/60 data-[selected=true]:bg-flame-wash",
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
      className={cn(
        "px-3 py-2 font-label text-ink-faint",
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
      className={cn(
        "px-3 py-2 align-middle text-ink-muted",
        align === "right" && "text-right font-value tabular-nums",
        align === "center" && "text-center",
        className,
      )}
      {...props}
    />
  );
}
