/**
 * Tenant presentation helpers: section→module mapping, brand theming, and
 * module-disabled detection. Server-safe (no browser APIs).
 *
 * The API enforces module access (403); these helpers only decide what to
 * render. Theme values are re-validated here even though the API validates
 * on write — the BFF may point at any API revision.
 */

import type * as React from "react";

import { ApiRequestError } from "@/lib/api/errors";
import type { Branding } from "@/lib/api/types";

/** Workspace section id → API module id (see slidein-api MODULE_REGISTRY). */
export const SECTION_MODULES: Record<string, string> = {
  overview: "overview",
  profile: "settings",
  discovery: "discovery",
  research: "research",
  qualification: "qualification",
  personalization: "personalization",
  outreach: "outreach",
  conversations: "inbox",
  activity: "activity",
};

const HEX_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

function cleanHex(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim();
  return HEX_RE.test(text) ? text.toLowerCase() : null;
}

/**
 * Tenant theme overrides for the semantic token contract in globals.css.
 * Returns `{}` when branding is absent or invalid, so the default Slidein
 * theme renders — the fallback is a complete theme, never a broken one.
 */
export function themeStyle(branding: Branding | null | undefined): React.CSSProperties {
  if (!branding) return {};
  const surface = cleanHex(branding.colors?.surface);
  const ink = cleanHex(branding.colors?.ink);
  const style: Record<string, string> = {};
  // NOTE (visual redesign): the tenant accent override is intentionally
  // removed. The dashboard spec pins selection, focus, and dots to the
  // single marketing orange in every workspace so both dashboards match
  // each other. Tenant surface/ink overrides below still apply, and the
  // branding settings form keeps saving normally.
  if (surface) {
    style["--surface"] = surface;
    style["--page-fill"] = surface;
  }
  if (ink) {
    style["--on-surface"] = ink;
    style["--text-strong"] = ink;
  }
  return style as React.CSSProperties;
}

/** Logo URL only when it is a plain https URL; otherwise null (initials). */
export function safeLogoUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!text.startsWith("https://") || text.includes("@")) return null;
  if (text.length > 2048) return null;
  return text;
}

export function brandInitials(name: string | undefined): string {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "SI";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

/** True when the API refused with a module-disabled 403. */
export function isModuleDisabled(error: unknown): boolean {
  if (!(error instanceof ApiRequestError)) return false;
  if (error.status !== 403) return false;
  const details = error.error.details ?? {};
  return (
    error.error.code === "not_authorized" &&
    ("module" in details || "modules" in details)
  );
}

/**
 * Resolve an API-suggested href to a workspace route. The API speaks in
 * canonical coordinates (`/prospects/{id}`, `/outreach?draft={id}`); the
 * workspace owns its route tree, so prospect records open under Discovery
 * and drafts under Outreach. Unknown shapes pass through unchanged.
 */
export function resolveHref(href: string | undefined): string {
  if (!href) return "/overview";
  const prospect = href.match(/^\/prospects\/([^/?]+)/);
  if (prospect) return `/discovery/${prospect[1]}`;
  const draft = href.match(/^\/outreach\?draft=([^&]+)/);
  if (draft) return `/outreach/${draft[1]}`;
  return href;
}

/** Human message for any API failure a page surfaces. */
export function apiFailureMessage(error: unknown): string {
  if (error instanceof ApiRequestError) return error.error.message;
  if (error instanceof Error) return error.message;
  return "Unexpected failure";
}
