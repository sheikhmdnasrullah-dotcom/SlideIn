import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { OsintConsole } from "@/components/workspace/osint-console";
import { PageFailure } from "@/components/workspace/page-failure";
import { operations } from "@/lib/api/operations";

export const dynamic = "force-dynamic";

export default async function OsintPage() {
  let health;
  try {
    health = await operations.osintHealth();
  } catch (error) {
    return <PageFailure error={error} module="research" />;
  }

  return (
    <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-6">
      <PageHeader
        eyebrow="Workflow · OSINT"
        title="Research console"
        meta="OpenOSINT lookups against a name, email, handle, or domain. Nothing is filed to a prospect record — use Run OSINT on a prospect to persist evidence."
      />

      <Section title="Query" tone="raised">
        <OsintConsole health={health} />
      </Section>
    </div>
  );
}
