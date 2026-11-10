import Link from "next/link";

import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { StatusBadge } from "@/components/system/status-badge";
import { PageFailure } from "@/components/workspace/page-failure";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import { requireConsoleSession } from "@/lib/auth/session";
import type { Overview, Readiness } from "@/lib/api/types";
import { ATTENTION_TONES, STAGE_LABELS, STAGE_ORDER, STATUS_NEXT_ACTION } from "@/lib/workflow/metadata";
import { resolveHref } from "@/lib/workflow/tenant";
import type { Stage } from "@/lib/api/types";

export const dynamic = "force-dynamic";

const STAGE_LINKS: Record<Stage, { href: string; module: string; action: string }> = {
  configure: { href: "/setup", module: "settings", action: "Open setup" },
  discover: { href: "/discovery", module: "discovery", action: "Add prospects" },
  research: { href: "/research", module: "research", action: "Open research" },
  qualify: { href: "/qualification", module: "qualification", action: "Open qualification" },
  personalize: { href: "/personalization", module: "personalization", action: "Review drafts" },
  outreach: { href: "/outreach", module: "outreach", action: "Open outreach" },
  converse: { href: "/conversations", module: "inbox", action: "Open conversations" },
  synthesize: { href: "/activity", module: "activity", action: "Open activity" },
};

function stageMetric(stage: Stage, overview: Overview, readiness: Readiness): string {
  if (stage === "configure") {
    const remaining = readiness.checklist.filter((item) => item.status !== "pass").length;
    return readiness.is_ready_for_activation ? "Ready" : `${remaining} setup checks remaining`;
  }
  if (stage === "discover") return `${overview.total_prospects} prospects`;
  if (stage === "research") {
    return `${overview.counts.researching ?? 0} researching · ${overview.counts.researched ?? 0} awaiting qualification`;
  }
  if (stage === "qualify") {
    return `${overview.counts.qualified ?? 0} qualified · ${overview.counts.disqualified ?? 0} disqualified`;
  }
  if (stage === "personalize") {
    const drafts = Object.values(overview.drafts).reduce((sum, count) => sum + count, 0);
    return `${drafts} drafts · ${overview.drafts.pending_review ?? 0} awaiting review`;
  }
  if (stage === "outreach") {
    const sent = Object.values(overview.delivery).reduce((sum, count) => sum + count, 0);
    return `${sent} messages · ${overview.counts.in_campaign ?? 0} in outreach`;
  }
  if (stage === "converse") {
    return `${overview.replies_received} replies · ${overview.open_conversations} open`;
  }
  return `${overview.total_prospects} records`;
}

export default async function OverviewPage() {
  await requireConsoleSession();

  let overview: Overview;
  let readiness: Readiness;
  let sectionPrefs: { id: string; label: string | null; visible: boolean }[];
  try {
    const [overviewResult, profileResult, consoleResult] = await Promise.all([
      operations.overview(WORKSPACE_ID, 20),
      operations.profile(WORKSPACE_ID),
      operations.consoleSections(WORKSPACE_ID),
    ]);
    overview = overviewResult;
    readiness = profileResult.readiness;
    sectionPrefs = consoleResult.sections;
  } catch (error) {
    return <PageFailure error={error} module="overview" />;
  }

  const labels = new Map(sectionPrefs.map((section) => [section.id, section.label]));
  const hidden = new Set(sectionPrefs.filter((section) => !section.visible).map((section) => section.id));
  const stages = STAGE_ORDER.filter((stage) => !hidden.has(STAGE_LINKS[stage].module));

  return (
    <>
      <PageHeader
        title="Workflow"
        meta={`${overview.total_prospects} prospects · ${overview.open_conversations} open conversations`}
      />

      {stages.map((stage, index) => {
        const link = STAGE_LINKS[stage];
        const health = overview.stage_health[stage];
        const attention = overview.attention.filter((item) => item.stage === stage);
        const actions = overview.next_actions.filter(
          (action) => STATUS_NEXT_ACTION[action.status]?.stage === stage,
        );
        const failed = health?.failed ?? 0;
        const review = health?.needs_review ?? 0;
        const tone = failed ? "danger" : review ? "warn" : health?.succeeded ? "live" : "neutral";
        const status = failed ? "failed" : review ? "review" : health?.succeeded ? "active" : "waiting";

        return (
          <Section
            key={stage}
            title={`${index + 1}. ${labels.get(link.module) || STAGE_LABELS[stage]}`}
            meta={stageMetric(stage, overview, readiness)}
            actions={
              <Link href={link.href} className="text-xs font-medium text-flame-vivid hover:underline focus-ring">
                {link.action}
              </Link>
            }
          >
            <div className="flex flex-wrap items-center gap-3 px-6 py-3">
              <StatusBadge tone={tone} label={status} />
              {health?.succeeded ? (
                <span className="text-2xs text-ink-muted">{health.succeeded} completed</span>
              ) : null}
              {failed ? <span className="text-2xs text-status-danger">{failed} failed</span> : null}
              {review ? <span className="text-2xs text-status-warn">{review} need review</span> : null}
            </div>

            {attention.length > 0 || actions.length > 0 ? (
              <Surface variant="inset" className="mx-4 mb-4 divide-y divide-rule">
                {attention.map((item) => (
                  <Link
                    key={item.run_id || `${item.subject_id}-${item.kind}`}
                    href={resolveHref(item.href)}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-surface-2 focus-ring"
                  >
                    <StatusBadge tone={ATTENTION_TONES[item.severity] ?? "info"} label={item.stage_label} />
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-ink-strong">{item.title}</span>
                      <span className="block truncate text-2xs text-ink-muted">{item.detail}</span>
                    </span>
                  </Link>
                ))}
                {actions.map((action) => (
                  <Link
                    key={action.prospect_id}
                    href={resolveHref(action.href)}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-surface-2 focus-ring"
                  >
                    <span className="min-w-0 grow">
                      <span className="block truncate text-sm text-ink-strong">{action.name}</span>
                      <span className="block truncate text-2xs text-ink-muted">{action.company}</span>
                    </span>
                    <StatusBadge tone="flame" label={action.action_label} />
                  </Link>
                ))}
              </Surface>
            ) : null}
          </Section>
        );
      })}
    </>
  );
}
