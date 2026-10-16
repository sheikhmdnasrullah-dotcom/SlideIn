"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * StaggerTbody: a tbody whose rows fade up with a 30ms stagger on first
 * paint only. The .is-live guard is added once after mount, so filtering,
 * sorting, typing or polling never replays the entrance.
 */
export function StaggerTbody({ className, ...props }: React.ComponentProps<"tbody">) {
  const ref = React.useRef<HTMLTableSectionElement>(null);
  React.useEffect(() => {
    ref.current?.classList.add("is-live");
  }, []);
  return (
    <tbody
      ref={ref}
      data-slot="table-body"
      className={cn("stagger-group divide-y divide-rule-soft", className)}
      {...props}
    />
  );
}
