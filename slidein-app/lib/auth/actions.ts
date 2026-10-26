/**
 * Auth server actions for the Console.
 *
 * The browser posts a form; the API decides whether the credentials are
 * good; only then is the HttpOnly session cookie written. Failures come
 * back as the API's own message — no invented copy, no credential echo.
 */

"use server";

import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { API_BASE_URL, WORKSPACE_ID } from "@/lib/api/config";
import { SESSION_COOKIE, sessionCookieOptions } from "./session";

export interface AuthFormState {
  error?: string;
  notice?: string;
}

const DEFAULT_SESSION_SECONDS = 60 * 60 * 24 * 14;

function str(value: FormDataEntryValue | string | null): string {
  return typeof value === "string" ? value.trim() : "";
}

/** Only same-origin absolute paths — never a protocol-relative URL. */
function safeNext(value: string): string {
  if (!value.startsWith("/") || value.startsWith("//")) return "/overview";
  return value;
}

function messageOf(payload: unknown, fallback: string): string {
  const record = (payload ?? {}) as Record<string, unknown>;
  const nested = (record.error ?? record.detail ?? record) as Record<string, unknown>;
  const message = nested && typeof nested.message === "string" ? nested.message : "";
  return message || fallback;
}

function sessionSeconds(expiresAt?: string): number {
  if (expiresAt) {
    const expires = Date.parse(expiresAt);
    if (!Number.isNaN(expires)) {
      const seconds = Math.floor((expires - Date.now()) / 1000);
      if (seconds > 60) return seconds;
    }
  }
  return DEFAULT_SESSION_SECONDS;
}

async function readPayload(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
}

export async function loginAction(
  _previous: AuthFormState | undefined,
  formData: FormData,
): Promise<AuthFormState> {
  const email = str(formData.get("email")).toLowerCase();
  const password = str(formData.get("password"));
  const next = safeNext(str(formData.get("next")));

  if (!email || !password) {
    return { error: "Enter your email and password." };
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ email, password }),
      cache: "no-store",
    });
  } catch (cause) {
    return {
      error: `The workspace API is unreachable: ${(cause as Error).message}`,
    };
  }

  const payload = await readPayload(response);
  if (!response.ok) {
    return { error: messageOf(payload, "Sign-in failed.") };
  }

  const record = (payload ?? {}) as Record<string, unknown>;
  const token = typeof record.token === "string" ? record.token : "";
  const tenant = typeof record.tenant_id === "string" ? record.tenant_id : "";
  if (!token) return { error: "Sign-in failed: no session was returned." };
  if (tenant !== WORKSPACE_ID) {
    return {
      error:
        "This account belongs to a different workspace. Use the workspace " +
        "you were invited to, or ask for access to this one.",
    };
  }

  const store = await cookies();
  store.set(SESSION_COOKIE, token, {
    ...sessionCookieOptions(),
    maxAge: sessionSeconds(typeof record.expires_at === "string" ? record.expires_at : undefined),
  });
  redirect(next);
}

/**
 * First-run setup: creates the only account that exists until more are
 * invited. The API closes this window itself once any user exists.
 */
export async function bootstrapAction(
  _previous: AuthFormState | undefined,
  formData: FormData,
): Promise<AuthFormState> {
  const email = str(formData.get("email")).toLowerCase();
  const password = str(formData.get("password"));
  const name = str(formData.get("name"));
  const next = safeNext(str(formData.get("next")));

  if (!email || !password) {
    return { error: "Enter an email and a password." };
  }
  if (password.length < 8) {
    return { error: "Use at least 8 characters for the password." };
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/v1/auth/bootstrap`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ email, password, name }),
      cache: "no-store",
    });
  } catch (cause) {
    return { error: `The workspace API is unreachable: ${(cause as Error).message}` };
  }

  const payload = await readPayload(response);
  if (!response.ok) {
    return { error: messageOf(payload, "Could not create the account.") };
  }

  const record = (payload ?? {}) as Record<string, unknown>;
  const token = typeof record.token === "string" ? record.token : "";
  if (!token) return { error: "Account created, but no session was returned." };

  const store = await cookies();
  store.set(SESSION_COOKIE, token, {
    ...sessionCookieOptions(),
    maxAge: sessionSeconds(typeof record.expires_at === "string" ? record.expires_at : undefined),
  });
  redirect(next);
}

/** Revoke server-side, drop the cookie, land on the sign-in screen. */
export async function logoutAction(): Promise<void> {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  if (token) {
    try {
      await fetch(`${API_BASE_URL}/v1/auth/logout`, {
        method: "POST",
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${token}`,
          "X-Slidein-Tenant": WORKSPACE_ID,
        },
        cache: "no-store",
      });
    } catch {
      // The cookie is still cleared below, so the browser is signed out
      // even when the API cannot confirm the revocation.
    }
  }
  store.set(SESSION_COOKIE, "", { ...sessionCookieOptions(), maxAge: 0 });
  redirect("/login");
}
