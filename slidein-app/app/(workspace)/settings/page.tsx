import Link from "next/link";

import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { EmptyState } from "@/components/system/states";
import { AutopilotCard } from "@/components/workspace/autopilot-card";
import { ConsoleSectionsEditor } from "@/components/workspace/console-sections-editor";
import { WebsiteConnections } from "@/components/workspace/website-connections";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";
import { requireConsoleSession } from "@/lib/auth/session";
import type { ConsoleSectionMeta } from "@/lib/api/types";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  await requireConsoleSession();

  let autopilot;
  let consoleSections: ConsoleSectionMeta[] = [];
  try {
    [autopilot, consoleSections] = await Promise.all([
      operations.autopilot(WORKSPACE_ID),
      operations.consoleSections(WORKSPACE_ID).then((result) => result.sections),
    ]);
  } catch {
    // Optional services must not block workspace settings.
  }

  return (
    <>
      <PageHeader
        eyebrow="Workspace · settings"
        title="Settings"
      />

      {autopilot ? (
        <Section
          title="Automation"
          description="The background agent loop: ingest, research, qualify, draft, approve, send."
        >
          <AutopilotCard status={autopilot} />
        </Section>
      ) : (
        <Section title="Automation">
          <Surface variant="raised">
            <EmptyState
              icon="inbox"
              title="Automation unavailable"
              description="The autopilot service is not responding. Retry or check the API status."
            />
          </Surface>
        </Section>
      )}

      <Section
        title="Website lead capture"
        description="Connect a client-owned website, install its snippet, and turn consented form submissions into ordinary prospects."
      >
        <WebsiteConnections />
      </Section>

      {consoleSections.length > 0 ? (
        <Section title="Sections">
          <ConsoleSectionsEditor initialSections={consoleSections} />
        </Section>
      ) : null}

      <Section title="Workspace">
        <Surface variant="raised" className="divide-y divide-rule">
          <Link
            href="/profile"
            className="flex items-center gap-3 px-6 py-3.5 transition-colors hover:bg-surface-2 focus-ring"
          >
            <span>Business Profile</span>
          </Link>
          <Link
            href="/setup"
            className="flex items-center gap-3 px-6 py-3.5 transition-colors hover:bg-surface-2 focus-ring"
          >
            <span>Client Setup</span>
          </Link>
          <Link
            href="/contracts"
            className="flex items-center gap-3 px-6 py-3.5 transition-colors hover:bg-surface-2 focus-ring"
          >
            <span>Stage Contracts</span>
          </Link>
        </Surface>
      </Section>
    </>
  );
}
