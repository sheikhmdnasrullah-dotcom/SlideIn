"use client";

import { useActionState } from "react";
import { KeyRound, Loader2 } from "lucide-react";

import { bootstrapAction, loginAction, type AuthFormState } from "@/lib/auth/actions";
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

  return (
    <form action={formAction} className={cn("flex flex-col gap-5", className)}>
      <input type="hidden" name="next" value={next} />

      {mode === "bootstrap" && (
        <Field label="Your name">
          <Input name="name" autoComplete="name" placeholder="Founder" />
        </Field>
      )}

      <Field label="Email">
        <Input
          name="email"
          type="email"
          autoComplete="email"
          required
          placeholder="you@company.com"
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

      <p className="font-code text-xs text-ink-faint">
        workspace {workspaceId}
      </p>
    </form>
  );
}
