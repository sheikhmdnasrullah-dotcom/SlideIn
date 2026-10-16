import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { PageFailure } from "@/components/workspace/page-failure";
import { operations } from "@/lib/api/operations";

export const dynamic = "force-dynamic";

export default async function ContractsPage() {
  let catalog;
  try {
    catalog = await operations.contracts();
  } catch (error) {
    return <PageFailure error={error} module="overview" />;
  }

  return (
    <>
      <PageHeader
        eyebrow="Reference · stage contracts"
        title="Stage contracts"
        meta={`${catalog.stages.length} stages · ${catalog.handoffs.length} handoffs`}
      />

      <Section title="Stages" description="What each stage requires, produces, and how it can fail.">
        <div className="flex flex-col gap-3">
          {catalog.stages.map((stage) => (
            <Surface key={stage.stage} variant="raised" className="px-4 py-3">
              <h2 className="font-display-soft text-sm text-ink-strong">{stage.title}</h2>
              <p className="max-w-prose pt-1 text-2xs leading-relaxed text-ink-muted">{stage.summary}</p>
              <div className="grid gap-3 pt-3 sm:grid-cols-2">
                <div>
                  <h3 className="font-label pb-1 text-ink-faint">Requires</h3>
                  <ul className="flex flex-col gap-0.5">
                    {stage.requires.map((field) => (
                      <li key={field.name} className="text-2xs text-ink-muted">
                        <span className="font-mono text-ink-strong">{field.name}</span>
                        {field.required ? " · required" : ""} — {field.description}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h3 className="font-label pb-1 text-ink-faint">Produces</h3>
                  <ul className="flex flex-col gap-0.5">
                    {stage.produces.map((field) => (
                      <li key={field.name} className="text-2xs text-ink-muted">
                        <span className="font-mono text-ink-strong">{field.name}</span> — {field.description}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
              {stage.failures.length > 0 && (
                <div className="pt-2">
                  <h3 className="font-label pb-1 text-ink-faint">Failures</h3>
                  <ul className="flex flex-col gap-0.5">
                    {stage.failures.map((failure) => (
                      <li key={failure.code} className="text-2xs text-ink-muted">
                        <span className="font-mono text-ink-strong">{failure.code}</span>
                        {" "}→ {failure.recovery_action}
                        {failure.retryable ? " · retryable" : ""} — {failure.description}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Surface>
          ))}
        </div>
      </Section>

      <Section title="Handoffs" description="What each stage carries to the next, and what blocks it.">
        <Surface variant="inset" className="divide-y divide-rule px-4 py-1">
          {catalog.handoffs.map((handoff, index) => (
            <div key={index} className="py-2 text-2xs">
              <span className="text-ink-strong">
                {handoff.from} → {handoff.to}
              </span>
              <span className="block pt-0.5 text-ink-faint">
                carries: {handoff.carried.join(", ") || "—"} · blocked by: {handoff.blocked_by.join(", ") || "—"}
              </span>
            </div>
          ))}
        </Surface>
      </Section>
    </>
  );
}
