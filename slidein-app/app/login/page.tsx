import { redirect } from "next/navigation";

import { LoginForm } from "./login-form";
import { WorkspaceMismatch } from "@/components/workspace/workspace-mismatch";
import { GlossTile } from "@/components/system/gloss-tile";
import { API_BASE_URL, WORKSPACE_ID } from "@/lib/api/config";
import { getSession } from "@/lib/auth/session";

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
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/overview";
}

/** Console sign-in and first-owner setup. */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const params = await searchParams;
  const next = safeNext(params.next);
  const session = await getSession();

  if (session && session.tenant_id === WORKSPACE_ID) {
    redirect(next);
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
                  ? "Create the owner account."
                  : "Sign in to your workspace."}
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

        </div>
      )}
    </main>
  );
}
