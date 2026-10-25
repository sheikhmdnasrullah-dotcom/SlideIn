"use client";

/**
 * Client setup screen: the one operation — context in, workspace out —
 * plus every exception that stands between "generated" and "active".
 *
 * The screen never hides a gap behind a green tick: each of the six stages
 * shows its own state, each blocker carries the API's remediation text, and
 * a capability the product does not have is listed as a proposed
 * enhancement rather than offered as a switch.
 */

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { Section } from "@/components/system/section";
import { StatusBadge } from "@/components/system/status-badge";
import { Surface } from "@/components/system/surface";
import {
  activateWorkspaceAction,
  probeConnectionAction,
  runSetupTestAction,
  setupAnswersAction,
  setupGenerateAction,
  type ActionResult,
  type SetupActionResult,
} from "@/lib/api/actions";
import type {
  SetupField,
  SetupQuestion,
  SetupStageKey,
  SetupStatus,
} from "@/lib/api/types";
import type { StatusTone } from "@/lib/workflow/metadata";
import { cn } from "@/lib/utils";

const IDLE: SetupActionResult = { ok: true, message: "" };

const GROUP_ORDER = ["business", "legal", "sending", "approvals", "integrations"];

const GROUP_LABELS: Record<string, string> = {
  business: "Business",
  legal: "Legal",
  sending: "Sending",
  approvals: "Approvals",
  integrations: "Integrations",
};

const STAGE_TONE: Record<SetupStageKey, StatusTone> = {
  workspace_generated: "info",
  configuration_validated: "info",
  integrations_connected: "info",
  workflow_tested: "info",
  ready_for_approval: "warn",
  active: "live",
};

function fieldTone(status: SetupField["status"]): StatusTone {
  if (status === "confirmed") return "live";
  if (status === "assumption") return "warn";
  return "neutral";
}

function questionTone(question: SetupQuestion): StatusTone {
  if (question.status === "answered") return "live";
  if (question.status === "prefilled") return "warn";
  return question.blocking ? "danger" : "neutral";
}

function ResultLine({ result }: { result: ActionResult }) {
  if (!result.message) return null;
  return (
    <p
      role={result.ok ? "status" : "alert"}
      className={cn(
        "text-2xs leading-relaxed",
        result.ok ? "text-status-live" : "text-status-danger",
      )}
    >
      {result.message}
    </p>
  );
}

/** Local empty state: `states.tsx` pulls in server-only config, so a client
 * screen states its own emptiness in the same words. */
function SetupEmpty({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 px-4 py-10 text-center">
      <span className="font-sans text-sm font-semibold text-ink-strong">{title}</span>
      <p className="max-w-[420px] font-sans text-xs leading-[18px] text-ink-muted">
        {description}
      </p>
    </div>
  );
}

function isLongField(key: string): boolean {
  return [
    "business_description",
    "core_value_prop",
    "ideal_customer_profile",
    "products_services",
    "qualification_rules",
    "exclusion_rules",
  ].includes(key);
}

// ── 1. progress ─────────────────────────────────────────────────────────────

function ProgressPanel({ status }: { status: SetupStatus }) {
  const active = status.state === "active";
  return (
    <Section
      eyebrow="Setup progress"
      title={active ? "Workspace active" : status.next_action.label}
      description="Six stages, in order. Generated never means active: each stage reports its own state."
      meta={`attempt ${status.attempt}${status.generated_at ? ` · ${status.generated_at.slice(0, 10)}` : " · not generated"}`}
      tone="raised"
      divided
      bodyClassName="px-6 py-4"
    >
      <ol className="flex flex-col gap-2.5">
        {status.checklist.map((item) => (
          <li key={item.key} className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2.5">
              <StatusBadge
                tone={item.done ? "live" : item.status === "current" ? STAGE_TONE[item.key] : "neutral"}
                label={item.status === "current" ? "in progress" : item.done ? "done" : "pending"}
              />
              <span className="text-[13px] font-medium text-ink-strong">{item.label}</span>
            </div>
            <p className="pl-1 text-2xs leading-relaxed text-ink-muted">{item.detail}</p>
          </li>
        ))}
      </ol>
    </Section>
  );
}

