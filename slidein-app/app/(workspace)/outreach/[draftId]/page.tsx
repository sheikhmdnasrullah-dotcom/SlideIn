import Link from "next/link";

import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { DefList, DefRow, formatDate } from "@/components/system/format";
import { EmptyState } from "@/components/system/states";
import { StatusBadge } from "@/components/system/status-badge";
import { EvidenceBlock } from "@/components/system/evidence";
import { PageFailure } from "@/components/workspace/page-failure";
import { ApproveForm, RejectForm, TriggerButton } from "@/components/workspace/action-forms";
import { revokeApprovalAction, sendDraftAction } from "@/lib/api/actions";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import {
  DRAFT_STATUS_LABELS,
  DRAFT_STATUS_TONES,
} from "@/lib/workflow/metadata";

export const dynamic = "force-dynamic";

export default async function DraftPage({ params }: { params: Promise<{ draftId: string }> }) {
  const { draftId } = await params;
  let draft;
  try {
    draft = await operations.draft(WORKSPACE_ID, draftId);
  } catch (error) {
    return <PageFailure error={error} module="outreach" />;
  }

  const prospect = draft.prospect;

  return (
    <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-6">
      <PageHeader
        eyebrow="Workflow · draft review"
        title={draft.subject || "Untitled draft"}
        meta={`v${draft.version}${draft.human_edited ? " · human-edited" : ""}`}
        actions={
          <StatusBadge
            tone={DRAFT_STATUS_TONES[draft.status] ?? "neutral"}
            label={DRAFT_STATUS_LABELS[draft.status] ?? draft.status}
          />
        }
      />

      <Section title="Message" tone="raised">
        {prospect && (
          <p className="pb-3 text-2xs text-ink-muted">
            To{" "}
            <Link href={`/discovery/${prospect.id}`} className="underline underline-offset-2 hover:text-ink-strong">
              {prospect.full_name} · {prospect.email}
            </Link>{" "}
            — {prospect.company_name}
          </p>
        )}
        <p className="max-w-prose whitespace-pre-wrap text-[0.8125rem] leading-relaxed text-ink-strong">
          {draft.body}
        </p>
        <div className="mt-4 border-t border-rule pt-4">
          <DefList>
            <DefRow label="Approved by">{draft.approved_by || "—"}</DefRow>
            <DefRow label="Approved at">{draft.approved_at ? formatDate(draft.approved_at) : "—"}</DefRow>
            <DefRow label="Approval note">{draft.approval_note || "—"}</DefRow>
            <DefRow label="Rejected by">{draft.rejected_by || "—"}</DefRow>
            <DefRow label="Reject reason">{draft.rejected_reason || "—"}</DefRow>
          </DefList>
        </div>
      </Section>

      {draft.status === "pending_review" && (
        <Section title="Review" description="Approve to allow sending, or reject with a reason.">
          <div className="grid gap-4 lg:grid-cols-2">
            <Surface variant="inset">
              <ApproveForm draftId={draft.id} />
            </Surface>
            <Surface variant="inset">
              <RejectForm draftId={draft.id} />
            </Surface>
          </div>
        </Section>
      )}

      {draft.status === "approved" && (
        <Section title="Dispatch" description="Approved and ready. Sending is checked against policy and suppression first.">
          <div className="flex flex-wrap gap-2">
            <TriggerButton
              invoke={sendDraftAction}
              id={draft.id}
              label="Send now"
              variant="default"
              size="md"
              dot
              confirm="Send this draft now? Policy and suppression checks run first."
            />
            <TriggerButton invoke={revokeApprovalAction} id={draft.id} label="Revoke approval" />
          </div>
        </Section>
      )}

      <Section title="Attributed evidence" meta={`${draft.evidence.length} items`}>
        {draft.evidence.length === 0 ? (
          <Surface variant="raised">
            <EmptyState icon="document" title="No attributed evidence" description="This draft cites no evidence items." />
          </Surface>
        ) : (
          <Surface variant="raised" className="px-4 py-2">
            <EvidenceBlock evidence={draft.evidence} />
          </Surface>
        )}
      </Section>

      {draft.versions.length > 0 && (
        <Section title="Versions" meta={`${draft.versions.length} versions`}>
          <Surface variant="inset" className="divide-y divide-rule px-4 py-1">
            {draft.versions.map((version) => (
              <div key={version.id} className="py-2">
                <div className="flex items-baseline justify-between gap-3 text-2xs">
                  <span className="font-medium text-ink-strong">
                    v{version.version} {version.is_human_edit ? "· human edit" : "· generated"}
                  </span>
                  <span className="text-ink-muted">
                    {version.changed_by} · {formatDate(version.created_at)}
                  </span>
                </div>
                {version.change_reason && (
                  <p className="pt-0.5 text-2xs text-ink-muted">{version.change_reason}</p>
                )}
              </div>
            ))}
          </Surface>
        </Section>
      )}
    </div>
  );
}
