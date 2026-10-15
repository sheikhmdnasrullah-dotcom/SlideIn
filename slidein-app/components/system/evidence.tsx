import { cn } from "@/lib/utils";
import { StatusBadge } from "./status-badge";
import { VERIFICATION_LABELS, VERIFICATION_TONES } from "@/lib/workflow/metadata";
import type { EvidenceItem } from "@/lib/api/types";

/**
 * EvidenceBlock: how the workspace shows that a claim is source-backed.
 * An evidence item is only shown with its URL and its verification status —
 * Research refuses to produce a claim without one.
 */
export function EvidenceBlock({
  evidence,
  className,
  compact = false,
}: {
  evidence: EvidenceItem[];
  className?: string;
  compact?: boolean;
}) {
  if (evidence.length === 0) {
    return (
      <p className={cn("text-2xs text-ink-faint", className)}>
        No evidence item is attributed to this claim.
      </p>
    );
  }
  return (
    <ul className={cn("flex flex-col divide-y divide-rule", className)}>
      {evidence.map((item) => (
        <li key={item.id} className={compact ? "py-1.5" : "py-2.5"}>
          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="font-label text-ink-faint">
                {item.evidence_type.replace(/_/g, " ")}
              </span>
              <StatusBadge
                tone={VERIFICATION_TONES[item.verification_status]}
                label={VERIFICATION_LABELS[item.verification_status]}
              />
              <span className="font-value text-2xs text-ink-faint">
                conf {item.confidence.toFixed(2)}
              </span>
            </div>
            <p className="text-[0.8125rem] leading-relaxed text-ink-muted">{item.claim_text}</p>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-ink-faint">
              {item.source_url ? (
                <a
                  href={item.source_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="rounded-xs text-ink-muted underline decoration-rule-strong underline-offset-2 hover:decoration-flame-vivid focus-ring"
                >
                  {item.source_name || item.source_url}
                </a>
              ) : (
                <span className="text-status-warn">no source url</span>
              )}
              <span>collected by {item.retrieved_by || item.collector}</span>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** SourceCitation: one line pointing at where a claim came from. */
export function SourceCitation({ url, name }: { url: string; name?: string }) {
  if (!url) return <span className="text-2xs text-ink-faint">no source</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer noopener"
      className="rounded-xs text-2xs text-ink-muted underline decoration-rule-strong underline-offset-2 hover:decoration-flame-vivid focus-ring"
    >
      {name || url}
    </a>
  );
}
