import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/feedback";
import { GlossTile, type GlossTileIcon } from "./gloss-tile";
import { API_BASE_URL } from "@/lib/api/config";
import { cn } from "@/lib/utils";

/**
 * The three states every panel can be in. A section never silently renders
 * nothing: it says why, and when there is a fix it offers the action.
 */
export function EmptyState({
  title,
  description,
  action,
  icon = "inbox",
  className,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: GlossTileIcon;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-4 py-12 text-center",
        className,
      )}
    >
      <GlossTile icon={icon} size={88} className="mb-4" />
      <span className="font-sans text-base leading-6 font-semibold text-ink-strong">
        {title}
      </span>
      {description && (
        <p className="max-w-[360px] font-sans text-sm leading-[22px] text-ink-muted">
          {description}
        </p>
      )}
      {action && <div className="pt-3">{action}</div>}
    </div>
  );
}

export function LoadingState({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-9 w-full" />
      ))}
    </div>
  );
}

/**
 * ErrorState: the reason is always visible, and the recovery action the
 * backend named is always offered. This is the "when a stage fails, make
 * the reason visible and provide a recovery action" contract in the UI.
 */
export function ErrorState({
  title = "This stage failed",
  error,
  onRetry,
  actions,
  className,
}: {
  title?: string;
  error?: { code?: string; message?: string; recovery_action?: string; retryable?: boolean };
  onRetry?: () => void;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col gap-2 rounded-lg border border-rule bg-surface px-6 py-4 shadow-raised",
        className,
      )}
    >
      <span className="font-display-soft text-[15px] leading-[22px] text-ink-strong">
        {title}
      </span>
      {error?.message && (
        <p className="max-w-prose text-sm leading-[22px] text-ink-muted">{error.message}</p>
      )}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        {error?.code && (
          <span className="font-label text-ink-muted">code: {error.code}</span>
        )}
        {error?.recovery_action && (
          <span className="font-label text-ink-muted">
            recovery: {error.recovery_action.replace(/_/g, " ")}
          </span>
        )}
        {error?.retryable && onRetry && (
          <Button size="sm" variant="outline" onClick={onRetry}>
            Retry
          </Button>
        )}
        {actions}
      </div>
    </div>
  );
}

/** Module guard: the workspace has this module switched off (API 403). */
export function ModuleDisabledState({ module }: { module: string }) {
  return (
    <EmptyState
      title="This module is not enabled for this workspace"
      description={`The '${module}' module is switched off. Enable it under Business Profile → Modules to use this section.`}
    />
  );
}

/** Configuration guard: how to reach a running API, when it is not running. */
export function ApiUnavailableState({ message }: { message?: string }) {
  return (
    <EmptyState
      title="The Slidein API is not reachable"
      description={
        message ??
        `Start it with \`SLIDEIN_API_KEYS='{\"ten_local\":{\"key\":\"dev-key\",\"role\":\"admin\"}}' python run.py\` inside slidein-api (expected at ${API_BASE_URL}).`
      }
    />
  );
}