// ── 2. context in ───────────────────────────────────────────────────────────

function ContextForm() {
  const [result, formAction, pending] = React.useActionState(
    setupGenerateAction,
    IDLE,
  );
  return (
    <form action={formAction} className="flex flex-col gap-5">
      <Field
        label="What the client gave you"
        hint="Notes, a brief, a call transcript, requirements — paste them as they are. Nothing is invented from what is not here."
      >
        <Textarea
          name="context"
          rows={7}
          placeholder={"Acme Mortgage Partners helps London renters become first-time buyers…"}
        />
      </Field>
      <Field
        label="Website (optional)"
        hint="Read server-side for positioning and headings. Only a public http(s) address is accepted."
      >
        <Input name="website" type="url" placeholder="https://example.com" />
      </Field>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={pending} size="sm">
          {pending ? "Generating…" : "Generate setup"}
        </Button>
        <ResultLine result={result} />
      </div>
    </form>
  );
}

function SourcesPanel({ status }: { status: SetupStatus }) {
  if (status.sources.length === 0 && status.rejected_sources.length === 0) {
    return (
      <SetupEmpty
        title="No context yet"
        description="Paste what the client gave you above. Extraction is deterministic: the same input always produces the same profile."
        />
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col divide-y divide-rule rounded-md border border-rule">
        {status.sources.map((source) => (
          <div key={source.id} className="flex flex-wrap items-center gap-3 px-3 py-2">
            <StatusBadge
              tone={
                source.status === "ready"
                  ? "live"
                  : source.status === "truncated"
                    ? "warn"
                    : "danger"
              }
              label={source.status}
            />
            <span className="text-2xs font-medium text-ink-strong">{source.label}</span>
            <span className="text-2xs text-ink-muted">
              {source.type} · {source.char_count.toLocaleString()} chars
            </span>
            {source.error && <span className="text-2xs text-status-danger">{source.error}</span>}
          </div>
        ))}
      </div>
      {status.rejected_sources.length > 0 && (
        <div className="flex flex-col gap-1">
          {status.rejected_sources.map((item) => (
            <p key={item.source} className="text-2xs text-status-danger">
              {item.source}: {item.error}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

// ── 3. what was read ────────────────────────────────────────────────────────

function ExtractedProfile({
  fields,
  conflicts,
  counts,
}: {
  fields: Record<string, SetupField> | null;
  conflicts: SetupStatus["conflicts"];
  counts: Record<string, number>;
}) {
  const filled = Object.values(fields ?? {}).filter((field) => field.value);
  if (filled.length === 0) return null;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-2xs text-ink-muted">
        <span>{counts.confirmed ?? 0} confirmed</span>
        <span>{counts.assumption ?? 0} assumed — confirm before activation</span>
        <span>{counts.unknown ?? 0} not stated</span>
      </div>
      <div className="flex flex-col divide-y divide-rule rounded-md border border-rule">
        {filled.map((field) => (
          <div key={field.key} className="flex flex-col gap-1 px-3 py-2">
            <div className="flex flex-wrap items-center gap-2.5">
              <StatusBadge tone={fieldTone(field.status)} label={field.status} />
              <span className="text-2xs font-medium text-ink-strong">{field.label}</span>
            </div>
            <p className="text-2xs leading-relaxed text-ink-strong">{field.value}</p>
            <p className="text-2xs leading-relaxed text-ink-muted">{field.basis}</p>
          </div>
        ))}
      </div>
      {conflicts.length > 0 && (
        <div className="flex flex-col gap-2">
          {conflicts.map((conflict) => (
            <div
              key={conflict.key}
              className="rounded-md border border-rule bg-status-warn-bg px-3 py-2"
            >
              <div className="flex flex-wrap items-center gap-2.5">
                <StatusBadge tone="warn" label="conflict" />
                <span className="text-2xs font-medium text-ink-strong">{conflict.label}</span>
              </div>
              <ul className="mt-1 flex flex-col gap-0.5">
                {conflict.values.map((value) => (
                  <li key={`${value.source}-${value.value}`} className="text-2xs text-ink-muted">
                    “{value.value}” — {value.source}
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-2xs text-ink-muted">
                Chosen: “{conflict.chosen}” ({conflict.chosen_from}). Resolve in the questions below.
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── 4. the decisions a human must make ──────────────────────────────────────

function QuestionsForm({ questions }: { questions: SetupQuestion[] }) {
  const [result, formAction, pending] = React.useActionState(
    setupAnswersAction,
    IDLE,
  );
  const groups = GROUP_ORDER.filter((group) =>
    questions.some((question) => question.group === group),
  );
  const extras = questions.filter((question) => !GROUP_ORDER.includes(question.group));
  const ordered = [
    ...groups.map((group) => ({
      group,
      items: questions.filter((question) => question.group === group),
    })),
    ...(extras.length > 0 ? [{ group: "other", items: extras }] : []),
  ];

  if (questions.length === 0) {
    return (
      <SetupEmpty
        title="Nothing to decide"
        description="Every question for this workspace is answered."
        />
    );
  }

  return (
    <form action={formAction} className="flex flex-col gap-6">
      {ordered.map((group) => (
        <div key={group.group} className="flex flex-col gap-3">
          <h3 className="font-label text-ink-muted">
            {GROUP_LABELS[group.group] ?? group.group}
          </h3>
          {group.items.map((question) => (
            <div key={question.key} className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2.5">
                <StatusBadge tone={questionTone(question)} label={question.status} />
                <span className="text-[13px] font-medium text-ink-strong">
                  {question.prompt}
                </span>
                {question.unblocks && (
                  <span className="text-2xs text-ink-muted">unblocks {question.unblocks}</span>
                )}
              </div>
              <p className="max-w-prose text-2xs leading-relaxed text-ink-muted">
                {question.help}
              </p>
              {question.kind === "choice" ? (
                <Select
                  name={`answer:${question.key}`}
                  aria-label={question.prompt}
                  defaultValue={question.value || question.default}
                  className="max-w-md"
                >
                  {question.options.length > 0 &&
                    !question.options.includes(question.value || question.default) && (
                      <option value={question.value || question.default}>
                        {question.value || question.default}
                      </option>
                    )}
                  {question.options.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </Select>
              ) : isLongField(question.key) ? (
                <Textarea
                  name={`answer:${question.key}`}
                  aria-label={question.prompt}
                  rows={2}
                  required={question.blocking}
                  defaultValue={question.value || question.default}
                />
              ) : (
                <Input
                  name={`answer:${question.key}`}
                  aria-label={question.prompt}
                  required={question.blocking}
                  defaultValue={question.value || question.default}
                  placeholder={question.default || question.value || ""}
                />
              )}
              {question.default && question.status !== "answered" && (
                <p className="text-2xs text-ink-muted">Proposed default: {question.default}</p>
              )}
            </div>
          ))}
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={pending} size="sm">
          {pending ? "Saving…" : "Save answers"}
        </Button>
        <ResultLine result={result} />
      </div>
    </form>
  );
}

// ── 5. exceptions ───────────────────────────────────────────────────────────

function ExceptionsPanel({ status }: { status: SetupStatus }) {
  const stages = status.validation.stages.filter(
    (stage) => stage.required && stage.status !== "pass",
  );
  const enhancements = status.proposed_enhancements;
  if (status.blockers.length === 0 && stages.length === 0 && enhancements.length === 0) {
    return (
      <SetupEmpty
        title="No exceptions"
        description="Nothing is blocking this setup."
        />
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {status.blockers.length > 0 && (
        <div className="flex flex-col divide-y divide-rule rounded-md border border-rule">
          {status.blockers.map((blocker) => (
            <div key={`${blocker.kind}:${blocker.id}`} className="flex flex-col gap-1 px-3 py-2.5">
              <div className="flex flex-wrap items-center gap-2.5">
                <StatusBadge
                  tone={blocker.human_action ? "warn" : "danger"}
                  label={blocker.kind.replace(/_/g, " ")}
                />
                <span className="text-2xs font-medium text-ink-strong">{blocker.title}</span>
              </div>
              {blocker.detail && (
                <p className="text-2xs leading-relaxed text-ink-muted">{blocker.detail}</p>
              )}
              {blocker.remediation && (
                <p className="text-2xs leading-relaxed text-ink-faint">
                  Fix: {blocker.remediation}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {stages.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <h3 className="font-label text-ink-muted">Required checks not passing</h3>
          {stages.map((stage) => (
            <div key={stage.key} className="flex flex-wrap items-baseline gap-2.5 text-2xs">
              <StatusBadge tone="danger" label={stage.status} />
              <span className="text-ink-strong">{stage.title}</span>
              <span className="text-ink-muted">{stage.message}</span>
            </div>
          ))}
        </div>
      )}

      {enhancements.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="font-label text-ink-muted">Requested but not built</h3>
          {enhancements.map((item) => (
            <div
              key={item.capability}
              className="rounded-md border border-rule bg-surface-2 px-3 py-2"
            >
              <div className="flex flex-wrap items-center gap-2.5">
                <StatusBadge tone="neutral" label="proposed" />
                <span className="text-2xs font-medium text-ink-strong">{item.capability}</span>
              </div>
              <p className="mt-0.5 text-2xs leading-relaxed text-ink-muted">{item.reason}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── 6. connect, test, activate ──────────────────────────────────────────────

function IntegrationPanel({ status }: { status: SetupStatus }) {
  const [pending, startTransition] = React.useTransition();
  const [message, setMessage] = React.useState<ActionResult>(IDLE);
  const integrations = status.blueprint?.required_integrations ?? [];

  const probe = (connectionId: string) => {
    startTransition(async () => setMessage(await probeConnectionAction(connectionId)));
  };

  if (integrations.length === 0) {
    return (
      <SetupEmpty
        title="No integrations required"
        description="The proposed scope does not call for an external system yet."
        />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col divide-y divide-rule rounded-md border border-rule">
        {integrations.map((item) => (
          <div key={item.id} className="flex flex-col gap-1 px-3 py-2.5">
            <div className="flex flex-wrap items-center gap-2.5">
              <StatusBadge
                tone={
                  item.required
                    ? status.connection_state[item.id] === "connected" ||
                      status.connection_state[item.id] === "builtin" ||
                      status.connection_state[item.id] === "not_required"
                      ? "live"
                      : "warn"
                    : "neutral"
                }
                label={
                  item.required
                    ? (status.connection_state[item.id] ?? "missing")
                    : "optional"
                }
              />
              <span className="text-2xs font-medium text-ink-strong">{item.label}</span>
            </div>
            <p className="text-2xs leading-relaxed text-ink-muted">{item.reason}</p>
            {item.secret_ref && (
              <p className="font-code text-2xs text-ink-faint">
                secret: {item.secret_ref} (server-side only)
              </p>
            )}
          </div>
        ))}
      </div>

      {status.connections.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="font-label text-ink-muted">Registered connections</h3>
          {status.connections.map((connection) => (
            <div
              key={connection.id}
              className="flex flex-wrap items-center gap-3 rounded-md border border-rule px-3 py-2"
            >
              <StatusBadge
                tone={
                  connection.status === "connected"
                    ? "live"
                    : connection.status === "failing"
                      ? "danger"
                      : "warn"
                }
                label={connection.status}
              />
              <span className="text-2xs font-medium text-ink-strong">{connection.label}</span>
              <span className="text-2xs text-ink-muted">{connection.provider}</span>
              {connection.last_error && (
                <span className="text-2xs text-status-danger">{connection.last_error}</span>
              )}
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={pending}
                onClick={() => probe(connection.id)}
              >
                {pending ? "Probing…" : "Probe"}
              </Button>
            </div>
          ))}
        </div>
      )}
      <ResultLine result={message} />
    </div>
  );
}

function TestActivatePanel({ status }: { status: SetupStatus }) {
  const [pending, startTransition] = React.useTransition();
  const [message, setMessage] = React.useState<ActionResult>(IDLE);
  const tested = status.states.workflow_tested;
  const active = status.states.active;

  const run = (invoke: () => Promise<ActionResult>) =>
    startTransition(async () => setMessage(await invoke()));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge tone={tested ? "live" : "warn"} label={tested ? "passed" : "not run"} />
          <span className="text-2xs text-ink-muted">
            {status.activation.last_test
              ? `Last test: ${status.activation.last_test.mode} on config v${status.activation.last_test.config_version}`
              : "A controlled test runs the workflow end to end and sends nothing to a real mailbox."}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={pending}
            onClick={() => run(() => runSetupTestAction())}
          >
            {pending ? "Running…" : "Run controlled test"}
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={pending || active}
            onClick={() => run(() => activateWorkspaceAction())}
          >
            {active ? "Activated" : "Activate workspace"}
          </Button>
        </div>
        <ResultLine result={message} />
        <p className="text-2xs leading-relaxed text-ink-muted">
          Activation needs every required stage to pass, including an explicit postal
          address, sender, lawful basis and approver. Approval stays on until you turn
          it off.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <h3 className="font-label text-ink-muted">Validation stages</h3>
        {status.validation.stages.map((stage) => (
          <div key={stage.key} className="flex flex-wrap items-baseline gap-2.5 text-2xs">
            <StatusBadge
              tone={
                stage.status === "pass"
                  ? "live"
                  : stage.status === "fail"
                    ? stage.required
                      ? "danger"
                      : "warn"
                    : "neutral"
              }
              label={stage.status}
              title={stage.message}
            />
            <span className="text-ink-strong">{stage.title}</span>
            <span className="text-ink-muted">{stage.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── screen ──────────────────────────────────────────────────────────────────

export function SetupScreen({ status }: { status: SetupStatus }) {
  const hasProfile = Boolean(status.profile && Object.keys(status.profile).length > 0);
  return (
    <>
      <ProgressPanel status={status} />

      <Section
        eyebrow="Step 1"
        title="Provide context"
        description="Notes, brief, transcript, website — whatever the client handed over. Extraction is deterministic and keeps the source of every value."
      >
        <Surface variant="raised" className="px-6 py-5">
          <ContextForm />
        </Surface>
        <Surface variant="raised" className="mt-4 px-6 py-4">
          <SourcesPanel status={status} />
        </Surface>
      </Section>

      <Section
        eyebrow="Step 2"
        title="Review what was read"
        description="Confirmed means a source stated it; assumed means it was read out of prose; unknown means nobody said it. Nothing here was invented."
        meta={status.generated_at ? `config v${status.config_version ?? "—"}` : "not generated"}
      >
        <Surface variant="raised" className="px-6 py-5">
          {hasProfile ? (
            <ExtractedProfile
              fields={status.profile}
              conflicts={status.conflicts}
              counts={status.counts}
            />
          ) : (
            <SetupEmpty
              title="Nothing generated yet"
              description="Provide context above to produce the profile, offers, ICP and workspace blueprint."
              />
          )}
        </Surface>
      </Section>

      <Section
        eyebrow="Step 3"
        title="Answer what only you can decide"
        description="Legal identity, who approves a send, and whether sending is live are never defaulted silently. Prefills are proposals — confirm or replace them."
        meta={`${status.open_blocking_questions.length} required open`}
      >
        <Surface variant="raised" className="px-6 py-5">
          <QuestionsForm questions={status.questions} />
        </Surface>
      </Section>

      <Section
        eyebrow="Step 4"
        title="Review exceptions"
        description="Every failed stage, every unanswered question, and every capability this build does not have — surfaced, never hidden."
        meta={`${status.blockers.length} blocker(s)`}
      >
        <Surface variant="raised" className="px-6 py-5">
          <ExceptionsPanel status={status} />
        </Surface>
      </Section>

      <Section
        eyebrow="Step 5"
        title="Connect tools"
        description="Credentials live in the server secret store; only their references are shown here. Probes never send mail."
        meta={`${(status.blueprint?.required_integrations ?? []).length} required`}
      >
        <Surface variant="raised" className="px-6 py-5">
          <IntegrationPanel status={status} />
        </Surface>
      </Section>

      <Section
        eyebrow="Step 6"
        title="Test, then activate"
        description="A controlled test proves the workflow end to end. Activation is the last step and only succeeds when every required stage passes."
        meta={status.states.active ? "active" : "not active"}
      >
        <Surface variant="raised" className="px-6 py-5">
          <TestActivatePanel status={status} />
        </Surface>
      </Section>
    </>
  );
}
