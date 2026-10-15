import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/feedback";
import { API_BASE_URL } from "@/lib/api/config";

/**
 * The three states every panel can be in. A section never silently renders
 * nothing: it says why, and when there is a fix it offers the action.
 */
export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-start gap-2 rounded-md bg-surface-2 px-4 py-6 ring-1 ring-rule",
        className,
      )}
    >
      <span className="font-display-soft text-sm text-ink-strong">{title}</span>
      {description && (
        <p className="max-w-prose text-2xs leading-relaxed text-ink-faint">{description}</p>
      )}
      {action && <div className="pt-1">{action}</div>}
    </div>
  );
}

export function LoadingState({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-2", className)}>
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
        "flex flex-col gap-2 rounded-md bg-surface-2 px-4 py-4 ring-1 ring-status-danger/30",
        className,
      )}
    >
      <span className="font-display-soft text-sm text-ink-strong">{title}</span>
      {error?.message && (
        <p className="max-w-prose text-2xs leading-relaxed text-ink-muted">{error.message}</p>
      )}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        {error?.code && (
          <span className="font-label text-ink-faint">code: {error.code}</span>
        )}
        {error?.recovery_action && (
          <span className="font-label text-ink-faint">
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

/** Configuration guard: how to reach a running API, when it is not running. */
export function ApiUnavailableState({ message }: { message?: string }) {
  return (
    <EmptyState
      title="The Slidein API is not reachable"
      description={
        message ??
        `Start it with \`SLIDEIN_API_KEYS='{"ten_local":{"key":"dev-key","role":"admin"}}' python run.py\` inside slidein-api (expected at ${API_BASE_URL}).`
      }
    />
  );
}
