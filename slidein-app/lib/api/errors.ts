import type { ApiError } from "./types";

/**
 * The single failure shape for API calls. Safe to import from client
 * components: this module touches no environment, no secrets, no fetch.
 */
export class ApiRequestError extends Error {
  readonly status: number;
  readonly error: ApiError;

  constructor(status: number, error: ApiError) {
    super(error.message);
    this.name = "ApiRequestError";
    this.status = status;
    this.error = error;
  }
}
