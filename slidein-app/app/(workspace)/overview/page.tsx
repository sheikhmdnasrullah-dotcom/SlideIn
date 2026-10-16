import Link from "next/link";

import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { Metric, MetricRow } from "@/components/system/metric";
import { EmptyState } from "@/components/system/states";
import { StatusBadge } from "@/components/system/status-badge";
import { PageFailure } from "@/components/workspace/page-failure";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import { ATTENTION_TONES, prospectStatusLabel } from "@/lib/workflow/metadata";
import { resolveHref } from "@/lib/workflow/tenant";

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  let overview;
  try {
    overview = await operations.overview(WORKSPACE_ID, 10);
  } catch (error) {
    return <PageFailure error={error} module="overview" />;
  }

  return (
    <>
      <PageHeader
        eyebrow="Workspace · overview"
        title="What needs a decision"
        meta={`${overview.total_prospects} prospects · ${overview.open_conversations} open conversations`}
      />

      <Section title="Pipeline" tone="raised">
        <MetricRow>
          <Metric label="Prospects" value={overview.total_prospects} />
          <Metric label="Replies received" value={overview.replies_received} />
          <Metric label="Open conversations" value={overview.open_conversations} />
          <Metric
            label="Discovered → replied"
            value={`${Math.round(overview.conversion.discovered_to_replied * 100)}%`}
            hint="conversion"
          />
        </MetricRow>
        <Surface variant="inset" className="mt-4 px-4 py-3">
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            {overview.funnel.map((step) => (
              <span key={step.status} className="flex items-baseline gap-2 text-2xs">
                <span className="text-ink-muted">{step.label}</span>
                <span className="font-value tabular-nums text-ink-strong">{step.count}</span>
              </span>
            ))}
          </div>
        </Surface>
      </Section>

      <Section
        title="Attention queue"
        description="Failed runs, drafts waiting on approval, and replies that need a human."
        meta={`${overview.attention.length} open`}
      >
        {overview.attention.length === 0 ? (
          <Surface variant="raised">
            <EmptyState icon="inbox"
              title="Nothing needs attention"
              description="Failures, pending approvals, and unhandled replies will queue here."
            />
          </Surface>
        ) : (
          <Surface variant="raised" className="divide-y divide-rule">
            {overview.attention.map((item, index) => (
              <Link
                key={`${item.subject_id}-${index}`}
                href={resolveHref(item.href)}
                className="flex items-center gap-3 px-6 py-3.5 transition-colors duration-[150ms] hover:bg-surface-2 focus-ring"
              >
                <StatusBadge tone={ATTENTION_TONES[item.severity] ?? "info"} label={item.stage_label} />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-ink-strong">
                    {item.title}
                  </span>
                  <span className="block truncate text-[13px] text-ink-muted">{item.detail}</span>
                </span>
              </Link>
            ))}
          </Surface>
        )}
      </Section>

      <Section title="Next actions" description="The highest-leverage step per prospect, in pipeline order.">
        {overview.next_actions.length === 0 ? (
          <Surface variant="raised">
            <EmptyState icon="inbox"
              title="No next actions"
              description="Ingest prospects under Discovery and actions will appear here."
            />
          </Surface>
        ) : (
          <Surface variant="raised" className="divide-y divide-rule">
            {overview.next_actions.map((action) => (
              <Link
                key={action.prospect_id}
                href={resolveHref(action.href)}
                className="flex items-center gap-3 px-6 py-3.5 transition-colors duration-[150ms] hover:bg-surface-2 focus-ring"
              >
                <span className="min-w-0 grow">
                  <span className="block truncate text-sm font-medium text-ink-strong">
                    {action.name} <span className="text-ink-muted">· {action.company}</span>
                  </span>
                  <span className="block text-[13px] text-ink-muted">
                    {prospectStatusLabel(action.status)} · score {action.score}
                  </span>
                </span>
                <StatusBadge tone="flame" label={action.action_label} />
              </Link>
            ))}
          </Surface>
        )}
      </Section>

      <Section title="Stage health" description="Succeeded / needs-review / failed runs per stage.">
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          {Object.entries(overview.stage_health).map(([stage, health]) => (
            <span key={stage} className="flex items-baseline gap-2 text-2xs">
              <span className="text-ink-muted">{stage}</span>
              <span className="font-value tabular-nums text-status-live">{health.succeeded}</span>
              <span className="font-value tabular-nums text-status-warn">{health.needs_review}</span>
              <span className="font-value tabular-nums text-status-danger">{health.failed}</span>
            </span>
          ))}
          {Object.keys(overview.stage_health).length === 0 && (
            <span className="text-2xs text-ink-muted">No stage runs yet.</span>
          )}
        </div>
      </Section>

      <Section title="Sources" description="Where prospects came from.">
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          {overview.sources.map((source) => (
            <span key={source.source} className="flex items-baseline gap-2 text-2xs">
              <span className="text-ink-muted">{source.source || "unknown"}</span>
              <span className="font-value tabular-nums text-ink-strong">{source.count}</span>
            </span>
          ))}
          {overview.sources.length === 0 && (
            <span className="text-2xs text-ink-muted">No sources yet.</span>
          )}
        </div>
      </Section>
    </>
  );
}
