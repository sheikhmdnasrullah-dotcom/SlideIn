import { cn } from "@/lib/utils";

/**
 * Section: the top-level grouping inside a page. One Section per workflow
 * stage, so the page reads in the same order the workflow runs.
 */
export type SectionTone = "flat" | "raised" | "well";

const TONE_CLASS: Record<SectionTone, string> = {
  flat: "",
  raised: "rounded-md bg-surface ring-1 ring-rule",
  well: "rounded-md bg-surface-2 ring-1 ring-rule",
};

export function Section({
  eyebrow,
  title,
  description,
  meta,
  actions,
  tone = "flat",
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
            "flex flex-col gap-2 px-4 pt-4 pb-3 sm:flex-row sm:items-end sm:justify-between sm:gap-6",
            tone !== "flat" && "px-4",
          )}
        >
          <div className="flex min-w-0 flex-col gap-1">
            {eyebrow && <span className="font-label text-ink-faint">{eyebrow}</span>}
            {title && <h2 className="font-display-soft text-base text-ink-strong">{title}</h2>}
            {description && (
              <p className="max-w-2xl text-2xs leading-relaxed text-ink-faint">{description}</p>
            )}
          </div>
          {(meta || actions) && (
            <div className="flex flex-wrap items-center gap-3 sm:justify-end">
              {meta && <span className="font-label text-ink-faint">{meta}</span>}
              {actions}
            </div>
          )}
        </header>
      )}
      <div className={cn("grow", bodyClassName ?? "px-0")}>{children}</div>
    </section>
  );
}

/** SectionRule: a hairline with a label, used between subsections. */
export function SectionRule({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-1">
      <span className="h-px grow bg-rule" />
      {label && <span className="font-label text-ink-faint">{label}</span>}
      <span className="h-px grow bg-rule" />
    </div>
  );
}
