import * as React from "react";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "h-8 w-full rounded-sm bg-surface px-2.5 text-[0.8125rem] text-ink-strong",
        "ring-1 ring-rule-strong placeholder:text-ink-faint",
        "transition-colors focus-visible:ring-2 focus-visible:ring-flame-ring focus-ring",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "w-full rounded-sm bg-surface px-2.5 py-2 text-[0.8125rem] leading-relaxed text-ink-strong",
        "ring-1 ring-rule-strong placeholder:text-ink-faint",
        "transition-colors focus-visible:ring-2 focus-visible:ring-flame-ring focus-ring",
        className,
      )}
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
    <label className={cn("flex flex-col gap-1", className)}>
      <span className="font-label text-ink-faint">{label}</span>
      {children}
      {hint && <span className="text-2xs text-ink-faint">{hint}</span>}
    </label>
  );
}

export function Select({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      className={cn(
        "h-8 rounded-sm bg-surface px-2 pr-7 text-[0.8125rem] text-ink-strong",
        "ring-1 ring-rule-strong focus-visible:ring-2 focus-visible:ring-flame-ring focus-ring",
        className,
      )}
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
    <label className={cn("flex items-center gap-2 text-[0.8125rem] text-ink-muted", className)}>
      <input
        type="checkbox"
        className="size-3.5 rounded-xs border-rule-strong accent-[var(--accent-vivid)]"
        {...props}
      />
      {label}
    </label>
  );
}
