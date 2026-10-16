import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/**
 * Button. Same contract as workspace-app's shadcn Button: variant × size,
 * focus ring from the token layer, and `render` for polymorphic use
 * (a Button that is really a `<Link>`).
 */

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-sm whitespace-nowrap font-label normal-case transition-[background-color,color,box-shadow] disabled:pointer-events-none disabled:opacity-50 focus-ring",
  {
    variants: {
      variant: {
        default: "bg-flame-vivid text-on-flame hover:brightness-95",
        secondary: "bg-surface-2 text-ink-strong ring-1 ring-rule hover:bg-paper-200/60",
        outline: "bg-transparent text-ink-strong ring-1 ring-rule-strong hover:bg-surface-2",
        ghost: "bg-transparent text-ink-muted hover:bg-surface-2 hover:text-ink-strong",
        danger: "bg-status-danger text-paper-25 hover:brightness-95",
        quiet: "bg-transparent text-ink-faint hover:text-ink-strong",
      },
      size: {
        sm: "h-7 px-2.5",
        md: "h-8 px-3",
        lg: "h-9 px-4",
        icon: "size-8",
        "icon-sm": "size-7",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export interface ButtonProps
  extends React.ComponentProps<"button">,
    VariantProps<typeof buttonVariants> {
  /** Render as a different element while keeping the button styling. */
  render?: React.ReactElement<{ className?: string }>;
}

export function Button({
  className,
  variant,
  size,
  render,
  ...props
}: ButtonProps) {
  const classes = cn(buttonVariants({ variant, size }), className);
  if (render) {
    return React.cloneElement(render, {
      ...props,
      className: cn(classes, (render.props as { className?: string }).className),
    });
  }
  return <button className={classes} {...props} />;
}

export { buttonVariants };
