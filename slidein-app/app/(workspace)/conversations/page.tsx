import Link from "next/link";

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
import type { Conversation } from "@/lib/api/types";
import {
  CONVERSATION_STATE_LABELS,
  CONVERSATION_STATE_TONES,
  REPLY_INTENT_LABELS,
  REPLY_INTENT_TONES,
} from "@/lib/workflow/metadata";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

const COLUMNS: Column<Conversation>[] = [
  {
    key: "subject",
    header: "Subject",
    render: (row) => (
      <span>
        <span className="block text-ink-strong">
          {row.requires_action && <span className="mr-1.5 inline-block size-1.5 rounded-full bg-status-warn align-middle" aria-label="needs action" />}
          {row.subject || "(no subject)"}
        </span>
        <span className="block text-2xs text-ink-faint">
          {row.last_message_at ? formatDate(row.last_message_at) : "no messages yet"}
        </span>
      </span>
    ),
  },
  {
    key: "intent",
    header: "Intent",
    render: (row) => (
      <StatusBadge
        tone={REPLY_INTENT_TONES[row.intent] ?? "neutral"}
        label={REPLY_INTENT_LABELS[row.intent] ?? row.intent}
        title={`${(row.intent_confidence * 100).toFixed(0)}% confidence`}
      />
    ),
  },
  {
    key: "state",
    header: "State",
    align: "right",
    render: (row) => (
      <StatusBadge
        tone={CONVERSATION_STATE_TONES[row.state] ?? "neutral"}
        label={CONVERSATION_STATE_LABELS[row.state] ?? row.state}
      />
    ),
  },
];

export default async function ConversationsPage({
  searchParams,
}: {
  searchParams: Promise<{ requires_action?: string }>;
}) {
  const params = await searchParams;
  const actionOnly = params.requires_action === "true";

  let conversations;
  try {
    conversations = await operations.conversations(
      WORKSPACE_ID,
      actionOnly ? { requires_action: true, limit: 100 } : { limit: 100 },
    );
  } catch (error) {
    return <PageFailure error={error} module="inbox" />;
  }

  return (
    <>
      <PageHeader
        eyebrow="Workflow · inbox"
        title="Conversations"
        meta={`${conversations.total} threads`}
      />

      <Section title="Inbox" description="Replies thread to their outbound message and classify by keyword intent.">
        <Surface variant="raised">
          <div className="flex flex-wrap items-center gap-1.5 border-b border-rule px-4 py-2.5">
            <Link
              href="/conversations"
              aria-current={!actionOnly || undefined}
              className={cn(
                "rounded-sm px-2 py-1 text-2xs transition-colors",
                !actionOnly
                  ? "bg-flame-wash text-flame ring-1 ring-flame-ring"
                  : "text-ink-muted hover:bg-surface-2 hover:text-ink-strong",
              )}
            >
              All
            </Link>
            <Link
              href="/conversations?requires_action=true"
              aria-current={actionOnly || undefined}
              className={cn(
                "rounded-sm px-2 py-1 text-2xs transition-colors",
                actionOnly
                  ? "bg-flame-wash text-flame ring-1 ring-flame-ring"
                  : "text-ink-muted hover:bg-surface-2 hover:text-ink-strong",
              )}
            >
              Needs action
            </Link>
          </div>
          <DataTable<Conversation>
            columns={COLUMNS}
            rows={conversations.data}
            keyOf={(row) => row.id}
            rowHref={(row) => `/conversations/${row.id}`}
            empty={
              <EmptyState
                title="No conversations"
                description="Replies to sent messages thread here automatically."
              />
            }
          />
        </Surface>
      </Section>
    </>
  );
}
