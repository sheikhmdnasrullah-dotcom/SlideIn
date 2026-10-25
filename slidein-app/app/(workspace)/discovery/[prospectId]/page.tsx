import Link from "next/link";

import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { DefList, DefRow, formatDate } from "@/components/system/format";
import { EmptyState } from "@/components/system/states";
import { StatusBadge } from "@/components/system/status-badge";
import { EvidenceBlock } from "@/components/system/evidence";
import { Timeline } from "@/components/system/timeline";
import { PageFailure } from "@/components/workspace/page-failure";
import { TriggerButton } from "@/components/workspace/action-forms";
import { personalizeAction, qualifyAction, researchAction, osintAction } from "@/lib/api/actions";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import {
  DRAFT_STATUS_LABELS,
  DRAFT_STATUS_TONES,
  PROSPECT_STATUS_TONES,
  STATUS_NEXT_ACTION,
  prospectStatusLabel,
} from "@/lib/workflow/metadata";

export const dynamic = "force-dynamic";

export default async function ProspectPage({ params }: { params: Promise<{ prospectId: string }> }) {
  const { prospectId } = await params;
  let prospect;
  try {
    prospect = await operations.prospect(WORKSPACE_ID, prospectId);
  } catch (error) {
    return <PageFailure error={error} module="discovery" />;
  }

  const next = STATUS_NEXT_ACTION[prospect.status];
  const evidence = prospect.evidence ?? [];
  const osintEvidence = evidence.filter((item) => item.collector.startsWith("openosint"));
  const qualifications = prospect.qualification ?? [];
  const latestQualification = qualifications[qualifications.length - 1];
  const drafts = prospect.drafts ?? [];
  const sent = prospect.sent_messages ?? [];
  const runs = prospect.stage_runs ?? [];
  const history = prospect.state_history ?? [];

  return (
    <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-6">
      <PageHeader
        eyebrow="Workflow · prospect record"
        title={prospect.full_name || prospect.email}
        meta={`${prospect.email} · ${prospect.company_name}`}
        actions={
          <StatusBadge
            tone={PROSPECT_STATUS_TONES[prospect.status] ?? "neutral"}
            label={prospectStatusLabel(prospect.status)}
          />
        }
      />

      <Section title="Record" tone="raised">
        <DefList>
          <DefRow label="Company">{`${prospect.company_name}${prospect.company_domain ? ` · ${prospect.company_domain}` : ""}`}</DefRow>
          <DefRow label="Title">{prospect.job_title || "—"}</DefRow>
          <DefRow label="Location">{prospect.location || "—"}</DefRow>
          <DefRow label="Source">{`${prospect.source}${prospect.source_ref ? ` · ${prospect.source_ref}` : ""}`}</DefRow>
          <DefRow label="Score">{String(prospect.qualification_score)}</DefRow>
          <DefRow label="Discovered">{formatDate(prospect.discovered_at)}</DefRow>
        </DefList>
        <div className="mt-4 flex flex-wrap gap-2 border-t border-rule pt-4">
          <TriggerButton invoke={researchAction} id={prospect.id} label="Run research" />
          <TriggerButton invoke={osintAction} id={prospect.id} label="Run OSINT" />
          <TriggerButton invoke={qualifyAction} id={prospect.id} label="Qualify" />
          <TriggerButton invoke={personalizeAction} id={prospect.id} label="Prepare draft" />
          <span className="self-center text-2xs text-ink-muted">
            Suggested next: {next.label}
          </span>
        </div>
      </Section>

      <Section title="OSINT" meta={`${osintEvidence.length} rows`}>
        {osintEvidence.length === 0 ? (
          <Surface variant="raised">
            <EmptyState
              icon="search"
              title="No OSINT rows yet"
              description="Run OSINT to execute the OpenOSINT lookups (dns, exposure, github) against this record and file each result as evidence."
            />
          </Surface>
        ) : (
          <Surface variant="raised" className="px-4 py-2">
            <EvidenceBlock evidence={osintEvidence} compact />
          </Surface>
        )}
      </Section>

      <Section title="Evidence" meta={`${evidence.length} items`}>
        {evidence.length === 0 ? (
          <Surface variant="raised">
            <EmptyState icon="document" title="No evidence yet" description="Run research to collect source-backed claims." />
          </Surface>
        ) : (
          <Surface variant="raised" className="px-4 py-2">
            <EvidenceBlock evidence={evidence} />
          </Surface>
        )}
      </Section>

      {latestQualification && (
        <Section title="Latest qualification" meta={`score ${latestQualification.score}`}>
          <p className="max-w-prose text-[0.8125rem] leading-relaxed text-ink-muted">
            {latestQualification.explanation || "No explanation recorded."}
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <h3 className="font-label pb-2 text-ink-muted">Matching criteria</h3>
              <Surface variant="inset" className="divide-y divide-rule px-4 py-1">
                {latestQualification.matching_criteria.map((criterion, index) => (
                  <div key={index} className="flex items-baseline justify-between gap-3 py-1.5 text-2xs">
                    <span className="font-medium text-ink-strong">{criterion.criterion}</span>
                    <span className="font-value tabular-nums text-status-live">
                      {criterion.points}/{criterion.max_points}
                    </span>
                  </div>
                ))}
                {latestQualification.matching_criteria.length === 0 && (
                  <p className="py-2 text-2xs text-ink-muted">None.</p>
                )}
              </Surface>
            </div>
            <div>
              <h3 className="font-label pb-2 text-ink-muted">Missing criteria</h3>
              <Surface variant="inset" className="divide-y divide-rule px-4 py-1">
                {latestQualification.missing_criteria.map((criterion, index) => (
                  <div key={index} className="flex items-baseline justify-between gap-3 py-1.5 text-2xs">
                    <span className="font-medium text-ink-strong">{criterion.criterion}</span>
                    <span className="font-value tabular-nums text-status-warn">
                      {criterion.points}/{criterion.max_points}
                    </span>
                  </div>
                ))}
                {latestQualification.missing_criteria.length === 0 && (
                  <p className="py-2 text-2xs text-ink-muted">None.</p>
                )}
              </Surface>
            </div>
          </div>
        </Section>
      )}

      <Section title="Drafts" meta={`${drafts.length} drafts`}>
        {drafts.length === 0 ? (
          <Surface variant="raised">
            <EmptyState icon="document" title="No drafts" description="Prepare a draft to start personalization." />
          </Surface>
        ) : (
          <Surface variant="raised" className="divide-y divide-rule">
            {drafts.map((draft) => (
              <Link
                key={draft.id}
                href={`/outreach/${draft.id}`}
                className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-surface-2"
              >
                <span className="min-w-0 grow">
                  <span className="block truncate text-[0.8125rem] text-ink-strong">{draft.subject}</span>
                  <span className="block text-[13px] text-ink-muted">v{draft.version}</span>
                </span>
                <StatusBadge
                  tone={DRAFT_STATUS_TONES[draft.status] ?? "neutral"}
                  label={DRAFT_STATUS_LABELS[draft.status] ?? draft.status}
                />
              </Link>
            ))}
          </Surface>
        )}
      </Section>

      <Section title="Deliveries" meta={`${sent.length} sent`}>
        {sent.length === 0 ? (
          <Surface variant="raised">
            <EmptyState icon="send" title="Nothing sent" description="Approved drafts dispatch from Outreach." />
          </Surface>
        ) : (
          <Surface variant="inset" className="divide-y divide-rule px-4 py-1">
            {sent.map((message) => (
              <div key={message.id} className="flex items-baseline justify-between gap-3 py-1.5 text-2xs">
                <span className="font-medium text-ink-strong">{message.recipient_email}</span>
                <span className="text-ink-muted">
                  {message.transport} · {message.delivery_status} · {formatDate(message.queued_at)}
                </span>
              </div>
            ))}
          </Surface>
        )}
      </Section>

      {runs.length > 0 && (
        <Section title="Stage runs" meta={`${runs.length} runs`}>
          <Timeline
            items={runs.map((run) => ({
              id: run.id,
              title: `${run.stage} · ${run.status}`,
              description: run.reason || run.error_message || undefined,
              when: run.started_at,
              tone: run.status === "succeeded" ? "live" : run.status === "failed" ? "danger" : "warn",
            }))}
          />
        </Section>
      )}

      {history.length > 0 && (
        <Section title="Status history">
          <Surface variant="inset" className="divide-y divide-rule px-4 py-1">
            {history.map((entry, index) => (
              <div key={index} className="flex items-baseline justify-between gap-3 py-1.5 text-2xs">
                <span className="font-medium text-ink-strong">{prospectStatusLabel(entry.state)}</span>
                <span className="text-ink-muted">
                  {formatDate(entry.entered_at)}{entry.reason ? ` · ${entry.reason}` : ""}
                </span>
              </div>
            ))}
          </Surface>
        </Section>
      )}
    </div>
  );
}
