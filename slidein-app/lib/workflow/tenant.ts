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
 *
 * The accent axis (selection, focus, dots, links, the flame role) is driven
 * by the tenant primary hex. Only ONE hue is ever active: the brand accent
 * replaces the Slidein orange on the accent axis, while surface, ink, rule
 * and status colours stay on the shared contract so the console still reads
 * as Slidein. The wordmark is live text, so it inverts with the theme.
 */
export function themeStyle(branding: Branding | null | undefined): React.CSSProperties {
  if (!branding) return {};
  const primary = cleanHex(branding.colors?.primary);
  const surface = cleanHex(branding.colors?.surface);
  const ink = cleanHex(branding.colors?.ink);
  const style: Record<string, string> = {};
  if (primary) {
    // Derive the supporting tints from the one primary hex. No second hue.
    style["--color-brand"] = primary;
    style["--text-accent"] = primary;
    style["--accent-vivid"] = primary;
    style["--accent-wash"] = `${primary}1a`;
    style["--accent-highlight"] = `${primary}2e`;
    style["--accent-ring"] = `${primary}3d`;
    style["--input-focus-ring"] = `${primary}24`;
    style["--focus-ring"] = `${primary}60`;
    style["--on-accent"] = "#ffffff";
    style["--color-flame"] = primary;
    style["--color-flame-vivid"] = primary;
    style["--color-flame-wash"] = `${primary}1a`;
    style["--color-flame-ring"] = `${primary}3d`;
    style["--color-on-flame"] = "#ffffff";
  }
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

/**
 * The qualifier shown under the workspace name in the sidebar: the remainder
 * of the business name after the first word, or the domain parent when the
 * name is a single word. Empty when the name is unconfigured.
 */
export function clientQualifier(name: string | undefined): string {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length > 1) return words.slice(1).join(" ");
  return "";
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
