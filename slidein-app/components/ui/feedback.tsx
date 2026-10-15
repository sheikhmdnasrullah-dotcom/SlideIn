import * as React from "react";

import { cn } from "@/lib/utils";

/** Skeleton placeholder. Never a spinner in place of content. */
export function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("animate-pulse rounded-xs bg-surface-2", className)}
      aria-hidden
      {...props}
    />
  );
}

/** A centred busy row for a full section fetch. */
export function Spinner({ className, label }: { className?: string; label?: string }) {
  return (
    <div className={cn("flex items-center gap-2 text-ink-faint", className)}>
      <span
        className="size-3 animate-spin rounded-full border border-rule-strong border-t-flame-vivid"
        aria-hidden
      />
      <span className="font-label">{label ?? "Loading"}</span>
    </div>
  );
}

/** Modal surface. Escape and backdrop click close it. */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        className="absolute inset-0 bg-scrim"
        aria-label="Close"
        onClick={onClose}
        type="button"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative z-10 w-full max-w-lg rounded-md bg-surface p-4 shadow-float ring-1 ring-rule-strong"
      >
        <header className="flex flex-col gap-1 pb-3">
          <h2 className="font-display-soft text-base text-ink-strong">{title}</h2>
          {description && <p className="text-2xs text-ink-faint">{description}</p>}
        </header>
        <div className="max-h-[65vh] overflow-y-auto">{children}</div>
        {footer && (
          <footer className="flex items-center justify-end gap-2 pt-4">{footer}</footer>
        )}
      </div>
    </div>
  );
}
