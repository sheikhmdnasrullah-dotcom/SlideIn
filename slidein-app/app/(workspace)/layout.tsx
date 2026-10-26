import type * as React from "react";
import { redirect } from "next/navigation";

import type { Metadata } from "next";

import { AutoRefresh } from "@/components/workspace/auto-refresh";
import { MobileNav } from "@/components/workspace/mobile-nav";
import { WorkflowSidebar } from "@/components/workspace/sidebar";
import { WorkspaceMismatch } from "@/components/workspace/workspace-mismatch";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import { dashboardUrl, requireConsoleSession } from "@/lib/auth/session";
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
  const session = await requireConsoleSession();
  if (!session) {
    // requireConsoleSession redirects; this keeps the type honest.
    redirect("/login");
  }
  if (session.tenant_id !== WORKSPACE_ID) {
    return (
      <WorkspaceMismatch sessionTenant={session.tenant_id} workspaceId={WORKSPACE_ID} />
    );
  }

  let attentionCounts: Record<string, number> | undefined;
  let branding: Branding | null = null;
  let enabledModules: string[] | null = null;
  let sectionLabels: Record<string, string> | null = null;
  let moduleOrder: string[] | null = null;
  try {
    const [overview, brand, modules, template, workspace] = await Promise.all([
      operations.overview(WORKSPACE_ID, 5),
      operations.branding(WORKSPACE_ID),
      operations.modules(WORKSPACE_ID),
      operations.tenantTemplate(WORKSPACE_ID),
      operations.workspaceConfig().catch(() => null),
    ]);
    const counts: Record<string, number> = {};
    for (const item of overview.attention) counts[sectionIdForStage(item.stage)] =
      (counts[sectionIdForStage(item.stage)] ?? 0) + 1;
    attentionCounts = counts;
    branding = brand.branding;
    enabledModules = modules.enabled;
    sectionLabels = template.terminology.sections ?? null;
    moduleOrder = workspace?.module_order ?? null;
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
    moduleOrder,
    user: {
      name: session.name?.trim() || session.email,
      email: session.email,
      role: session.role,
    },
    dashboardHref: dashboardUrl("/dashboard"),
  };
  return (
    <div className="flex min-h-0 w-full flex-col lg:flex-row" style={themeStyle(branding)}>
      <MobileNav {...sidebarProps} />
      <div className="hidden min-h-0 lg:flex">
        <WorkflowSidebar {...sidebarProps} />
      </div>
      <main className="min-h-0 min-w-0 grow overflow-y-auto">
        <AutoRefresh seconds={60} />
        <div className="page-enter mx-auto flex max-w-[1280px] flex-col gap-6 px-5 py-5 md:px-10 md:py-10">
          {children}
        </div>
      </main>
    </div>
  );
}

function sectionIdForStage(stage: string): string {
  return SECTIONS.find((section) => section.stage === stage)?.id ?? "overview";
}
