/** Runtime configuration for the Slidein API connection. */

const env = process.env;

export const API_BASE_URL: string =
  env.SLIDEIN_API_URL || env.NEXT_PUBLIC_SLIDEIN_API_URL || "http://127.0.0.1:8100";

export const API_KEY: string = env.SLIDEIN_API_KEY || "";

export const WORKSPACE_ID: string =
  env.SLIDEIN_WORKSPACE_ID || env.NEXT_PUBLIC_SLIDEIN_WORKSPACE_ID || "ten_local";

/** `true` when the API is contacted with no key (local development). */
export const AUTH_DISABLED: boolean =
  (env.SLIDEIN_AUTH_MODE || "enforced").toLowerCase() === "disabled" || !API_KEY;
