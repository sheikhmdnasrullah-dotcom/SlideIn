import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { StatusTone } from "@/lib/workflow/metadata";

/**
 * StatusBadge: the one tokenized status indicator. Tones map to the
 * theme-tokenized --status-* colors, so the same badge reads correctly on
 * day and night without a `dark:` variant.
 */
const TONE_STYLE: Record<StatusTone, { border: string; bg: string; color: string }> = {
  live: {
    border: "color-mix(in oklch, var(--status-live) 30%, transparent)",
    bg: "color-mix(in oklch, var(--status-live) 10%, transparent)",
    color: "var(--status-live)",
  },
  info: {
    border: "color-mix(in oklch, var(--status-info) 30%, transparent)",
    bg: "color-mix(in oklch, var(--status-info) 10%, transparent)",
    color: "var(--status-info)",
  },
  warn: {
    border: "color-mix(in oklch, var(--status-warn) 30%, transparent)",
    bg: "color-mix(in oklch, var(--status-warn) 10%, transparent)",
    color: "var(--status-warn)",
  },
  danger: {
    border: "color-mix(in oklch, var(--status-danger) 30%, transparent)",
    bg: "color-mix(in oklch, var(--status-danger) 10%, transparent)",
    color: "var(--status-danger)",
  },
  neutral: {
    border: "var(--rule-strong)",
    bg: "var(--surface-2)",
    color: "var(--text-muted)",
  },
  flame: {
    border: "var(--accent-ring)",
    bg: "var(--accent-wash)",
    color: "var(--text-accent)",
  },
};

export function StatusBadge({
  tone,
  label,
  dot = false,
  title,
  className,
}: {
  tone: StatusTone;
  label?: React.ReactNode;
  dot?: boolean;
  title?: string;
  className?: string;
}) {
  const style = TONE_STYLE[tone];
  return (
    <Badge
      variant="outline"
      title={title}
      className={cn("gap-1 font-label normal-case", className)}
      style={{ borderColor: style.border, backgroundColor: style.bg, color: style.color }}
    >
      {dot && (
        <span
          className={cn(
            "size-1.5 rounded-full bg-current",
            tone === "live" && "animate-pulse",
          )}
          aria-hidden
        />
      )}
      {label ?? tone}
    </Badge>
  );
}

/** Small count + label pair used in section headers and handoff cards. */
export function CountChip({
  count,
  label,
  tone = "neutral",
}: {
  count: number;
  label: string;
  tone?: StatusTone;
}) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="font-value text-base text-ink-strong">{count}</span>
      <span className="text-2xs text-ink-faint">{label}</span>
      <StatusBadge tone={tone} label="" className="sr-only" />
    </span>
  );
}
