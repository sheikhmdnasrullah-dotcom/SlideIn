/**
 * Server-side client for the Slidein workflow API.
 *
 * Every route handler in this app goes through here: one base URL, one API
 * key from the environment (never shipped to the browser), one error shape.
 */

import "server-only";

import { API_BASE_URL, API_KEY, WORKSPACE_ID } from "./config";
import { ApiRequestError } from "./errors";
import type { ApiError } from "./types";

export { ApiRequestError };

type Query = Record<string, string | number | boolean | undefined | null>;

function buildUrl(path: string, query?: Query): string {
  const url = new URL(API_BASE_URL.replace(/\/$/, "") + path);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    url.searchParams.set(key, String(value));
  }
  return url.toString();
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  query?: Query;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query } = options;
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Slidein-Tenant": WORKSPACE_ID,
  };
  if (API_KEY) headers.Authorization = `Bearer ${API_KEY}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch (cause) {
    throw new ApiRequestError(503, {
      code: "provider_unavailable",
      message: `Slidein API unreachable at ${API_BASE_URL}: ${(cause as Error).message}`,
      recovery_action: "retry_stage",
      retryable: true,
      details: {},
    });
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload: unknown = text ? safeParse(text) : null;

  if (!response.ok) {
    const error = normaliseError(response.status, payload);
    throw new ApiRequestError(response.status, error);
  }
  return payload as T;
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
}

function normaliseError(status: number, payload: unknown): ApiError {
  const record = (payload ?? {}) as Record<string, unknown>;
  const nested = (record.error ?? record.detail ?? record) as Record<string, unknown>;
  const code = typeof nested.code === "string" ? nested.code : "ERROR";
  const message =
    typeof nested.message === "string" ? nested.message : `Request failed with ${status}`;
  const details = (nested.details ?? {}) as Record<string, unknown>;
  const recovery =
    typeof nested.recovery_action === "string" ? nested.recovery_action : "retry_stage";
  const retryable = nested.retryable === true;
  return { code, message, details, recovery_action: recovery, retryable };
}

export interface WorkflowClient {
  get<T>(path: string, query?: Query): Promise<T>;
  post<T>(path: string, body?: unknown): Promise<T>;
  put<T>(path: string, body?: unknown): Promise<T>;
  del<T>(path: string): Promise<T>;
}

export const client: WorkflowClient = {
  get: <T,>(path: string, query?: Query) => request<T>(path, { method: "GET", query }),
  post: <T,>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  put: <T,>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body }),
  del: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
};

export function workspacePath(path: string, workspaceId: string): string {
  return `/v1/tenants/${workspaceId}${path}`;
}
