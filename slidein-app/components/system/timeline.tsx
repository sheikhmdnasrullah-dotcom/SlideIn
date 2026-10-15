import { cn } from "@/lib/utils";
import { StatusBadge } from "./status-badge";

/**
 * Timeline: the ordered history of a record. Used for a prospect's state
 * trail, a draft's versions, a conversation, and the stage runs behind a
 * subject. Reads the same persisted data in every case.
 */
export interface TimelineItem {
  id: string;
  title: React.ReactNode;
  meta?: React.ReactNode;
  description?: React.ReactNode;
  tone?: "flame" | "live" | "info" | "warn" | "danger" | "neutral";
  when?: string;
  href?: string;
}

const TONE_DOT: Record<string, string> = {
  flame: "bg-flame-vivid",
  live: "bg-status-live",
  info: "bg-status-info",
  warn: "bg-status-warn",
  danger: "bg-status-danger",
  neutral: "bg-bone-400",
};

export function Timeline({
  items,
  className,
  emptyLabel = "Nothing recorded yet.",
}: {
  items: TimelineItem[];
  className?: string;
  emptyLabel?: string;
}) {
  if (items.length === 0) {
    return <p className="px-4 py-3 text-2xs text-ink-faint">{emptyLabel}</p>;
  }
  return (
    <ol className={cn("flex flex-col", className)}>
      {items.map((item, index) => (
        <li key={item.id} className="relative flex gap-3 px-4 py-2.5">
          {index < items.length - 1 && (
            <span className="absolute left-[19px] top-6 bottom-0 w-px bg-rule" aria-hidden />
          )}
          <span className="relative mt-1 flex size-2.5 shrink-0 items-center justify-center">
            <span className={cn("size-2 rounded-full", TONE_DOT[item.tone ?? "neutral"])} />
          </span>
          <div className="flex min-w-0 flex-col gap-0.5">
            <div className="flex flex-wrap items-baseline gap-2">
              {typeof item.title === "string" ? (
                <span className="font-display-soft text-[0.8125rem] text-ink-strong">
                  {item.title}
                </span>
              ) : (
                item.title
              )}
              {item.when && (
                <span className="font-label text-ink-faint">{item.when}</span>
              )}
            </div>
            {item.description && (
              <p className="max-w-prose text-2xs leading-relaxed text-ink-muted">
                {item.description}
              </p>
            )}
            {item.meta && <div className="flex flex-wrap items-center gap-2 pt-0.5">{item.meta}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}

/** Compact stage-progress rail: where a prospect is, and what is next. */
export function StageRail({
  stages,
  activeStage,
  className,
}: {
  stages: { stage: string; label: string }[];
  activeStage: string;
  className?: string;
}) {
  const activeIndex = stages.findIndex((item) => item.stage === activeStage);
  return (
    <ol className={cn("flex items-center gap-1", className)}>
      {stages.map((item, index) => {
        const done = activeIndex >= 0 && index < activeIndex;
        const current = index === activeIndex;
        return (
          <li key={item.stage} className="flex items-center gap-1">
            <span
              className={cn(
                "h-1 rounded-pill transition-colors",
                current ? "w-6 bg-flame-vivid" : done ? "w-3 bg-status-live" : "w-3 bg-rule-strong",
              )}
              title={item.label}
            />
            <span className="sr-only">{item.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** A labelled value with a status tone — used in handoff cards. */
export function StatusLine({
  label,
  tone,
  children,
}: {
  label: string;
  tone?: "flame" | "live" | "info" | "warn" | "danger" | "neutral";
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {tone && <StatusBadge tone={tone} label={label} />}
      {!tone && <span className="font-label text-ink-faint">{label}</span>}
      <span className="text-2xs text-ink-muted">{children}</span>
    </div>
  );
}
