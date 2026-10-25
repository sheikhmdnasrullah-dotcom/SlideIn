/**
 * Workflow metadata — the single place the UI learns what a status, stage,
 * or failure code means.
 *
 * Nothing here invents behaviour: every label and tone is derived from the
 * contract declared in `slidein-api/slidein_api/contracts.py` and from the
 * lifecycle in `lifecycle.py`.
 */

import type {
  ConversationState,
  DeliveryEventType,
  DraftStatus,
  ProspectStatus,
  ReplyIntent,
  RunStatus,
  SentStatus,
  Stage,
  VerificationStatus,
} from "../api/types";

export type StatusTone = "live" | "info" | "warn" | "danger" | "neutral" | "flame";

// ── sections ───────────────────────────────────────────────────────────────

export interface SectionMeta {
  id: string;
  href: string;
  label: string;
  group: "pipeline" | "setup" | "history";
  /** The stage each section fronts, so the nav is the workflow order. */
  stage: Stage;
  description: string;
}

export const SECTIONS: SectionMeta[] = [
  {
    id: "overview",
    href: "/overview",
    label: "Overview",
    group: "pipeline",
    stage: "synthesize",
    description: "What the pipeline is holding and what needs a decision.",
  },
  {
    id: "profile",
    href: "/profile",
    label: "Business Profile",
    group: "setup",
    stage: "configure",
    description: "Versioned configuration handed to Discovery.",
  },
  {
    id: "discovery",
    href: "/discovery",
    label: "Discovery",
    group: "pipeline",
    stage: "discover",
    description: "Source-attributed prospect records for the active ICP.",
  },
  {
    id: "research",
    href: "/research",
    label: "Research",
    group: "pipeline",
    stage: "research",
    description: "Source-backed evidence about one prospect.",
  },
  {
    id: "osint",
    href: "/osint",
    label: "OSINT",
    group: "pipeline",
    stage: "research",
    description: "Ad-hoc OpenOSINT lookups against a name, email, handle, or domain.",
  },
  {
    id: "qualification",
    href: "/qualification",
    label: "Qualification",
    group: "pipeline",
    stage: "qualify",
    description: "Explainable ICP score and justified offer match.",
  },
  {
    id: "personalization",
    href: "/personalization",
    label: "Personalization",
    group: "pipeline",
    stage: "personalize",
    description: "Versioned drafts built from attributed evidence.",
  },
  {
    id: "outreach",
    href: "/outreach",
    label: "Outreach",
    group: "pipeline",
    stage: "outreach",
    description: "Approval, sending policy, dispatch, delivery events.",
  },
  {
    id: "conversations",
    href: "/conversations",
    label: "Conversations",
    group: "pipeline",
    stage: "converse",
    description: "Inbound replies on the same prospect records.",
  },
  {
    id: "activity",
    href: "/activity",
    label: "Activity",
    group: "history",
    stage: "synthesize",
    description: "The workflow history of every record.",
  },
];

export const STAGE_LABELS: Record<Stage, string> = {
  configure: "Business Profile",
  discover: "Discovery",
  research: "Research",
  qualify: "Qualification",
  personalize: "Personalization",
  outreach: "Outreach",
  converse: "Conversations",
  synthesize: "Overview",
};

// ── status maps ────────────────────────────────────────────────────────────

export const PROSPECT_STATUS_LABELS: Record<ProspectStatus, string> = {
  discovered: "Discovered",
  researching: "Researching",
  researched: "Researched",
  qualified: "Qualified",
  disqualified: "Disqualified",
  draft_ready: "Draft ready",
  in_campaign: "In campaign",
  replied: "Replied",
  opted_out: "Opted out",
};

export const PROSPECT_STATUS_TONES: Record<ProspectStatus, StatusTone> = {
  discovered: "neutral",
  researching: "info",
  researched: "info",
  qualified: "flame",
  disqualified: "danger",
  draft_ready: "warn",
  in_campaign: "live",
  replied: "live",
  opted_out: "danger",
};

export const DRAFT_STATUS_LABELS: Record<DraftStatus, string> = {
  pending_review: "Pending review",
  approved: "Approved",
  rejected: "Rejected",
  sent: "Sent",
  cancelled: "Cancelled",
};

export const DRAFT_STATUS_TONES: Record<DraftStatus, StatusTone> = {
  pending_review: "warn",
  approved: "live",
  rejected: "danger",
  sent: "info",
  cancelled: "neutral",
};

export const SENT_STATUS_LABELS: Record<SentStatus, string> = {
  queued: "Queued",
  submitted: "Submitted",
  accepted: "Accepted",
  delivered: "Delivered",
  bounced: "Bounced",
  deferred: "Deferred",
  complained: "Complained",
  failed: "Failed",
};

export const SENT_STATUS_TONES: Record<SentStatus, StatusTone> = {
  queued: "neutral",
  submitted: "info",
  accepted: "info",
  delivered: "live",
  bounced: "danger",
  deferred: "warn",
  complained: "danger",
  failed: "danger",
};

export const DELIVERY_EVENT_LABELS: Record<DeliveryEventType, string> = {
  submitted: "Submitted",
  accepted: "Accepted",
  delivered: "Delivered",
  bounced: "Bounced",
  deferred: "Deferred",
  opened: "Opened",
  clicked: "Clicked",
  complained: "Complained",
  unsubscribed: "Unsubscribed",
};

export const DELIVERY_EVENT_TONES: Record<DeliveryEventType, StatusTone> = {
  submitted: "info",
  accepted: "info",
  delivered: "live",
  bounced: "danger",
  deferred: "warn",
  opened: "live",
  clicked: "live",
  complained: "danger",
  unsubscribed: "danger",
};

