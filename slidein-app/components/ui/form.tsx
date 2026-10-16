import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Form primitives. 44px white fields, 14px radius, strong hairline;
 * focus is an ink border plus a 4px accent ring; errors swap both to danger.
 */

const fieldClass =
  "w-full bg-surface text-sm text-ink-strong border border-rule-strong placeholder:text-ink-faint transition-[border-color,box-shadow] duration-[120ms] hover:border-[var(--input-focus-border)] focus-visible:border-[var(--input-focus-border)] focus-visible:shadow-[0_0_0_4px_var(--input-focus-ring)] focus-visible:outline-none aria-invalid:border-status-danger aria-invalid:focus-visible:shadow-[0_0_0_4px_var(--status-danger-bg)] disabled:pointer-events-none disabled:opacity-40";

export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      data-slot="input"
      className={cn("h-11 rounded-md px-3.5", fieldClass, className)}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn("min-h-[88px] rounded-md px-3.5 py-3 leading-relaxed", fieldClass, className)}
      {...props}
    />
  );
}

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("flex flex-col", className)}>
      <span className="mb-2 font-sans text-[13px] leading-[18px] font-medium text-ink-strong">
        {label}
      </span>
      {children}
      {hint && (
        <span className="mt-1.5 font-sans text-xs leading-4 text-ink-muted">{hint}</span>
      )}
    </label>
  );
}

export function Select({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="select"
      className={cn("h-11 rounded-md px-3.5 pr-9", fieldClass, className)}
      {...props}
    />
  );
}

export function Checkbox({
  className,
  label,
  ...props
}: React.ComponentProps<"input"> & { label: React.ReactNode }) {
  return (
    <label className={cn("flex items-center gap-2 text-sm text-ink-muted", className)}>
      <input
        type="checkbox"
        data-slot="checkbox"
        className="size-4 shrink-0 rounded-xs border-rule-strong accent-[var(--accent-vivid)] focus-ring"
        {...props}
      />
      {label}
    </label>
  );
}
