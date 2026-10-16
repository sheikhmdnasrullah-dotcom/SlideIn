import Link from "next/link";

import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { DataTable, type Column } from "@/components/system/data-table";
import { EmptyState } from "@/components/system/states";
import { StatusBadge } from "@/components/system/status-badge";
import { PageFailure } from "@/components/workspace/page-failure";
import { TriggerButton } from "@/components/workspace/action-forms";
import { qualifyAction } from "@/lib/api/actions";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import type { Prospect, Qualification } from "@/lib/api/types";
import {
  PROSPECT_STATUS_TONES,
  prospectStatusLabel,
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
        <span className="block text-[13px] text-ink-muted">{row.company_name}</span>
      </span>
    ),
  },
  {
    key: "status",
    header: "Status",
    render: (row) => (
      <StatusBadge
        tone={PROSPECT_STATUS_TONES[row.status] ?? "neutral"}
        label={prospectStatusLabel(row.status)}
      />
    ),
  },
  {
    key: "action",
    header: "Qualify",
    align: "right",
    render: (row) => <TriggerButton invoke={qualifyAction} id={row.id} label="Qualify" />,
  },
];

const RESULT_COLUMNS: Column<Qualification>[] = [
  {
    key: "score",
    header: "Score",
    render: (row) => (
      <span className="font-value text-base tabular-nums text-ink-strong">{row.score}</span>
    ),
  },
  {
    key: "verdict",
    header: "Verdict",
    render: (row) => (
      <StatusBadge tone={row.is_qualified ? "live" : "warn"} label={row.is_qualified ? "Qualified" : "Not qualified"} />
    ),
  },
  {
    key: "explanation",
    header: "Explanation",
    render: (row) => (
      <span className="block max-w-prose text-2xs leading-relaxed text-ink-muted">
        {row.explanation || "—"}
      </span>
    ),
  },
];

export default async function QualificationPage({
  searchParams,
}: {
  searchParams: Promise<{ qualified_only?: string }>;
}) {
  const params = await searchParams;
  const qualifiedOnly = params.qualified_only === "true";

  let queue;
  let results;
  try {
    [queue, results] = await Promise.all([
      operations.prospects(WORKSPACE_ID, { status: "researched", limit: 100 }),
      operations.qualifications(WORKSPACE_ID, qualifiedOnly, 100),
    ]);
  } catch (error) {
    return <PageFailure error={error} module="qualification" />;
  }

  return (
    <>
      <PageHeader
        eyebrow="Workflow · qualify"
        title="Qualification"
        meta={`${queue.total} awaiting · ${results.total} scored`}
      />

      <Section
        title="Qualification queue"
        description="Researched prospects are scored against the active ICP by a fixed-weight rubric — the same weights every time."
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
                description="Research prospects first; they arrive here scored-ready."
              />
            }
          />
        </Surface>
      </Section>

      <Section title="Results" meta={`${results.data.length} shown`}>
        <Surface variant="raised">
          <div className="mb-4 flex w-fit max-w-full flex-wrap items-center gap-1 rounded-pill bg-status-neutral-bg p-1">
            <Link
              href="/qualification"
              aria-current={!qualifiedOnly || undefined}
              className={cn(
                "flex h-8 items-center rounded-pill px-3.5 text-[13px] font-medium transition-all duration-[220ms focus-ring",
                !qualifiedOnly
                  ? "bg-surface text-ink-strong shadow-raised"
                  : "text-ink-muted hover:text-ink-strong",
              )}
            >
              All
            </Link>
            <Link
              href="/qualification?qualified_only=true"
              aria-current={qualifiedOnly || undefined}
              className={cn(
                "flex h-8 items-center rounded-pill px-3.5 text-[13px] font-medium transition-all duration-[220ms focus-ring",
                qualifiedOnly
                  ? "bg-surface text-ink-strong shadow-raised"
                  : "text-ink-muted hover:text-ink-strong",
              )}
            >
              Qualified only
            </Link>
          </div>
          <DataTable<Qualification>
            columns={RESULT_COLUMNS}
            rows={results.data}
            keyOf={(row) => row.id}
            rowHref={(row) => `/discovery/${row.prospect_id}`}
            empty={
              <EmptyState icon="document" title="No qualification results" description="Qualify a prospect above." />
            }
          />
        </Surface>
      </Section>
    </>
  );
}
