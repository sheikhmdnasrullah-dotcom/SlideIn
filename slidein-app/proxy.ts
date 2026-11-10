import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE } from "@/lib/auth/session";

/**
 * Cheap pre-render gate: no session cookie means send the visitor to the
 * shared sign-in screen before any page work happens. The layout performs
 * the authoritative check (the cookie alone proves nothing — the API
 * validates it), so this only saves wasted renders.
 *
 * Local development with `SLIDEIN_AUTH_MODE=disabled` (set by `./dev`) skips
 * the redirect: the API resolves an admin on the default workspace, so the
 * Console renders immediately without a sign-in exchange.
 */
const DISABLED_AUTH =
  (process.env.SLIDEIN_AUTH_MODE || "").toLowerCase() === "disabled";

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const isAuthScreen = pathname === "/login";
  const isRootPage = pathname === "/";

  if (
    !DISABLED_AUTH &&
    !hasSession &&
    !isAuthScreen &&
    !isRootPage
  ) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(pathname)}`;
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|api/|.*\\.(?:svg|png|jpg|jpeg|gif|webp|woff2?)$).*)",
  ],
};
