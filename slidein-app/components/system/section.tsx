import { cn } from "@/lib/utils";

/**
 * Section: the top-level grouping inside a page. One Section per workflow
 * stage, so the page reads in the same order the workflow runs.
 */
export type SectionTone = "flat" | "raised" | "well";

const TONE_CLASS: Record<SectionTone, string> = {
  flat: "",
  raised: "overflow-hidden rounded-lg border border-rule bg-surface shadow-raised",
  well: "overflow-hidden rounded-md border border-rule bg-surface-2",
};

export function Section({
  eyebrow,
  title,
  description,
  meta,
  actions,
  tone = "flat",
  divided = false,
  className,
  bodyClassName,
  children,
}: {
  eyebrow?: React.ReactNode;
  title?: React.ReactNode;
  description?: React.ReactNode;
  meta?: React.ReactNode;
  actions?: React.ReactNode;
  tone?: SectionTone;
  divided?: boolean;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      data-slot="section"
      className={cn("flex flex-col", TONE_CLASS[tone], className)}
    >
      {(title || eyebrow || actions || meta) && (
        <header
          className={cn(
            "flex flex-col gap-2 px-6 pt-6 pb-4 sm:flex-row sm:items-end sm:justify-between sm:gap-6",
          )}
        >
          <div className="flex min-w-0 flex-col gap-1">
            {eyebrow && <span className="font-label text-ink-muted">{eyebrow}</span>}
            {title && (
              <h2 className="font-display-soft text-[15px] leading-[22px] text-ink-strong">
                {title}
              </h2>
            )}
            {description && (
              <p className="max-w-2xl text-[13px] leading-relaxed text-ink-muted">
                {description}
              </p>
            )}
          </div>
          {(meta || actions) && (
            <div className="flex flex-wrap items-center gap-3 sm:justify-end">
              {meta && <span className="font-label text-ink-muted">{meta}</span>}
              {actions}
            </div>
          )}
        </header>
      )}
      <div className={cn("grow", divided && "border-t border-rule", bodyClassName ?? "px-0")}>{children}</div>
    </section>
  );
}

/** SectionRule: a hairline with a label, used between subsections. */
export function SectionRule({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-1">
      <span className="h-px grow bg-rule" />
      {label && <span className="font-label text-ink-muted">{label}</span>}
      <span className="h-px grow bg-rule" />
    </div>
  );
}
