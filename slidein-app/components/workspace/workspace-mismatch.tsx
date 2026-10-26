import { logoutAction } from "@/lib/auth/actions";

/**
 * A session that belongs to a different workspace. Both interfaces render
 * this instead of pretending the data is missing — the account exists, it
 * just is not this tenant's.
 */
export function WorkspaceMismatch({
  sessionTenant,
  workspaceId,
}: {
  sessionTenant: string;
  workspaceId: string;
}) {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-background px-5">
      <div className="flex w-full max-w-[440px] flex-col gap-5 rounded-2xl border border-rule bg-surface p-8 shadow-raised">
        <span className="font-label text-ink-muted">Wrong workspace</span>
        <h1 className="font-display text-[24px] leading-[30px] text-ink-strong">
          This account is not part of this workspace
        </h1>
        <p className="font-sans text-sm leading-6 text-ink-muted">
          You are signed in as a member of <span className="font-code">{sessionTenant}</span>,
          but this console serves <span className="font-code">{workspaceId}</span>. Sign out
          and use the account that belongs here.
        </p>
        <form action={logoutAction}>
          <button
            type="submit"
            className="h-11 w-full rounded-pill bg-button-primary px-6 font-sans text-sm font-medium text-on-button-primary shadow-button transition-transform duration-[120ms] hover:-translate-y-px active:translate-y-0 focus-ring"
          >
            Sign out
          </button>
        </form>
      </div>
    </div>
  );
}
