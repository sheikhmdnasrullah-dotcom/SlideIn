import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-xs px-1.5 py-0.5 font-label normal-case whitespace-nowrap",
  {
    variants: {
      variant: {
        solid: "bg-flame-vivid text-on-flame",
        outline: "ring-1 ring-rule-strong bg-surface-2 text-ink-muted",
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
