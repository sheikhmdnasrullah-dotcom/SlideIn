import { cn } from "@/lib/utils";

/**
 * PageHeader: the standard top-of-page header. An ops console header is a
 * coordinate, not a billboard: 28px title, quiet meta, right actions.
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
        "flex flex-col gap-2 pb-8 sm:flex-row sm:items-end sm:justify-between sm:gap-6",
        className,
      )}
    >
      <div className="flex min-w-0 flex-col gap-1">
        {eyebrow && <span className="font-label text-ink-muted">{eyebrow}</span>}
        <h1 className="font-display text-[28px] leading-[34px] text-ink-strong">{title}</h1>
      </div>
      <div className="flex flex-wrap items-center gap-3 sm:justify-end">
        {meta && <span className="font-label text-ink-muted">{meta}</span>}
        {actions}
      </div>
    </header>
  );
}
