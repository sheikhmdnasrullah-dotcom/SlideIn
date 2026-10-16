import Link from "next/link";

import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { EmptyState } from "@/components/system/states";
import { StatusBadge } from "@/components/system/status-badge";
import { formatDate } from "@/components/system/format";
import { PageFailure } from "@/components/workspace/page-failure";
import { TriggerButton } from "@/components/workspace/action-forms";
import { closeConversationAction, reopenConversationAction } from "@/lib/api/actions";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import {
  CONVERSATION_STATE_LABELS,
  CONVERSATION_STATE_TONES,
  REPLY_INTENT_LABELS,
  REPLY_INTENT_TONES,
} from "@/lib/workflow/metadata";

export const dynamic = "force-dynamic";

export default async function ConversationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let detail;
  try {
    detail = await operations.conversation(WORKSPACE_ID, id);
  } catch (error) {
    return <PageFailure error={error} module="inbox" />;
  }
  const { conversation, prospect, replies, outbound } = detail;

  return (
    <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-6">
      <PageHeader
        eyebrow="Workflow · thread"
        title={conversation.subject || "(no subject)"}
        meta={prospect ? `${prospect.full_name || prospect.email} · ${prospect.company_name}` : undefined}
        actions={
          <StatusBadge
            tone={CONVERSATION_STATE_TONES[conversation.state] ?? "neutral"}
            label={CONVERSATION_STATE_LABELS[conversation.state] ?? conversation.state}
          />
        }
      />

      {prospect && (
        <p className="text-2xs text-ink-muted">
          Prospect record:{" "}
          <Link href={`/discovery/${prospect.id}`} className="underline underline-offset-2 hover:text-ink-strong">
            {prospect.full_name || prospect.email}
          </Link>
        </p>
      )}

      <Section title="Replies" meta={`${replies.length} messages`}>
        {replies.length === 0 ? (
          <Surface variant="raised">
            <EmptyState icon="inbox" title="No replies yet" description="Inbound replies to tracked sends will thread here." />
          </Surface>
        ) : (
          <div className="flex flex-col gap-3">
            {replies.map((reply) => (
              <Surface key={reply.id} variant="raised" className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-2 pb-2">
                  <span className="text-2xs text-ink-strong">{reply.sender_email}</span>
                  <span className="text-2xs text-ink-muted">{formatDate(reply.received_at)}</span>
                  <StatusBadge
                    tone={REPLY_INTENT_TONES[reply.intent] ?? "neutral"}
                    label={`${REPLY_INTENT_LABELS[reply.intent] ?? reply.intent} · ${(reply.intent_confidence * 100).toFixed(0)}%`}
                  />
                  {reply.requires_action && <StatusBadge tone="warn" label="Needs action" />}
                </div>
                {reply.subject && (
                  <p className="pb-1 text-[0.8125rem] font-medium text-ink-strong">{reply.subject}</p>
                )}
                <p className="max-w-prose whitespace-pre-wrap text-[0.8125rem] leading-relaxed text-ink-muted">
                  {reply.body}
                </p>
                {reply.recommended_action && (
                  <p className="pt-2 text-2xs text-ink-muted">Suggested: {reply.recommended_action}</p>
                )}
              </Surface>
            ))}
          </div>
        )}
      </Section>

      {outbound.length > 0 && (
        <Section title="Outbound" meta={`${outbound.length} sent`}>
          <Surface variant="inset" className="divide-y divide-rule px-4 py-1">
            {outbound.map((message) => (
              <div key={message.id} className="flex items-baseline justify-between gap-3 py-1.5 text-2xs">
                <span className="font-medium text-ink-strong">{message.recipient_email}</span>
                <span className="text-ink-muted">
                  {message.delivery_status} · {formatDate(message.queued_at)}
                </span>
              </div>
            ))}
          </Surface>
        </Section>
      )}

      <Section title="Thread state">
        <div className="flex flex-wrap gap-2">
          {conversation.state === "closed" ? (
            <TriggerButton invoke={reopenConversationAction} id={conversation.id} label="Reopen thread" />
          ) : (
            <TriggerButton invoke={closeConversationAction} id={conversation.id} label="Close thread" />
          )}
        </div>
      </Section>
    </div>
  );
}
