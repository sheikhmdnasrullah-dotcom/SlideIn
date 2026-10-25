"use client";

/**
 * OsintConsole: ad-hoc research against the OpenOSINT adapter. The form
 * posts to a server action; lookup findings and Google dork links render
 * inline from the returned payload — nothing is filed to a prospect.
 */

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input } from "@/components/ui/form";
import { StatusBadge } from "@/components/system/status-badge";
import { Surface } from "@/components/system/surface";
import { runOsintResearchAction, type OsintResearchActionResult } from "@/lib/api/actions";
import type { OsintHealth, OsintResearchResult } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const IDLE: OsintResearchActionResult = { ok: true, message: "" };

function ResultLine({ result }: { result: OsintResearchActionResult }) {
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

function LookupRow({ row }: { row: OsintResearchResult["lookups"][number] }) {
  return (
    <li className="flex flex-col gap-1.5 py-2.5">
      <div className="flex flex-wrap items-baseline gap-2">
        <StatusBadge tone={row.ok ? "live" : "danger"} label={row.lookup} />
        <code className="font-code text-2xs text-ink-muted">{row.target || "—"}</code>
        <span className="ml-auto text-2xs tabular-nums text-ink-faint">
          {(row.duration_ms / 1000).toFixed(1)}s
        </span>
      </div>
      {row.error && (
        <p className="text-2xs leading-relaxed text-status-danger">{row.error}</p>
      )}
      {row.lines.length > 0 && (
        <ul className="flex flex-col gap-0.5 rounded-xs bg-surface-2 px-3 py-2">
          {row.lines.map((line, index) => (
            <li key={index} className="font-code text-2xs leading-relaxed break-words text-ink-muted">
              {line}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function DorkGrid({ dorks }: { dorks: OsintResearchResult["dorks"] }) {
  if (dorks.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      <h3 className="font-label text-ink-muted">Search everywhere else</h3>
      <div className="flex flex-wrap gap-2">
        {dorks.map((dork) => (
          <a
            key={dork.url}
            href={dork.url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-pill border-rule px-3 py-1 text-2xs text-ink-muted hover:border-rule-strong hover:text-ink-strong focus-ring"
          >
            {dork.label}
          </a>
        ))}
      </div>
    </div>
  );
}

export function OsintConsole({ health }: { health: OsintHealth }) {
  const [result, formAction, pending] = React.useActionState(runOsintResearchAction, IDLE);
  const data = result.data;
  const connected = health.status === "connected";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={connected ? "live" : "danger"} label={`CLI ${health.status}`} />
        <code className="font-code text-2xs break-all text-ink-faint">{health.detail}</code>
      </div>

      <form action={formAction} className="flex flex-col gap-5">
        <Field
          label="Query"
          hint="Auto-detected: full name → GitHub search + platform dorks; email/handle/domain → matching lookups."
        >
          <Input
            name="query"
            required
            autoFocus
            placeholder="Sanjida Nasrin Efa · jane@acme.example · acme.com · @handle"
          />
        </Field>

        <div className="flex flex-wrap gap-x-5 gap-y-2">
          {health.lookups.map((lookup) => (
            <Checkbox
              key={lookup.name}
              name="lookups"
              value={lookup.name}
              label={
                <span className="inline-flex items-baseline gap-1.5">
                  {lookup.name}
                  {lookup.active && (
                    <span className="text-2xs text-status-warn">active</span>
                  )}
                </span>
              }
            />
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <Checkbox
            name="allow_active"
            label="Allow active lookups (email/username enumeration — noisy)"
          />
          <Button type="submit" disabled={pending} size="sm">
            {pending ? "Researching…" : "Run research"}
          </Button>
        </div>

        <ResultLine result={result} />
      </form>

      {data && (
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-baseline gap-2 border-t border-rule pt-4">
            <span className="font-label text-ink-muted">Results</span>
            <code className="font-code text-2xs text-ink-faint">
              {data.query} → {data.target_type}
            </code>
          </div>

          {data.lookups.length === 0 ? (
            <p className="text-2xs text-ink-muted">No lookups ran for this query.</p>
          ) : (
            <Surface variant="raised" className="divide-y divide-rule px-4 py-1">
              <ul className="divide-y divide-rule">
                {data.lookups.map((row) => (
                  <LookupRow key={row.lookup} row={row} />
                ))}
              </ul>
            </Surface>
          )}

          <DorkGrid dorks={data.dorks} />
        </div>
      )}
    </div>
  );
}
