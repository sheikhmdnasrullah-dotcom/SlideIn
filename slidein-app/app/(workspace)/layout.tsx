import type * as React from "react";

import type { Metadata } from "next";

import { MobileNav } from "@/components/workspace/mobile-nav";
import { WorkflowSidebar } from "@/components/workspace/sidebar";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import type { Branding } from "@/lib/api/types";
import { SECTIONS } from "@/lib/workflow/metadata";
import { themeStyle } from "@/lib/workflow/tenant";

export async function generateMetadata(): Promise<Metadata> {
  try {
    const { branding } = await operations.branding(WORKSPACE_ID);
    const name = branding.business_name.trim();
    if (name) return { title: `${name} — workspace` };
  } catch {
    // Fall through to the default title below.
  }
  return { title: "Slidein — client workspace" };
}

/**
 * Persistent workspace shell. The sidebar stays mounted across section
 * switches — only the page body swaps — so navigating the workflow never
 * loses the section context.
 *
 * Tenant brand + modules load here so the whole workspace (nav, theme)
 * reflects the active tenant. Everything is best-effort: without the API
 * the default theme and full nav render, and every panel says why data is
 * missing.
 */
export default async function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  let attentionCounts: Record<string, number> | undefined;
  let branding: Branding | null = null;
  let enabledModules: string[] | null = null;
  let sectionLabels: Record<string, string> | null = null;
  try {
    const [overview, brand, modules, template] = await Promise.all([
      operations.overview(WORKSPACE_ID, 5),
      operations.branding(WORKSPACE_ID),
      operations.modules(WORKSPACE_ID),
      operations.tenantTemplate(WORKSPACE_ID),
    ]);
    const counts: Record<string, number> = {};
    for (const item of overview.attention) counts[sectionIdForStage(item.stage)] =
      (counts[sectionIdForStage(item.stage)] ?? 0) + 1;
    attentionCounts = counts;
    branding = brand.branding;
    enabledModules = modules.enabled;
    sectionLabels = template.terminology.sections ?? null;
  } catch {
    // The workspace is usable without the API; every panel says why.
  }

  const sidebarProps = {
    attentionCounts,
    workspaceId: WORKSPACE_ID,
    brandName: branding?.business_name || undefined,
    logoUrl: branding?.logo_url || undefined,
    enabledModules,
    sectionLabels,
  };
  return (
    <div className="flex min-h-0 w-full flex-col md:flex-row" style={themeStyle(branding)}>
      <MobileNav {...sidebarProps} />
      <div className="hidden min-h-0 md:flex">
        <WorkflowSidebar {...sidebarProps} />
      </div>
      <main className="min-h-0 min-w-0 grow overflow-y-auto">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-4 sm:px-6 sm:py-6">
          {children}
        </div>
      </main>
    </div>
  );
}

function sectionIdForStage(stage: string): string {
  return SECTIONS.find((section) => section.stage === stage)?.id ?? "overview";
}
