import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/**
 * Button. Same contract as before: variant × size, focus ring from the
 * token layer, and `render` for polymorphic use (a Button that is really
 * a `<Link>`). Visuals follow the marketing pill language: fully rounded,
 * confident, with depth.
 *
 *   dot   an 8px accent dot before the label — ONLY on the single most
 *         important button in a view.
 */

const buttonVariants = cva(
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-pill whitespace-nowrap font-sans text-sm font-medium transition-[transform,background-color,color,box-shadow,border-color] duration-[120ms] ease-out hover:-translate-y-px active:translate-y-0 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-40 disabled:shadow-none disabled:transform-none focus-ring",
  {
    variants: {
      variant: {
        default: "bg-button-primary text-on-button-primary shadow-button hover:shadow-button",
        secondary:
          "border border-rule-strong bg-surface text-ink-strong hover:shadow-raised",
        outline:
          "border border-rule-strong bg-surface text-ink-strong hover:shadow-raised",
        ghost: "bg-transparent text-ink-muted hover:bg-hover-tint hover:text-ink-strong",
        danger:
          "border border-transparent bg-surface text-status-danger hover:bg-status-danger-bg",
        quiet: "bg-transparent text-ink-faint hover:text-ink-strong",
      },
      size: {
        sm: "h-8 px-4 text-[13px]",
        md: "h-10 px-5 text-sm",
        lg: "h-11 px-6 text-sm",
        icon: "size-9",
        "icon-sm": "size-8",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export interface ButtonProps
  extends React.ComponentProps<"button">,
    VariantProps<typeof buttonVariants> {
  /** Render as a different element while keeping the button styling. */
  render?: React.ReactElement<{ className?: string; children?: React.ReactNode }>;
  /** 8px accent dot before the label: the view's single primary action only. */
  dot?: boolean;
  /** Replaces the dot with a 14px spinner without changing width. */
  loading?: boolean;
}

export function Button({
  className,
  variant,
  size,
  render,
  dot = false,
  loading = false,
  children,
  ...props
}: ButtonProps) {
  const classes = cn(buttonVariants({ variant, size }), className);
  const content = (
    <>
      {(dot || loading) && (
        <span aria-hidden className="flex w-[14px] shrink-0 items-center justify-center">
          {loading ? (
            <span className="size-[14px] animate-spin rounded-full border-2 border-current border-t-transparent opacity-60" />
          ) : (
            <span className="size-2 rounded-full bg-flame-vivid" />
          )}
        </span>
      )}
      {children}
    </>
  );
  if (render) {
    return React.cloneElement(render, {
      ...props,
      className: cn(classes, (render.props as { className?: string }).className),
      children: content,
    });
  }
  return (
    <button className={classes} {...props}>
      {content}
    </button>
  );
}

export { buttonVariants };
