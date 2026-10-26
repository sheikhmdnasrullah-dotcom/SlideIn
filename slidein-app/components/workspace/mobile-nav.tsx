"use client";

import * as React from "react";
import { Menu, X } from "lucide-react";

import { WorkflowSidebar } from "./sidebar";
import { GlossTile } from "@/components/system/gloss-tile";
import { brandInitials, safeLogoUrl } from "@/lib/workflow/tenant";
import { cn } from "@/lib/utils";

/**
 * MobileNav: the workspace chrome below the lg breakpoint. The desktop
 * sidebar is a fixed 264px rail; here it becomes a left drawer opened
 * from a round menu button in the top bar. No animation (conditional
 * render), so there is no motion to gate on prefers-reduced-motion.
 */
export function MobileNav({
  attentionCounts,
  workspaceId,
  brandName,
  logoUrl,
  enabledModules,
  sectionLabels,
  user,
  dashboardHref,
}: {
  attentionCounts?: Record<string, number>;
  workspaceId: string;
  brandName?: string;
  logoUrl?: string | null;
  enabledModules?: string[] | null;
  sectionLabels?: Record<string, string> | null;
  user?: { name: string; email: string; role: string } | null;
  dashboardHref?: string;
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
    <div className="lg:hidden">
      <div className="flex h-16 items-center gap-3 border-b border-rule bg-sidebar-fill px-5">
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open navigation"
          aria-expanded={open}
          className="flex size-10 shrink-0 items-center justify-center rounded-full text-ink-muted hover:bg-hover-tint hover:text-ink-strong focus-ring"
        >
          <Menu className="size-[18px]" aria-hidden />
        </button>
        {logo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={logo} alt="" className="size-9 rounded-[11px] object-contain" />
        ) : (
          <GlossTile size={36} float={false}>
            <span className="font-sans text-[13px] font-semibold text-ink-strong">
              {brandInitials(displayName)}
            </span>
          </GlossTile>
        )}
        <span className="truncate font-sans text-[15px] font-semibold text-ink-strong">{displayName}</span>
      </div>

      {open && (
        <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Workspace navigation">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
            className="absolute inset-0 cursor-default bg-backdrop-soft"
          />
          <div className="absolute inset-y-0 left-0 flex w-[17rem] max-w-[85vw] flex-col bg-sidebar-fill shadow-float">
            <div className="flex justify-end p-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close navigation"
                className="flex size-10 items-center justify-center rounded-full text-ink-muted hover:bg-hover-tint hover:text-ink-strong focus-ring"
              >
                <X className="size-[18px]" aria-hidden />
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
                user={user}
                dashboardHref={dashboardHref}
                className={cn("h-full w-full border-r-0")}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
