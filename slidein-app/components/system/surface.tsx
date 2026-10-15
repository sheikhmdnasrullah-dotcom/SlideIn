import { cn } from "@/lib/utils";

/**
 * Surface: the non-card container. A sectioned container holds a list
 * divided by hairlines, a table, or a metric row — without boxing each
 * child in its own rounded rectangle.
 *
 *   flat    inherits the section tone; no border
 *   inset   a well: surface-2 with a hairline rule. Grouping without boxes.
 *   raised  surface with a stronger rule. One panel, not a rectangle per datum.
 */
export type SurfaceVariant = "flat" | "inset" | "raised";

const VARIANT_CLASS: Record<SurfaceVariant, string> = {
  flat: "bg-transparent",
  inset: "bg-surface-2 ring-1 ring-rule rounded-md",
  raised: "bg-surface ring-1 ring-rule-strong rounded-md shadow-raised",
};

export function Surface({
  variant = "flat",
  className,
  children,
  ...props
}: React.ComponentProps<"div"> & { variant?: SurfaceVariant }) {
  return (
    <div
      data-slot="surface"
      data-variant={variant}
      className={cn("px-4 py-3", VARIANT_CLASS[variant], className)}
      {...props}
    >
      {children}
    </div>
  );
}

/** Divider: a hairline between items inside a Surface. */
export function Divider({ className }: { className?: string }) {
  return <div className={cn("h-px w-full bg-rule", className)} />;
}
