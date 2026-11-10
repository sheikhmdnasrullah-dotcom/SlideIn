"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Checkbox, Input } from "@/components/ui/form";
import { Surface } from "@/components/system/surface";
import { saveConsoleSectionsAction, type ActionResult } from "@/lib/api/actions";
import type { ConsoleSectionMeta } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const LABELS: Record<string, string> = {
  overview: "Overview",
  discovery: "Discovery",
  research: "Research",
  qualification: "Qualification",
  personalization: "Personalization",
  outreach: "Outreach",
  inbox: "Conversations",
  activity: "Activity",
  settings: "Settings",
};

const IDLE: ActionResult = { ok: true, message: "" };

export function ConsoleSectionsEditor({ initialSections }: { initialSections: ConsoleSectionMeta[] }) {
  const [sections, setSections] = React.useState(initialSections);
  const [result, formAction, pending] = React.useActionState(saveConsoleSectionsAction, IDLE);

  return (
    <form action={formAction}>
      <input type="hidden" name="sections" value={JSON.stringify(sections)} />
      <Surface variant="raised" className="divide-y divide-rule">
        {sections.map((section, index) => (
          <div key={section.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
            <span className="w-6 font-value text-xs text-ink-faint">{index + 1}</span>
            <Input
              aria-label={`${LABELS[section.id] ?? section.id} label`}
              value={section.label ?? LABELS[section.id] ?? section.id}
              onChange={(event) => setSections((current) => current.map(
                (item) => item.id === section.id ? { ...item, label: event.target.value } : item,
              ))}
              className="min-w-40 grow"
              maxLength={80}
              required
            />
            <Checkbox
              label="Visible"
              checked={section.visible}
              disabled={section.id === "settings"}
              onChange={(event) => setSections((current) => current.map(
                (item) => item.id === section.id
                  ? { ...item, visible: section.id === "settings" || event.target.checked }
                  : item,
              ))}
            />
          </div>
        ))}
      </Surface>
      <div className="mt-4 flex items-center gap-3">
        <Button type="submit" size="sm" disabled={pending}>Save layout</Button>
        {result.message ? (
          <p role={result.ok ? "status" : "alert"} className={cn(
            "text-2xs",
            result.ok ? "text-status-live" : "text-status-danger",
          )}>
            {result.message}
          </p>
        ) : null}
      </div>
    </form>
  );
}
