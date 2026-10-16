import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/**
 * Badge. Tinted pills in sentence-case sans — never solid blocks, never mono.
 */
const badgeVariants = cva(
  "inline-flex h-[26px] items-center gap-1.5 rounded-pill px-2.5 font-sans text-xs font-medium whitespace-nowrap",
  {
    variants: {
      variant: {
        solid: "bg-button-primary text-on-button-primary",
        outline: "border border-rule-strong bg-surface text-ink-muted",
        quiet: "bg-transparent text-ink-faint",
      },
    },
    defaultVariants: { variant: "outline" },
  },
);

export function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { badgeVariants };
