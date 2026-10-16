import { cn } from "@/lib/utils";

/** ISO timestamp -> compact local string. */
export function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31536000],
    ["month", 2592000],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return formatter.format(Math.round(seconds / size), unit);
  }
  return formatter.format(seconds, "second");
}

export function formatPercent(value: number | undefined, digits = 0): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

/** Middle-dot separated inline list. */
export function Dots({ items }: { items: (string | number | null | undefined)[] }) {
  const visible = items.filter((item) => item !== null && item !== undefined && item !== "");
  if (visible.length === 0) return <span className="text-ink-faint">—</span>;
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {visible.map((item, index) => (
        <span key={index} className="flex items-center gap-1.5">
          {index > 0 && <span className="text-ink-faint" aria-hidden>·</span>}
          <span>{item}</span>
        </span>
      ))}
    </span>
  );
}

/** A link-ish text button used inside dense rows. */
export function InlineLink({
  href,
  children,
  className,
}: {
  href: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <a
      href={href}
      className={cn(
        "rounded-xs text-ink-strong underline decoration-rule-strong underline-offset-2",
        "transition-colors hover:decoration-flame-vivid focus-ring",
        className,
      )}
    >
      {children}
    </a>
  );
}

/** Key/value row used in detail side panels. */
export function DefRow({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-baseline justify-between gap-4 py-1", className)}>
      <span className="font-label text-ink-muted">{label}</span>
      <span className="text-right text-sm text-ink-muted">{children}</span>
    </div>
  );
}

/** Hairline-separated definition list. */
export function DefList({ children, className }: { children: React.ReactNode; className?: string }) {
  return <dl className={cn("divide-y divide-rule", className)}>{children}</dl>;
}
