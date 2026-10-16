import { Inter_Tight } from "next/font/google";

/**
 * FONT LAYER — Slidein client workspace.
 * ONE face for everything: Inter Tight, the same single family as the
 * approved marketing site, loaded once at weights 400 / 500 / 600.
 * Literal code, IDs, API keys and credential values use the system
 * monospace stack via the .font-code role — never for labels or headings.
 */
export const appFace = Inter_Tight({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-app-sans",
  weight: ["400", "500", "600"],
  fallback: ["system-ui", "arial"],
});
