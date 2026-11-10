"use client";

import { useActionState, useState } from "react";
import { ArrowLeft, KeyRound, Loader2, ShieldCheck } from "lucide-react";

import {
  bootstrapAction,
  loginAction,
  changePasswordAction,
  type AuthFormState,
} from "@/lib/auth/actions";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { cn } from "@/lib/utils";

/**
 * The one sign-in screen both interfaces start from. The Console shows it
 * unbranded by tenant: branding only loads once a session exists, so the
 * screen states facts (workspace id) instead of guessing a brand.
 */
export function LoginForm({
  mode,
  next,
  workspaceId,
  className,
}: {
  mode: "login" | "bootstrap";
  next: string;
  workspaceId: string;
  className?: string;
}) {
  const action = mode === "bootstrap" ? bootstrapAction : loginAction;
  const [state, formAction, pending] = useActionState<AuthFormState | undefined, FormData>(
    action,
    undefined,
  );

  const [changeState, changeFormAction, changePending] = useActionState<
    AuthFormState | undefined,
    FormData
  >(changePasswordAction, undefined);

  const [cancelled, setCancelled] = useState(false);

  const mustChange =
    !cancelled &&
    (Boolean(state?.must_change_password) || Boolean(changeState?.must_change_password));
  const activeUsername = changeState?.username || state?.username || "";

  if (mustChange) {
    return (
      <form action={changeFormAction} className={cn("flex flex-col gap-5", className)}>
        <input type="hidden" name="next" value={next} />
        <input type="hidden" name="username" value={activeUsername} />

        <div className="rounded-lg border border-rule bg-surface-subtle p-3.5 flex flex-col gap-1.5">
          <div className="flex items-center gap-2 text-ink-strong font-medium text-sm">
            <ShieldCheck className="size-4 text-flame-vivid" aria-hidden />
            <span>Set your permanent password</span>
          </div>
          <p className="text-xs text-ink-muted">
            Account <strong className="font-code text-ink-strong">{activeUsername}</strong> was
            provisioned with an initial temporary password. Please create your permanent password to
            continue.
          </p>
        </div>

        <Field label="New password">
          <Input
            name="new_password"
            type="password"
            autoComplete="new-password"
            required
            minLength={6}
            placeholder="At least 6 characters"
          />
        </Field>

        <Field label="Confirm new password">
          <Input
            name="confirm_password"
            type="password"
            autoComplete="new-password"
            required
            minLength={6}
            placeholder="Re-enter your new password"
          />
        </Field>

        {changeState?.error && (
          <p
            role="alert"
            className="rounded-md border border-status-danger bg-status-danger-bg px-3 py-2 font-sans text-sm text-status-danger"
          >
            {changeState.error}
          </p>
        )}

        <Button type="submit" size="lg" dot disabled={changePending} className="w-full">
          {changePending ? (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden />
              Saving password...
            </>
          ) : (
            <>
              <KeyRound className="size-4" aria-hidden />
              Save password & enter workspace
            </>
          )}
        </Button>

        <button
          type="button"
          onClick={() => setCancelled(true)}
          className="flex items-center justify-center gap-1.5 text-xs text-ink-muted hover:text-ink-strong transition-colors py-1 cursor-pointer"
        >
          <ArrowLeft className="size-3.5" aria-hidden />
          Back to sign in
        </button>
      </form>
    );
  }

  return (
    <form action={formAction} className={cn("flex flex-col gap-5", className)}>
      <input type="hidden" name="next" value={next} />

      {mode === "bootstrap" && (
        <Field label="Your name">
          <Input name="name" autoComplete="name" placeholder="Founder" />
        </Field>
      )}

      <Field label="Username or email">
        <Input
          name="email"
          type="text"
          autoComplete="username"
          required
          placeholder="admin or you@company.com"
        />
      </Field>

      <Field label="Password">
        <Input
          name="password"
          type="password"
          autoComplete={mode === "bootstrap" ? "new-password" : "current-password"}
          required
          placeholder="••••••••"
        />
      </Field>

      {state?.error && (
        <p
          role="alert"
          className="rounded-md border border-status-danger bg-status-danger-bg px-3 py-2 font-sans text-sm text-status-danger"
        >
          {state.error}
        </p>
      )}

      <Button type="submit" size="lg" dot disabled={pending} className="w-full">
        {pending ? (
          <>
            <Loader2 className="size-4 animate-spin" aria-hidden />
            Signing in
          </>
        ) : mode === "bootstrap" ? (
          <>
            <KeyRound className="size-4" aria-hidden />
            Create the first account
          </>
        ) : (
          "Sign in"
        )}
      </Button>

      <p className="font-code text-xs text-ink-faint">workspace {workspaceId}</p>
    </form>
  );
}

