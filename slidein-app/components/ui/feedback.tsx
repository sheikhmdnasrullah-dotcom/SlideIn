import * as React from "react";

import { cn } from "@/lib/utils";

/** Skeleton placeholder: pill bars with a slow shimmer. Never a spinner. */
export function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("skeleton-shimmer rounded-pill bg-skeleton", className)}
      aria-hidden
      {...props}
    />
  );
}

/** A centred busy row for a full section fetch. */
export function Spinner({ className, label }: { className?: string; label?: string }) {
  return (
    <div className={cn("flex items-center gap-2 text-ink-muted", className)}>
      <span
        className="size-3.5 animate-spin rounded-full border-2 border-rule-strong border-t-flame-vivid"
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
    <div className="dialog-enter fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        className="absolute inset-0 cursor-default bg-scrim"
        aria-label="Close"
        onClick={onClose}
        type="button"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="dialog-panel relative z-10 w-full max-w-lg rounded-xl border border-rule bg-surface p-8 shadow-float"
      >
        <header className="flex flex-col gap-1 pb-4">
          <h2 className="font-display-soft text-[15px] leading-[22px] text-ink-strong">{title}</h2>
          {description && <p className="text-[13px] text-ink-muted">{description}</p>}
        </header>
        <div className="max-h-[65vh] overflow-y-auto">{children}</div>
        {footer && (
          <footer className="flex items-center justify-end gap-2 pt-6">{footer}</footer>
        )}
      </div>
    </div>
  );
}
