"use client";

/**
 * AutopilotCard: the workspace's window into the autonomous agent loop.
 * The loop itself runs in the API's background task — this card only shows
 * its state (last tick, totals, pipeline) and lets a human flip the
 * per-workspace switches or force an immediate tick.
 */

import * as React from "react";

import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/system/status-badge";
import { Surface } from "@/components/system/surface";
import { runAutopilotNowAction, toggleAutopilotAction } from "@/lib/api/actions";
import type { ActionResult } from "@/lib/api/actions";
import type { AutopilotStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const IDLE: ActionResult = { ok: true, message: "" };

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

function SwitchRow({
  name,
  label,
  detail,
  value,
  pending,
  action,
}: {
  name: "enabled" | "auto_approve" | "send_enabled";
  label: string;
  detail: string;
  value: boolean;
  pending: boolean;
  action: (formData: FormData) => void;
}) {
  return (
    <form
      action={action}
      className="flex items-center gap-3 border-b border-rule px-5 py-2.5 last:border-b-0"
    >
      <input type="hidden" name="switch" value={name} />
      <input type="hidden" name="value" value={value ? "false" : "true"} />
      <span className="min-w-0 grow">
        <span className="block text-sm font-medium text-ink-strong">{label}</span>
        <span className="block text-2xs text-ink-muted">{detail}</span>
      </span>
      <StatusBadge tone={value ? "live" : "neutral"} label={value ? "on" : "off"} />
      <Button type="submit" variant="outline" size="sm" disabled={pending}>
        {value ? "Turn off" : "Turn on"}
      </Button>
    </form>
  );
}

function StatRow({ stats }: { stats: Record<string, number> }) {
  const interesting = ["ingested", "researched", "qualified", "drafts", "approved", "sent"];
  const entries = interesting.filter((key) => (stats[key] ?? 0) > 0);
  if (entries.length === 0) {
    return <span className="text-2xs text-ink-muted">No work done on the last tick.</span>;
  }
  return (
    <span className="flex flex-wrap gap-x-4 gap-y-1">
      {entries.map((key) => (
        <span key={key} className="flex items-baseline gap-1.5 text-2xs">
          <span className="text-ink-muted">{key}</span>
          <span className="font-value tabular-nums text-ink-strong">{stats[key]}</span>
        </span>
      ))}
    </span>
  );
}

export function AutopilotCard({ status }: { status: AutopilotStatus }) {
  const [pending, startTransition] = React.useTransition();
  const [result, setResult] = React.useState<ActionResult>(IDLE);

  const onToggle = (formData: FormData) => {
    startTransition(async () => {
      setResult(await toggleAutopilotAction(IDLE, formData));
    });
  };
  const onRunNow = () => {
    startTransition(async () => {
      setResult(await runAutopilotNowAction());
    });
  };

  const live = status.enabled && status.master_enabled;
  const totals = status.totals;

  return (
    <Surface variant="raised">
      <div className="flex flex-wrap items-center gap-3 border-b border-rule px-5 py-3">
        <StatusBadge
          tone={status.master_enabled ? (live ? "live" : "neutral") : "danger"}
          label={status.master_enabled ? (live ? "running" : "paused") : "disabled"}
        />
        <span className="min-w-0 grow">
          <span className="block text-sm font-medium text-ink-strong">Autopilot</span>
          <span className="block text-2xs text-ink-muted">
            {status.master_enabled
              ? `Ticks every ${Math.round(status.interval_seconds / 60)}m · researches, drafts and ${status.send_enabled ? "sends" : "parks"} via ${status.transport}`
              : "The master switch (SLIDEIN_AUTOPILOT) is off in the API environment."}
          </span>
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onRunNow}
          disabled={pending || !status.master_enabled}
        >
          Run a tick now
        </Button>
      </div>

      <SwitchRow
        name="enabled"
        label="Workspace autopilot"
        detail="Advance this workspace's pipeline on every background tick."
        value={status.enabled}
        pending={pending}
        action={onToggle}
      />
      <SwitchRow
        name="auto_approve"
        label="Auto-approve drafts"
        detail="Approve drafts the moment personalization finishes."
        value={status.auto_approve}
        pending={pending}
        action={onToggle}
      />
      <SwitchRow
        name="send_enabled"
        label="Send approved drafts"
        detail={`Dispatch through ${status.transport}. Suppression, approval policy and rate limits always apply.`}
        value={status.send_enabled}
        pending={pending}
        action={onToggle}
      />

      <div className="flex flex-col gap-2 px-5 py-3">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-2xs">
          <span className="text-ink-muted">last tick</span>
          <span className="font-value tabular-nums text-ink-strong">
            {status.last_tick_at
              ? new Date(status.last_tick_at).toLocaleString()
              : "never"}
          </span>
          {status.last_status && status.last_status !== "never_run" && (
            <StatusBadge
              tone={status.last_status === "ok" ? "live" : "danger"}
              label={status.last_status}
            />
          )}
          <span className="ml-auto flex gap-4">
            <span className="flex items-baseline gap-1.5">
              <span className="text-ink-muted">in campaign</span>
              <span className="font-value tabular-nums text-ink-strong">
                {status.pipeline.in_campaign ?? 0}
              </span>
            </span>
            <span className="flex items-baseline gap-1.5">
              <span className="text-ink-muted">replied</span>
              <span className="font-value tabular-nums text-ink-strong">
                {status.pipeline.replied ?? 0}
              </span>
            </span>
            <span className="flex items-baseline gap-1.5">
              <span className="text-ink-muted">open conversations</span>
              <span className="font-value tabular-nums text-ink-strong">
                {status.open_conversations}
              </span>
            </span>
          </span>
        </div>
        <StatRow stats={status.last_stats} />
        {Object.keys(totals).length > 0 && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-2xs">
            <span className="text-ink-faint">totals</span>
            {Object.entries(totals)
              .filter(([, count]) => count > 0)
              .map(([key, count]) => (
                <span key={key} className="flex items-baseline gap-1.5">
                  <span className="text-ink-muted">{key}</span>
                  <span className="font-value tabular-nums text-ink-strong">{count}</span>
                </span>
              ))}
          </div>
        )}
        {status.last_error && (
          <p className="text-2xs leading-relaxed text-status-danger">{status.last_error}</p>
        )}
        <ResultLine result={result} />
      </div>
    </Surface>
  );
}
