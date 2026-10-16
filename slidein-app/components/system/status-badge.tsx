import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { StatusTone } from "@/lib/workflow/metadata";

/**
 * StatusBadge: the one tokenized status indicator. Tinted pills in
 * sentence-case sans with a 6px semantic dot — never solid blocks,
 * never mono. Tones map to the theme-tokenized --status-* colors.
 */
const TONE_STYLE: Record<StatusTone, { bg: string; color: string; dot: string }> = {
  live: {
    bg: "var(--status-live-bg)",
    color: "var(--status-live)",
    dot: "var(--status-live)",
  },
  info: {
    bg: "var(--status-info-bg)",
    color: "var(--status-info)",
    dot: "var(--status-info)",
  },
  warn: {
    bg: "var(--status-warn-bg)",
    color: "var(--status-warn)",
    dot: "var(--status-warn)",
  },
  danger: {
    bg: "var(--status-danger-bg)",
    color: "var(--status-danger)",
    dot: "var(--status-danger)",
  },
  neutral: {
    bg: "var(--status-neutral-bg)",
    color: "var(--status-neutral)",
    dot: "var(--status-neutral)",
  },
  flame: {
    bg: "var(--accent-wash)",
    color: "var(--text-accent)",
    dot: "var(--accent-vivid)",
  },
};

export function StatusBadge({
  tone,
  label,
  dot = true,
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
      className={cn(
        "border-transparent",
        dot &&
          "before:content-[''] before:size-1.5 before:shrink-0 before:rounded-full before:bg-[var(--badge-dot)]",
        dot && tone === "live" && "before:animate-pulse",
        className,
      )}
      style={
        {
          backgroundColor: style.bg,
          color: style.color,
          "--badge-dot": style.dot,
        } as React.CSSProperties
      }
    >
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
    <span className="inline-flex items-baseline gap-1" data-metric>
      <span className="font-value text-base text-ink-strong">{count}</span>
      <span className="text-xs text-ink-muted">{label}</span>
      <StatusBadge tone={tone} label="" className="sr-only" />
    </span>
  );
}
