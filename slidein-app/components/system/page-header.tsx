import { cn } from "@/lib/utils";

/**
 * PageHeader: the standard top-of-page header. An ops console header is a
 * coordinate, not a billboard.
 *
 *   eyebrow  mono label above the title (the workflow stage coordinate)
 *   title    the page name
 *   meta     right-aligned metadata (counts, config version, a chip)
 *   actions  right-aligned controls
 */
export function PageHeader({
  eyebrow,
  title,
  meta,
  actions,
  className,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  meta?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header
      data-slot="page-header"
      className={cn(
        "flex flex-col gap-2 pb-4 sm:flex-row sm:items-end sm:justify-between sm:gap-6",
        className,
      )}
    >
      <div className="flex min-w-0 flex-col gap-1">
        {eyebrow && <span className="font-label text-ink-faint">{eyebrow}</span>}
        <h1 className="font-display-soft text-lg text-ink-strong">{title}</h1>
      </div>
      <div className="flex flex-wrap items-center gap-3 sm:justify-end">
        {meta && <span className="font-label text-ink-faint">{meta}</span>}
        {actions}
      </div>
    </header>
  );
}
