import Link from "next/link";

import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { DataTable, type Column } from "@/components/system/data-table";
import { EmptyState } from "@/components/system/states";
import { StatusBadge } from "@/components/system/status-badge";
import { PageFailure } from "@/components/workspace/page-failure";
import { IngestForm } from "@/components/workspace/action-forms";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import type { Prospect } from "@/lib/api/types";
import {
  PROSPECT_STATUS_LABELS,
  PROSPECT_STATUS_TONES,
  prospectStatusLabel,
} from "@/lib/workflow/metadata";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

const STATUSES = Object.keys(PROSPECT_STATUS_LABELS);

const COLUMNS: Column<Prospect>[] = [
  {
    key: "name",
    header: "Prospect",
    render: (row) => (
      <span>
        <span className="block font-medium text-ink-strong">{row.full_name || row.email}</span>
        <span className="block text-[13px] text-ink-muted">{row.email}</span>
      </span>
    ),
  },
  {
    key: "company",
    header: "Company",
    render: (row) => (
      <span>
        <span className="block text-ink-strong">{row.company_name || "—"}</span>
        <span className="block text-[13px] text-ink-muted">{row.job_title}</span>
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
    key: "score",
    header: "Score",
    align: "right",
    render: (row) => <span className="font-value tabular-nums">{row.qualification_score}</span>,
  },
  {
    key: "source",
    header: "Source",
    render: (row) => <span className="text-ink-muted">{row.source || "—"}</span>,
  },
];

export default async function DiscoveryPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; search?: string }>;
}) {
  const params = await searchParams;
  const status = params.status || undefined;
  const search = params.search || undefined;

  let page;
  try {
    page = await operations.prospects(WORKSPACE_ID, { status, search, limit: 100 });
  } catch (error) {
    return <PageFailure error={error} module="discovery" />;
  }

  return (
    <>
      <PageHeader
        eyebrow="Workflow · discover"
        title="Discovery"
        meta={`${page.total} prospects`}
      />

      <Section
        title="Ingest prospects"
        description="Paste CSV rows. Duplicates are reported, never merged; bad rows are skipped with a reason."
        tone="raised"
      >
        <IngestForm />
      </Section>

      <Section title="Prospects" meta={`${page.data.length} shown`}>
        <Surface variant="raised">
          <div className="mb-4 flex w-fit max-w-full flex-wrap items-center gap-1 rounded-pill bg-status-neutral-bg p-1">
            <FilterChip href="/discovery" active={!status} label="All" />
            {STATUSES.map((value) => (
              <FilterChip
                key={value}
                href={`/discovery?status=${value}`}
                active={status === value}
                label={prospectStatusLabel(value)}
              />
            ))}
          </div>
          <DataTable<Prospect>
            columns={COLUMNS}
            rows={page.data}
            keyOf={(row) => row.id}
            rowHref={(row) => `/discovery/${row.id}`}
            empty={
              <EmptyState icon="search"
                title="No prospects match"
                description="Ingest above, or clear the filter."
              />
            }
          />
        </Surface>
      </Section>
    </>
  );
}

function FilterChip({ href, active, label }: { href: string; active: boolean; label: string }) {
  return (
    <Link
      href={href}
      aria-current={active || undefined}
      className={cn(
        "flex h-8 items-center rounded-pill px-3.5 text-[13px] font-medium transition-all duration-[220ms focus-ring",
        active
          ? "bg-surface text-ink-strong shadow-raised"
          : "text-ink-muted hover:text-ink-strong",
      )}
    >
      {label}
    </Link>
  );
}
