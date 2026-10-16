import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { DataTable, type Column } from "@/components/system/data-table";
import { EmptyState } from "@/components/system/states";
import { StatusBadge } from "@/components/system/status-badge";
import { PageFailure } from "@/components/workspace/page-failure";
import { TriggerButton } from "@/components/workspace/action-forms";
import { researchAction } from "@/lib/api/actions";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import type { Prospect } from "@/lib/api/types";
import {
  PROSPECT_STATUS_TONES,
  prospectStatusLabel,
} from "@/lib/workflow/metadata";

export const dynamic = "force-dynamic";

const COLUMNS: Column<Prospect>[] = [
  {
    key: "name",
    header: "Prospect",
    render: (row) => (
      <span>
        <span className="block text-ink-strong">{row.full_name || row.email}</span>
        <span className="block text-2xs text-ink-faint">
          {row.company_name} · {row.company_domain}
        </span>
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
    header: "Research",
    align: "right",
    render: (row) => <TriggerButton invoke={researchAction} id={row.id} label="Run research" />,
  },
];

export default async function ResearchPage() {
  let discovered;
  let researched;
  try {
    [discovered, researched] = await Promise.all([
      operations.prospects(WORKSPACE_ID, { status: "discovered", limit: 100 }),
      operations.prospects(WORKSPACE_ID, { status: "researched", limit: 100 }),
    ]);
  } catch (error) {
    return <PageFailure error={error} module="research" />;
  }
  const queue = [...discovered.data];

  return (
    <>
      <PageHeader
        eyebrow="Workflow · research"
        title="Research"
        meta={`${queue.length} awaiting · ${researched.total} researched`}
      />

      <Section
        title="Research queue"
        description="Discovered prospects with no verified evidence yet. Research collects source-backed claims; every claim keeps its source."
      >
        <Surface variant="raised">
          <DataTable<Prospect>
            columns={COLUMNS}
            rows={queue}
            keyOf={(row) => row.id}
            rowHref={(row) => `/discovery/${row.id}`}
            empty={
              <EmptyState
                title="Queue is clear"
                description="Ingest prospects under Discovery to fill the research queue."
              />
            }
          />
        </Surface>
      </Section>

      <Section title="Recently researched" meta={`${researched.data.length} shown`}>
        {researched.data.length === 0 ? (
          <EmptyState title="Nothing researched yet" description="Run research above." />
        ) : (
          <Surface variant="inset" className="divide-y divide-rule px-4 py-1">
            {researched.data.slice(0, 10).map((row) => (
              <div key={row.id} className="flex items-baseline justify-between gap-3 py-1.5 text-2xs">
                <span className="text-ink-strong">
                  {row.full_name || row.email} <span className="text-ink-faint">· {row.company_name}</span>
                </span>
                <span className="font-value tabular-nums text-ink-muted">score {row.qualification_score}</span>
              </div>
            ))}
          </Surface>
        )}
      </Section>
    </>
  );
}
