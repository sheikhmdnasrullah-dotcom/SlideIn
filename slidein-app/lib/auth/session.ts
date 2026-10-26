/**
 * Session helpers for the Console BFF.
 *
 * One session serves both interfaces: the API mints the token, this app
 * stores it in an HttpOnly cookie (shared with Dashboard via
 * `SLIDEIN_COOKIE_DOMAIN`) and forwards it as a bearer credential on every
 * API call. The cookie is never readable by client-side JavaScript.
 */

import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { API_BASE_URL, WORKSPACE_ID } from "@/lib/api/config";

export const SESSION_COOKIE = "slidein_session";

/** `.slideinventure.com` in production; empty on localhost so the cookie
 * stays host-only (host-only cookies are already shared across ports). */
const COOKIE_DOMAIN = process.env.SLIDEIN_COOKIE_DOMAIN || "";

/** The client-facing app — where sessions without the console interface go. */
export const DASHBOARD_ORIGIN = (
  process.env.SLIDEIN_DASHBOARD_URL || "https://app.slideinventure.com"
).replace(/\/$/, "");

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
  if (!token) return null;
  try {
    const response = await fetch(`${API_BASE_URL}/v1/auth/session`, {
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
        "X-Slidein-Tenant": WORKSPACE_ID,
      },
      cache: "no-store",
    });
    if (!response.ok) return null;
    const payload = (await response.json()) as SessionInfo;
    if (!payload || typeof payload.email !== "string") return null;
    return payload;
  } catch {
    return null;
  }
}

/** The interface switcher targets this session in the other app. */
export function dashboardUrl(pathname = "/dashboard"): string {
  return `${DASHBOARD_ORIGIN}${pathname.startsWith("/") ? pathname : `/${pathname}`}`;
}

/**
 * Gate for every Console page. Sends anonymous visitors to the shared
 * sign-in screen; viewers (dashboard-only roles) to the Dashboard.
 * Returns null when the session belongs to a different workspace so the
 * caller can explain the mismatch instead of silently redirecting.
 */
export async function requireConsoleSession(): Promise<SessionInfo | null> {
  const session = await getSession();
  if (!session) {
    redirect("/login");
  }
  if (session.tenant_id !== WORKSPACE_ID) return session;
  if (!session.interfaces.includes("console")) {
    redirect(dashboardUrl("/dashboard"));
  }
  return session;
}
