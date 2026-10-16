import Link from "next/link";

import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { DataTable, type Column } from "@/components/system/data-table";
import { DefList, DefRow, formatDate } from "@/components/system/format";
import { EmptyState } from "@/components/system/states";
import { StatusBadge } from "@/components/system/status-badge";
import { PageFailure } from "@/components/workspace/page-failure";
import { SuppressionForm, TriggerButton } from "@/components/workspace/action-forms";
import { removeSuppressionAction } from "@/lib/api/actions";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import type { Draft, SentMessage, SuppressionRecord } from "@/lib/api/types";
import {
  DRAFT_STATUS_LABELS,
  DRAFT_STATUS_TONES,
} from "@/lib/workflow/metadata";

export const dynamic = "force-dynamic";

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
];

const SENT_COLUMNS: Column<SentMessage>[] = [
  {
    key: "recipient",
    header: "Recipient",
    render: (row) => (
      <span>
        <span className="block text-ink-strong">{row.recipient_email}</span>
        <span className="block text-[13px] text-ink-muted">{row.sender_email}</span>
      </span>
    ),
  },
  {
    key: "status",
    header: "Delivery",
    render: (row) => (
      <StatusBadge
        tone={row.delivery_status === "delivered" ? "live" : row.delivery_status === "bounced" || row.delivery_status === "complained" || row.delivery_status === "failed" ? "danger" : "info"}
        label={row.delivery_status}
      />
    ),
  },
  {
    key: "transport",
    header: "Transport",
    render: (row) => <span className="text-ink-muted">{row.transport}</span>,
  },
];

const SUPPRESSION_COLUMNS: Column<SuppressionRecord>[] = [
  {
    key: "email",
    header: "Email",
    render: (row) => (
      <span>
        <span className="block font-medium text-ink-strong">{row.email}</span>
        <span className="block text-[13px] text-ink-muted">{row.reason}{row.note ? ` · ${row.note}` : ""}</span>
      </span>
    ),
  },
  {
    key: "by",
    header: "Suppressed by",
    render: (row) => (
      <span className="text-ink-muted">
        {row.suppressed_by} · {formatDate(row.suppressed_at)}
      </span>
    ),
  },
  {
    key: "action",
    header: "",
    align: "right",
    render: (row) => (
      <TriggerButton
        invoke={removeSuppressionAction}
        id={row.id}
        label="Remove"
        variant="quiet"
        confirm={`Remove suppression for ${row.email}? It can be sent to again.`}
      />
    ),
  },
];

export default async function OutreachPage() {
  let pending;
  let policy;
  let sent;
  let suppression;
  try {
    [pending, policy, sent, suppression] = await Promise.all([
      operations.drafts(WORKSPACE_ID, { status: "pending_review", limit: 100 }),
      operations.policy(WORKSPACE_ID),
      operations.sentMessages(WORKSPACE_ID),
      operations.suppression(WORKSPACE_ID),
    ]);
  } catch (error) {
    return <PageFailure error={error} module="outreach" />;
  }

  return (
    <>
      <PageHeader
        eyebrow="Workflow · outreach"
        title="Outreach"
        meta={`${pending.total} pending review · ${sent.total} sent`}
      />

      <Section
        title="Pending approval"
        description="Nothing sends without a human decision. Open a draft to review its evidence, then approve or reject."
      >
        <Surface variant="raised">
          <DataTable<Draft>
            columns={DRAFT_COLUMNS}
            rows={pending.data}
            keyOf={(row) => row.id}
            rowHref={(row) => `/outreach/${row.id}`}
            empty={
              <EmptyState icon="send"
                title="Nothing awaiting approval"
                description="Approved drafts can be sent from their review page."
              />
            }
          />
        </Surface>
      </Section>

      <Section title="Sending policy" description="Hard limits the API enforces on every dispatch.">
        <Surface variant="inset" className="px-4 py-2">
          <DefList>
            <DefRow label="Approval required">{policy.policy.require_approval ? "Yes" : "No"}</DefRow>
            <DefRow label="Daily limit">{String(policy.policy.daily_limit)}</DefRow>
            <DefRow label="Hourly limit">{String(policy.policy.hourly_limit)}</DefRow>
            <DefRow label="Max attempts">{String(policy.policy.max_attempts)}</DefRow>
            <DefRow label="Send window">{policy.policy.send_window || "—"}</DefRow>
            <DefRow label="Allowed senders">{policy.policy.allowed_senders.join(", ") || "—"}</DefRow>
          </DefList>
        </Surface>
      </Section>

      <Section title="Sent" meta={`${sent.total} messages`}>
        {sent.data.length === 0 ? (
          <Surface variant="raised">
            <EmptyState icon="send" title="Nothing sent yet" description="Approved drafts dispatch from their review page." />
          </Surface>
        ) : (
          <Surface variant="raised">
            <DataTable<SentMessage>
              columns={SENT_COLUMNS}
              rows={sent.data}
              keyOf={(row) => row.id}
            />
          </Surface>
        )}
      </Section>

      <Section
        title="Suppression list"
        description="Suppressed addresses are never sent to, by any stage. Bounces and complaints land here automatically."
        meta={`${suppression.total} entries`}
      >
        <Surface variant="raised" className="mb-4">
          <DataTable<SuppressionRecord>
            columns={SUPPRESSION_COLUMNS}
            rows={suppression.data}
            keyOf={(row) => row.id}
            empty={<EmptyState icon="inbox" title="No suppressions" description="Opt-outs and bounces will appear here." />}
          />
        </Surface>
        <Surface variant="raised">
          <SuppressionForm />
        </Surface>
      </Section>

      <p className="text-xs text-ink-muted">
        Review all drafts under <Link href="/personalization" className="underline underline-offset-2 hover:text-ink-strong">Personalization</Link>.
      </p>
    </>
  );
}
