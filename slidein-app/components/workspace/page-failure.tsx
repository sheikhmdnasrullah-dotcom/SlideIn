import {
  ApiUnavailableState,
  ErrorState,
  ModuleDisabledState,
} from "@/components/system/states";
import { Surface } from "@/components/system/surface";
import { ApiRequestError } from "@/lib/api/client";
import { isModuleDisabled } from "@/lib/workflow/tenant";

/**
 * PageFailure: every section page renders this when its data load throws.
 * Three honest outcomes: module off (API 403), API unreachable, or the
 * API's own error with its code and recovery action.
 */
export function PageFailure({ error, module }: { error: unknown; module: string }) {
  if (isModuleDisabled(error))
    return (
      <Surface variant="raised">
        <ModuleDisabledState module={module} />
      </Surface>
    );
  if (error instanceof ApiRequestError) {
    if (error.status === 503 || error.error.code === "provider_unavailable") {
      return (
        <Surface variant="raised">
          <ApiUnavailableState message={error.error.message} />
        </Surface>
      );
    }
    return (
      <ErrorState
        title="This section could not load"
        error={{
          code: error.error.code,
          message: error.error.message,
          recovery_action: error.error.recovery_action,
          retryable: error.error.retryable,
        }}
      />
    );
  }
  return (
    <ErrorState
      title="This section could not load"
      error={{ message: error instanceof Error ? error.message : "Unexpected failure" }}
    />
  );
}
