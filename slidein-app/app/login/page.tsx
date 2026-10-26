import { redirect } from "next/navigation";

import { LoginForm } from "./login-form";
import { WorkspaceMismatch } from "@/components/workspace/workspace-mismatch";
import { GlossTile } from "@/components/system/gloss-tile";
import { API_BASE_URL, WORKSPACE_ID } from "@/lib/api/config";
import { dashboardUrl, getSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

interface AuthState {
  bootstrap_available: boolean;
}

async function authState(): Promise<AuthState> {
  try {
    const response = await fetch(`${API_BASE_URL}/v1/auth/state`, { cache: "no-store" });
    if (response.ok) {
      const payload = (await response.json()) as Partial<AuthState>;
      return { bootstrap_available: payload.bootstrap_available === true };
    }
  } catch {
    // The API being down must not break the sign-in screen: it still
    // renders, and the submit action reports the outage verbatim.
  }
  return { bootstrap_available: false };
}

function safeNext(value: string | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/overview";
  return value;
}

/**
 * The shared entry point. An already-signed-in visitor is routed to the
 * interface their role actually opens; everyone else sees the form.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const params = await searchParams;
  const next = safeNext(params.next);
  const session = await getSession();

  if (session && session.tenant_id === WORKSPACE_ID) {
    if (session.interfaces.includes("console")) redirect(next);
    redirect(dashboardUrl("/dashboard"));
  }

  const state = await authState();

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-8 bg-background px-5 py-10">
      {session ? (
        <WorkspaceMismatch sessionTenant={session.tenant_id} workspaceId={WORKSPACE_ID} />
      ) : (
        <div className="flex w-full max-w-[420px] flex-col items-stretch gap-7">
          <div className="flex flex-col items-center gap-3 text-center">
            <GlossTile size={44}>
              <span className="font-sans text-[15px] font-semibold text-ink-strong">SL</span>
            </GlossTile>
            <div className="flex flex-col gap-1">
              <h1 className="font-display text-[26px] leading-[32px] text-ink-strong">
                {state.bootstrap_available ? "Set up your workspace" : "Sign in to Slidein"}
              </h1>
              <p className="font-sans text-sm text-ink-muted">
                {state.bootstrap_available
                  ? "This workspace has no accounts yet. Create the owner login — it opens both Console and Dashboard."
                  : "Console and Dashboard share one account."}
              </p>
            </div>
          </div>

          <div className="rounded-2xl border border-rule bg-surface p-7 shadow-raised">
            <LoginForm
              mode={state.bootstrap_available ? "bootstrap" : "login"}
              next={next}
              workspaceId={WORKSPACE_ID}
            />
          </div>

          <p className="text-center font-sans text-xs text-ink-faint">
            Operators and admins use Console. Clients only need Dashboard — same
            login, different view.
          </p>
        </div>
      )}
    </main>
  );
}
