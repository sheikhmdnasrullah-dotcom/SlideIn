/**
 * Temporary, client-specific brand override for local dev / first-client demos.
 *
 * Per the Interface Architecture Rule (saas/AGENTS.md § "Client differences
 * belong in versioned configuration and validated Console section preferences"),
 * brand differences are configuration only — never a per-client code fork. This
 * module is the local-dev switch: set `SLIDEIN_BRAND=finaya` and the one Console
 * shell re-skins to the active client (logo + accent + name) without touching
 * the canonical brand pipeline (GET /tenants/{id}/branding).
 *
 * Assets are stored locally under `/public/brands/<key>/`. Nothing here phones
 * home to a third party.
 */

import type { Branding } from "@/lib/api/types";

export interface LocalBrand {
  key: string;
  label: string;
  branding: Branding;
  fonts?: { heading: string; body: string };
}

export const FINAYA_HOME_LOANS: LocalBrand = {
  key: "finaya",
  label: "Finaya Home Loans",
  branding: {
    business_name: "Finaya Home Loans",
    logo_url: "/brands/finaya/logo.svg",
    favicon_url: "/brands/finaya/logo.svg",
    colors: {
      // Teal from Finaya's official site (bg-brand / text-brand = teal-700).
      primary: "#0d9488",
      surface: "#ffffff",
      ink: "#0a0a0a",
    },
    email_from_name: "Finaya Home Loans",
    custom_domain: "",
    domain_verified: false,
  },
  fonts: {
    heading: "var(--font-finaya-display, ui-serif)",
    body: "var(--font-finaya-body, inherit)",
  },
};

const BRANDS: Record<string, LocalBrand> = {
  finaya: FINAYA_HOME_LOANS,
};

export function localBrand(): LocalBrand | null {
  const key = (process.env.SLIDEIN_BRAND || "").trim().toLowerCase();
  if (!key || !BRANDS[key]) return null;
  return BRANDS[key];
}
