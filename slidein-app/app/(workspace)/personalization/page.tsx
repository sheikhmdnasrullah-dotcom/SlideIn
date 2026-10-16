import Link from "next/link";

import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { DataTable, type Column } from "@/components/system/data-table";
import { EmptyState } from "@/components/system/states";
import { StatusBadge } from "@/components/system/status-badge";
import { PageFailure } from "@/components/workspace/page-failure";
import { TriggerButton } from "@/components/workspace/action-forms";
import { personalizeAction } from "@/lib/api/actions";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import type { Draft, Prospect } from "@/lib/api/types";
import {
  DRAFT_STATUS_LABELS,
  DRAFT_STATUS_TONES,
} from "@/lib/workflow/metadata";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

const QUEUE_COLUMNS: Column<Prospect>[] = [
  {
    key: "name",
    header: "Prospect",
    render: (row) => (
      <span>
        <span className="block font-medium text-ink-strong">{row.full_name || row.email}</span>
        <span className="block text-[13px] text-ink-muted">
          {row.company_name} · score {row.qualification_score}
        </span>
      </span>
    ),
  },
  {
    key: "action",
    header: "Draft",
    align: "right",
    render: (row) => <TriggerButton invoke={personalizeAction} id={row.id} label="Prepare draft" />,
  },
];

const DRAFT_COLUMNS: Column<Draft>[] = [
  {
    key: "subject",
    header: "Subject",
    render: (row) => <span className="font-medium text-ink-strong">{row.subject}</span>,
  },
  {
    key: "status",
    header: "Status",
    render: (row) => (
      <StatusBadge
        tone={DRAFT_STATUS_TONES[row.status] ?? "neutral"}
        label={DRAFT_STATUS_LABELS[row.status] ?? row.status}
      />
    ),
  },
  {
    key: "version",
    header: "Version",
    align: "right",
    render: (row) => (
      <span className="font-value tabular-nums text-ink-muted">
        v{row.version}
        {row.human_edited ? " · edited" : ""}
      </span>
    ),
  },
];

const DRAFT_STATUSES = ["pending_review", "approved", "rejected", "sent", "cancelled"];

export default async function PersonalizationPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const params = await searchParams;
  const status = params.status || undefined;

  let queue;
  let drafts;
  try {
    [queue, drafts] = await Promise.all([
      operations.prospects(WORKSPACE_ID, { status: "qualified", limit: 100 }),
      operations.drafts(WORKSPACE_ID, { status, limit: 100 }),
    ]);
  } catch (error) {
    return <PageFailure error={error} module="personalization" />;
  }

  return (
    <>
      <PageHeader
        eyebrow="Workflow · personalize"
        title="Personalization"
        meta={`${queue.total} awaiting · ${drafts.total} drafts`}
      />

      <Section
        title="Draft queue"
        description="Qualified prospects. Every draft sentence rests on attributed evidence — thin evidence yields needs-review, never filler."
      >
        <Surface variant="raised">
          <DataTable<Prospect>
            columns={QUEUE_COLUMNS}
            rows={queue.data}
            keyOf={(row) => row.id}
            rowHref={(row) => `/discovery/${row.id}`}
            empty={
              <EmptyState icon="document"
                title="Queue is clear"
                description="Qualify prospects first; they arrive here draft-ready."
              />
            }
          />
        </Surface>
      </Section>

      <Section title="Drafts" meta={`${drafts.data.length} shown`}>
        <Surface variant="raised">
          <div className="mb-4 flex w-fit max-w-full flex-wrap items-center gap-1 rounded-pill bg-status-neutral-bg p-1">
            <Link
              href="/personalization"
              aria-current={!status || undefined}
              className={cn(
                "flex h-8 items-center rounded-pill px-3.5 text-[13px] font-medium transition-all duration-[220ms focus-ring",
                !status
                  ? "bg-surface text-ink-strong shadow-raised"
                  : "text-ink-muted hover:text-ink-strong",
              )}
            >
              All
            </Link>
            {DRAFT_STATUSES.map((value) => (
              <Link
                key={value}
                href={`/personalization?status=${value}`}
                aria-current={status === value || undefined}
                className={cn(
                  "flex h-8 items-center rounded-pill px-3.5 text-[13px] font-medium transition-all duration-[220ms focus-ring",
                  status === value
                    ? "bg-surface text-ink-strong shadow-raised"
                    : "text-ink-muted hover:text-ink-strong",
                )}
              >
                {DRAFT_STATUS_LABELS[value as Draft["status"]] ?? value}
              </Link>
            ))}
          </div>
          <DataTable<Draft>
            columns={DRAFT_COLUMNS}
            rows={drafts.data}
            keyOf={(row) => row.id}
            rowHref={(row) => `/outreach/${row.id}`}
            empty={<EmptyState icon="document" title="No drafts" description="Prepare a draft above." />}
          />
        </Surface>
      </Section>
    </>
  );
}
