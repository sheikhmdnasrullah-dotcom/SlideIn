import { WorkflowSidebar } from "@/components/workspace/sidebar";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import { SECTIONS } from "@/lib/workflow/metadata";

/**
 * Persistent workspace shell. The sidebar stays mounted across section
 * switches — only the page body swaps — so navigating the workflow never
 * loses the section context.
 */
export default async function WorkspaceLayout({ children }: LayoutProps<"/">) {
  let attentionCounts: Record<string, number> | undefined;
  try {
    const overview = await operations.overview(WORKSPACE_ID, 5);
    const counts: Record<string, number> = {};
    for (const item of overview.attention) counts[sectionIdForStage(item.stage)] =
      (counts[sectionIdForStage(item.stage)] ?? 0) + 1;
    attentionCounts = counts;
  } catch {
    // The workspace is usable without the API; every panel says why.
  }

  return (
    <div className="flex min-h-0 w-full">
      <WorkflowSidebar attentionCounts={attentionCounts} workspaceId={WORKSPACE_ID} />
      <main className="min-w-0 grow overflow-y-auto">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-6">{children}</div>
      </main>
    </div>
  );
}

function sectionIdForStage(stage: string): string {
  return SECTIONS.find((section) => section.stage === stage)?.id ?? "overview";
}