export const RUN_STATUS_LABELS: Record<RunStatus, string> = {
  running: "Running",
  succeeded: "Succeeded",
  needs_review: "Needs review",
  failed: "Failed",
  retrying: "Retrying",
};

export const RUN_STATUS_TONES: Record<RunStatus, StatusTone> = {
  running: "info",
  succeeded: "live",
  needs_review: "warn",
  failed: "danger",
  retrying: "warn",
};

export const CONVERSATION_STATE_LABELS: Record<ConversationState, string> = {
  open: "Open",
  awaiting_reply: "Awaiting reply",
  closed: "Closed",
};

export const CONVERSATION_STATE_TONES: Record<ConversationState, StatusTone> = {
  open: "warn",
  awaiting_reply: "info",
  closed: "neutral",
};

export const REPLY_INTENT_LABELS: Record<ReplyIntent, string> = {
  unclassified: "Unclassified",
  interested: "Interested",
  information_request: "Information request",
  objection: "Objection",
  out_of_office: "Out of office",
  unsubscribe: "Unsubscribe",
  not_interested: "Not interested",
};

export const REPLY_INTENT_TONES: Record<ReplyIntent, StatusTone> = {
  unclassified: "warn",
  interested: "live",
  information_request: "info",
  objection: "warn",
  out_of_office: "neutral",
  unsubscribe: "danger",
  not_interested: "neutral",
};

export const VERIFICATION_LABELS: Record<VerificationStatus, string> = {
  verified: "Verified",
  inferred: "Inferred",
  unverified: "Unverified",
};

export const VERIFICATION_TONES: Record<VerificationStatus, StatusTone> = {
  verified: "live",
  inferred: "warn",
  unverified: "danger",
};

// ── failure codes ──────────────────────────────────────────────────────────

export const RECOVERY_LABELS: Record<string, string> = {
  create_business_profile: "Create a business profile",
  complete_business_profile: "Complete the business profile",
  add_offer: "Add an offer",
  define_icp: "Define an ICP",
  review_config_version: "Review the configuration version",
  return_to_discovery: "Back to Discovery",
  merge_duplicate: "Review the duplicate",
  fix_prospect_record: "Fix the prospect record",
  regenerate_draft: "Regenerate the draft",
  review_draft: "Review the draft",
  run_prerequisite_stage: "Run the prerequisite stage",
  review_prospect_status: "Review the prospect status",
  retry_stage: "Retry the stage",
  retry_stage_later: "Retry once the limit resets",
  review_suppression: "Review the suppression list",
  request_authorization: "Request authorization",
  switch_workspace: "Switch workspace",
  approve_draft: "Approve the draft",
  handle_reply: "Handle the reply",
};

export const FAILURE_TONE: Record<string, StatusTone> = {
  profile_missing: "warn",
  profile_incomplete: "warn",
  offer_missing: "warn",
  icp_missing: "warn",
  config_version_conflict: "warn",
  prospect_not_found: "neutral",
  prospect_duplicate: "warn",
  prospect_invalid: "warn",
  draft_not_found: "warn",
  draft_not_reviewed: "warn",
  draft_not_approved: "warn",
  stage_prerequisite: "warn",
  invalid_transition: "warn",
  invalid_input: "warn",
  source_unavailable: "danger",
  provider_unavailable: "danger",
  rate_limited: "warn",
  transport_rejected: "danger",
  suppressed: "danger",
  not_authorized: "danger",
  tenant_forbidden: "danger",
  approval_required: "warn",
  unknown: "danger",
};

export const ATTENTION_TONES: Record<string, StatusTone> = {
  danger: "danger",
  warn: "warn",
  info: "info",
};

// ── pipeline order (drives the prospect timeline + next action) ────────────

export const PIPELINE_ORDER: ProspectStatus[] = [
  "discovered",
  "researched",
  "qualified",
  "draft_ready",
  "in_campaign",
  "replied",
];

export const STAGE_ORDER: Stage[] = [
  "configure",
  "discover",
  "research",
  "qualify",
  "personalize",
  "outreach",
  "converse",
];

/** The action each status implies, mirroring the overview next-actions. */
export const STATUS_NEXT_ACTION: Record<ProspectStatus, { action: string; label: string; stage: Stage }> = {
  discovered: { action: "run_research", label: "Run research", stage: "research" },
  researching: { action: "finish_research", label: "Finish research", stage: "research" },
  researched: { action: "run_qualification", label: "Qualify", stage: "qualify" },
  qualified: { action: "prepare_draft", label: "Prepare a draft", stage: "personalize" },
  disqualified: { action: "no_action", label: "Disqualified", stage: "qualify" },
  draft_ready: { action: "review_draft", label: "Review the draft", stage: "personalize" },
  in_campaign: { action: "await_reply", label: "Await reply", stage: "outreach" },
  replied: { action: "handle_reply", label: "Handle the reply", stage: "converse" },
  opted_out: { action: "no_action", label: "Opted out", stage: "converse" },
};

export function stageLabel(stage: string | undefined): string {
  if (!stage) return "—";
  return STAGE_LABELS[stage as Stage] ?? stage;
}

export function prospectStatusLabel(status: string | undefined): string {
  if (!status) return "—";
  return PROSPECT_STATUS_LABELS[status as ProspectStatus] ?? status;
}

export function recoveryLabel(action: string | undefined): string {
  if (!action) return "—";
  return RECOVERY_LABELS[action] ?? action;
}
