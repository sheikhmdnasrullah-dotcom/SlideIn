import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { DataTable, type Column } from "@/components/system/data-table";
import { EmptyState } from "@/components/system/states";
import { StatusBadge } from "@/components/system/status-badge";
import { formatDate } from "@/components/system/format";
import { PageFailure } from "@/components/workspace/page-failure";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import type { ActivityLog, StageRun } from "@/lib/api/types";
import { RUN_STATUS_LABELS, RUN_STATUS_TONES, stageLabel } from "@/lib/workflow/metadata";

export const dynamic = "force-dynamic";

const ACTIVITY_COLUMNS: Column<ActivityLog>[] = [
  {
    key: "action",
    header: "Action",
    render: (row) => (
      <span>
        <span className="block font-mono text-2xs text-ink-strong">{row.action}</span>
        <span className="block text-2xs text-ink-faint">
          {row.actor} · {row.actor_role}
        </span>
      </span>
    ),
  },
  {
    key: "summary",
    header: "Summary",
    render: (row) => (
      <span className="block max-w-prose text-2xs leading-relaxed text-ink-muted">
        {row.summary || row.reason || "—"}
      </span>
    ),
  },
  {
    key: "when",
    header: "When",
    align: "right",
    render: (row) => <span className="text-2xs text-ink-muted">{formatDate(row.created_at)}</span>,
  },
];

const RUN_COLUMNS: Column<StageRun>[] = [
  {
    key: "stage",
    header: "Stage",
    render: (row) => <span className="text-ink-strong">{stageLabel(row.stage)}</span>,
  },
  {
    key: "status",
    header: "Status",
    render: (row) => (
      <StatusBadge
        tone={RUN_STATUS_TONES[row.status] ?? "neutral"}
        label={RUN_STATUS_LABELS[row.status] ?? row.status}
      />
    ),
  },
  {
    key: "reason",
    header: "Reason",
    render: (row) => (
      <span className="block max-w-prose text-2xs leading-relaxed text-ink-muted">
        {row.reason || row.error_message || "—"}
      </span>
    ),
  },
];

export default async function ActivityPage() {
  let activity;
  let runs;
  try {
    [activity, runs] = await Promise.all([
      operations.activity(WORKSPACE_ID, { limit: 100 }),
      operations.runs(WORKSPACE_ID, { limit: 50 }),
    ]);
  } catch (error) {
    return <PageFailure error={error} module="activity" />;
  }

  return (
    <>
      <PageHeader
        eyebrow="History · activity"
        title="Activity"
        meta={`${activity.total} events · ${runs.failed.length} failed runs`}
      />

      {(runs.failed.length > 0 || runs.needs_review.length > 0) && (
        <Section
          title="Runs needing attention"
          description="Failed executions and stages waiting on review, newest first."
        >
          <Surface variant="raised">
            <DataTable<StageRun>
              columns={RUN_COLUMNS}
              rows={[...runs.failed, ...runs.needs_review]}
              keyOf={(row) => row.id}
            />
          </Surface>
        </Section>
      )}

      <Section title="History" description="Every consequential action, who took it, and why.">
        <Surface variant="raised">
          <DataTable<ActivityLog>
            columns={ACTIVITY_COLUMNS}
            rows={activity.data}
            keyOf={(row) => row.id}
            empty={
              <EmptyState
                title="No activity yet"
                description="Workflow actions and configuration changes will be recorded here."
              />
            }
          />
        </Surface>
      </Section>
    </>
  );
}
