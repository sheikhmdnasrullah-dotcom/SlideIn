import Link from "next/link";

import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { STAGE_ORDER, STAGE_LABELS, SECTIONS } from "@/lib/workflow/metadata";

export default function HelpPage() {
  return (
    <>
      <PageHeader title="Workflow" />

      <Section title="Stages">
        <Surface variant="raised" className="px-6 py-4">
          <ol className="space-y-3">
            {STAGE_ORDER.map((stage, index) => {
              const section = SECTIONS.find((item) => item.stage === stage);
              return (
                <li key={stage} className="flex gap-3">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-flame-wash font-value text-xs text-flame">
                    {index + 1}
                  </span>
                  <span>
                    <strong className="text-ink-strong">{STAGE_LABELS[stage] ?? stage}</strong>
                    {section ? (
                      <span className="block text-2xs text-ink-muted">{section.description}</span>
                    ) : null}
                  </span>
                </li>
              );
            })}
          </ol>
        </Surface>
      </Section>

      <Section title="Reference">
        <Surface variant="raised" className="divide-y divide-rule">
          <Link href="/contracts" className="flex items-center justify-between px-6 py-3.5 hover:bg-surface-2 focus-ring">
            <span className="text-sm text-ink-strong">Stage contracts</span>
          </Link>
          <Link href="/settings" className="flex items-center justify-between px-6 py-3.5 hover:bg-surface-2 focus-ring">
            <span className="text-sm text-ink-strong">Workspace settings</span>
          </Link>
        </Surface>
      </Section>
    </>
  );
}
