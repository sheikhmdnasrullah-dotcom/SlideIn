"use client";

import * as React from "react";

/** Minimal tooltip context — the workspace does not need the full Radix tree. */
const TooltipContext = React.createContext<{ show: (node: React.ReactNode) => void } | null>(
  null,
);

export function TooltipProvider({ children }: { children: React.ReactNode }) {
  const [node, setNode] = React.useState<React.ReactNode>(null);
  const value = React.useMemo(() => ({ show: setNode }), []);

  return (
    <TooltipContext.Provider value={value}>
      {children}
      {node && (
        <div
          role="tooltip"
          className="pointer-events-none fixed bottom-4 left-1/2 z-[60] -translate-x-1/2 rounded-xs bg-ink px-2 py-1 text-2xs text-paper-25 shadow-float"
        >
          {node}
        </div>
      )}
    </TooltipContext.Provider>
  );
}

/** A trigger that shows a tokenized tooltip on hover and focus. */
export function WithTooltip({
  label,
  children,
}: {
  label: React.ReactNode;
  children: React.ReactElement<{ onMouseEnter?: unknown; onFocus?: unknown; onMouseLeave?: unknown; onBlur?: unknown }>;
}) {
  const context = React.useContext(TooltipContext);
  return React.cloneElement(children, {
    onMouseEnter: () => context?.show(label),
    onMouseLeave: () => context?.show(null),
    onFocus: () => context?.show(label),
    onBlur: () => context?.show(null),
  });
}
