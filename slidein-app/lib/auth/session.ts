/**
 * Session helpers for the Console BFF.
 *
 * The API mints the token, this app stores it in an HttpOnly cookie and
 * forwards it as a bearer credential on every API call. The cookie is never
 * readable by client-side JavaScript.
 */

import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { API_BASE_URL, WORKSPACE_ID } from "@/lib/api/config";

export const SESSION_COOKIE = "slidein_session";

/** `.slideinventure.com` in production; empty on localhost so the cookie
 * stays host-only (host-only cookies are already shared across ports). */
const COOKIE_DOMAIN = process.env.SLIDEIN_COOKIE_DOMAIN || "";

export interface SessionInfo {
  email: string;
  name?: string | null;
  role: string;
  interfaces: string[];
  tenant_id: string;
  user_id: string;
  method?: string;
}

interface CookieOptions {
  httpOnly: true;
  sameSite: "lax";
  secure: boolean;
  path: "/";
  domain?: string;
}

function cookieOptions(): CookieOptions {
  return {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    ...(COOKIE_DOMAIN ? { domain: COOKIE_DOMAIN } : {}),
  };
}

/** The HttpOnly options both auth actions use when writing the cookie. */
export function sessionCookieOptions(): CookieOptions {
  return cookieOptions();
}

/** Read the raw session token, if any. */
export async function readSessionToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value ?? null;
}

/**
 * Resolve the signed-in identity by asking the API — never by trusting the
 * cookie alone. Returns null for missing, expired, revoked or unreachable
 * sessions so callers can treat "unknown" as "not signed in".
 */
export async function getSession(): Promise<SessionInfo | null> {
  const token = await readSessionToken();
  const disabled =
    (process.env.SLIDEIN_AUTH_MODE || "").toLowerCase() === "disabled";

  if (!token && !disabled) return null;

  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Slidein-Tenant": WORKSPACE_ID,
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/v1/auth/session`, {
      headers,
      cache: "no-store",
    });
    if (!response.ok) return null;
    const payload = (await response.json()) as SessionInfo;
    if (!payload || typeof payload.email !== "string") {
      if (!disabled) return null;
    }
    return payload;
  } catch {
    return null;
  }
}

/** Require a valid workspace session before rendering Console. */
export async function requireSession(): Promise<SessionInfo | null> {
  const session = await getSession();
  if (!session) {
    redirect("/login");
  }
  return session;
}

export const requireConsoleSession = requireSession;
