import { PageHeader } from "@/components/system/page-header";
import { PageFailure } from "@/components/workspace/page-failure";
import { SetupScreen } from "@/components/workspace/setup/setup-screen";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";

export const dynamic = "force-dynamic";

/**
 * Client setup: the one-shot onboarding flow.

 *   provide context -> generate setup -> review exceptions
 *   -> connect tools -> test -> activate
 *
 * The page renders the API's own status: six stages, each reporting its
 * real state, so a workspace is never presented as active before it is.
 */
export default async function SetupPage() {
  let status;
  try {
    status = await operations.setupStatus(WORKSPACE_ID);
  } catch (error) {
    return <PageFailure error={error} module="settings" />;
  }

  const meta = status.generated_at
    ? `${status.state.replace(/_/g, " ")} · attempt ${status.attempt} · ${
        status.open_blocking_questions.length
      } open`
    : "not generated";

  return (
    <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-6">
      <PageHeader
        eyebrow="Setup · one-shot onboarding"
        title="Client Setup"
        meta={meta}
      />
      <SetupScreen status={status} />
    </div>
  );
}
