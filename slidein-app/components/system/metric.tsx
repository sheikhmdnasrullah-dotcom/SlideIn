import { cn } from "@/lib/utils";

/**
 * Metric: one number and its label. Tabular numerals, no sparkline theatre.
 */
export function Metric({
  label,
  value,
  hint,
  tone,
  className,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  tone?: "flame" | "live" | "warn" | "danger";
  className?: string;
}) {
  const toneClass =
    tone === "flame"
      ? "text-flame"
      : tone === "live"
        ? "text-status-live"
        : tone === "warn"
          ? "text-status-warn"
          : tone === "danger"
            ? "text-status-danger"
            : "text-ink-strong";
  return (
    <div className={cn("flex flex-col gap-0.5", className)}>
      <span className="font-label text-ink-muted">{label}</span>
      <span className={cn("font-value text-xl leading-none", toneClass)} data-metric>{value}</span>
      {hint && <span className="text-xs text-ink-muted">{hint}</span>}
    </div>
  );
}

/** MetricRow: a row of metrics divided by hairlines — not boxes. */
export function MetricRow({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-2 divide-x divide-rule sm:grid-cols-3 lg:grid-cols-4",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** MetricCell: one slot inside a MetricRow. */
export function MetricCell({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("px-6 py-4 first:pl-0", className)}>{children}</div>;
}
