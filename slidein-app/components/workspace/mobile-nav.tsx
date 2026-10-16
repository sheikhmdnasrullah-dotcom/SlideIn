"use client";

import * as React from "react";
import { Menu, X } from "lucide-react";

import { WorkflowSidebar } from "./sidebar";
import { brandInitials, safeLogoUrl } from "@/lib/workflow/tenant";
import { cn } from "@/lib/utils";

/**
 * MobileNav: the workspace chrome below the md breakpoint. The desktop
 * sidebar is a fixed 15rem rail; here it becomes a slide-over opened from a
 * compact top bar. No animation (conditional render), so there is no motion
 * to gate on prefers-reduced-motion.
 */
export function MobileNav({
  attentionCounts,
  workspaceId,
  brandName,
  logoUrl,
  enabledModules,
  sectionLabels,
}: {
  attentionCounts?: Record<string, number>;
  workspaceId: string;
  brandName?: string;
  logoUrl?: string | null;
  enabledModules?: string[] | null;
  sectionLabels?: Record<string, string> | null;
}) {
  const [open, setOpen] = React.useState(false);
  const displayName = brandName?.trim() || "Slidein";
  const logo = safeLogoUrl(logoUrl);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open ]);

  return (
    <div className="md:hidden">
      <div className="flex h-12 items-center gap-2 border-b border-rule bg-surface px-3">
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open navigation"
          aria-expanded={open}
          className="flex size-8 items-center justify-center rounded-sm text-ink-muted hover:bg-surface-2 hover:text-ink-strong focus-ring"
        >
          <Menu className="size-4" aria-hidden />
        </button>
        {logo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={logo} alt="" className="size-6 rounded-xs object-contain" />
        ) : (
          <span className="flex size-6 items-center justify-center rounded-xs bg-flame-vivid font-mono text-2xs font-semibold text-on-flame">
            {brandInitials(displayName)}
          </span>
        )}
        <span className="truncate font-display-soft text-sm text-ink-strong">{displayName}</span>
      </div>

      {open && (
        <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Workspace navigation">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
            className="absolute inset-0 cursor-default bg-scrim"
          />
          <div className="absolute inset-y-0 left-0 flex w-[17rem] max-w-[85vw] flex-col bg-surface shadow-float">
            <div className="flex justify-end border-b border-rule p-1">
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close navigation"
                className="flex size-8 items-center justify-center rounded-sm text-ink-muted hover:bg-surface-2 hover:text-ink-strong focus-ring"
              >
                <X className="size-4" aria-hidden />
              </button>
            </div>
            <div
              className="min-h-0 grow"
              onClick={(event) => {
                if ((event.target as HTMLElement).closest("a")) setOpen(false);
              }}
            >
              <WorkflowSidebar
                attentionCounts={attentionCounts}
                workspaceId={workspaceId}
                brandName={brandName}
                logoUrl={logoUrl}
                enabledModules={enabledModules}
                sectionLabels={sectionLabels}
                className={cn("h-full w-full border-r-0")}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
