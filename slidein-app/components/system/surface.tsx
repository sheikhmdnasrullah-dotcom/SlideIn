import { cn } from "@/lib/utils";

/**
 * Surface: the non-card container. A sectioned container holds a list
 * divided by hairlines, a table, or a metric row.
 *
 *   flat    inherits the section tone; no border
 *   inset   a nested panel: #FAFAFA with a hairline, never a second shadow
 *   raised  a card: white, hairline, 20px radius, soft shadow, 24px padding
 */
export type SurfaceVariant = "flat" | "inset" | "raised";

const VARIANT_CLASS: Record<SurfaceVariant, string> = {
  flat: "bg-transparent",
  inset: "rounded-md border border-rule bg-surface-2 p-4",
  raised: "rounded-lg border border-rule bg-surface p-6 shadow-raised",
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
