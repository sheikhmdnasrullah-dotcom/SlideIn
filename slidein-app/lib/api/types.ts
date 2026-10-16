/**
 * Typed shapes of everything the Slidein workflow API persists.
 *
 * These mirror `slidein-api/slidein_api/serialize.py` exactly — one payload
 * per record, so a UI field can never drift from the stored one.
 */

// ── lifecycle enums ────────────────────────────────────────────────────────

export const PROSPECT_STATUSES = [
  "discovered",
  "researching",
  "researched",
  "qualified",
  "disqualified",
  "draft_ready",
  "in_campaign",
  "replied",
  "opted_out",
] as const;
export type ProspectStatus = (typeof PROSPECT_STATUSES)[number];

export const DRAFT_STATUSES = [
  "pending_review",
  "approved",
  "rejected",
  "sent",
  "cancelled",
] as const;
export type DraftStatus = (typeof DRAFT_STATUSES)[number];

export const SENT_STATUSES = [
  "queued",
  "submitted",
  "accepted",
  "delivered",
  "bounced",
  "deferred",
  "complained",
  "failed",
] as const;
export type SentStatus = (typeof SENT_STATUSES)[number];

export const DELIVERY_EVENT_TYPES = [
  "submitted",
  "accepted",
  "delivered",
  "bounced",
  "deferred",
  "opened",
  "clicked",
  "complained",
  "unsubscribed",
] as const;
export type DeliveryEventType = (typeof DELIVERY_EVENT_TYPES)[number];

export const VERIFICATION_STATUSES = ["verified", "inferred", "unverified"] as const;
export type VerificationStatus = (typeof VERIFICATION_STATUSES)[number];

export const RUN_STATUSES = ["running", "succeeded", "needs_review", "failed", "retrying"] as const;
export type RunStatus = (typeof RUN_STATUSES)[number];

export const CONVERSATION_STATES = ["open", "awaiting_reply", "closed"] as const;
export type ConversationState = (typeof CONVERSATION_STATES)[number];

export const REPLY_INTENTS = [
  "unclassified",
  "interested",
  "information_request",
  "objection",
  "out_of_office",
  "unsubscribe",
  "not_interested",
] as const;
export type ReplyIntent = (typeof REPLY_INTENTS)[number];

export const STAGES = [
  "configure",
  "discover",
  "research",
  "qualify",
  "personalize",
  "outreach",
  "converse",
  "synthesize",
] as const;
export type Stage = (typeof STAGES)[number];

// ── configuration ──────────────────────────────────────────────────────────

export interface BusinessProfile {
  id: string;
  tenant_id: string;
  legal_name: string;
  website_url: string;
  industry: string;
  company_description: string;
  core_value_prop: string;
  markets_served: string[];
  target_roles: string[];
  brand_voice: string;
  version: number;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface Offer {
  id: string;
  tenant_id: string;
  profile_id: string;
  name: string;
  summary: string;
  pain_points_solved: string[];
  target_persona: string;
  proof_points: string[];
  version: number;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface Icp {
  id: string;
  tenant_id: string;
  profile_id: string | null;
  name: string;
  industries: string[];
  company_size_min: number;
  company_size_max: number;
  geographies: string[];
  target_roles: string[];
  required_signals: string[];
  exclusion_keywords: string[];
  qualify_threshold: number;
  version: number;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface ConfigVersionRecord {
  id: string;
  tenant_id: string;
  entity_type: string;
  entity_id: string;
  version: number;
  snapshot: Record<string, unknown>;
  actor: string;
  reason: string;
  created_at: string;
}

// ── pipeline ───────────────────────────────────────────────────────────────

export interface Prospect {
  id: string;
  tenant_id: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  phone: string;
  company_name: string;
  company_domain: string;
  job_title: string;
  linkedin_url: string;
  company_size: number | null;
  location: string;
  source: string;
  source_ref: string;
  source_detail: Record<string, unknown>;
  status: ProspectStatus;
  status_reason: string;
  qualification_score: number;
  profile_id: string | null;
  profile_version: number | null;
  icp_id: string | null;
  icp_version: number | null;
  offer_id: string | null;
  discovered_by: string;
  discovered_at: string;
  updated_at: string;
  /** Present on the detail payload only. */
  state_history?: StateHistoryEntry[];
  evidence?: EvidenceItem[];
  qualification?: Qualification[];
  offer_matches?: OfferMatch[];
  drafts?: Draft[];
  draft_versions?: Record<string, DraftVersion[]>;
  sent_messages?: SentMessage[];
  delivery_events?: DeliveryEvent[];
  activity?: ActivityLog[];
  conversations?: ConversationDetail[];
  stage_runs?: StageRun[];
}

export interface StateHistoryEntry {
  state: string;
  entered_at: string;
  exited_at: string | null;
  reason: string;
  actor: string;
  stage: string;
  run_id: string;
}

export interface EvidenceItem {
  id: string;
  tenant_id: string;
  prospect_id: string;
  evidence_type: string;
  claim_text: string;
  source_url: string;
  source_name: string;
  confidence: number;
  verification_status: VerificationStatus;
  collector: string;
  retrieved_by: string;
  retrieved_at: string;
}

export interface Criterion {
  criterion: string;
  points: number;
  max_points: number;
  detail: string;
  evidence_ids: string[];
}

export interface Qualification {
  id: string;
  tenant_id: string;
  prospect_id: string;
  icp_id: string;
  icp_version: number | null;
  profile_version: number | null;
  score: number;
  is_qualified: boolean;
  matching_criteria: Criterion[];
  missing_criteria: Criterion[];
  explanation: string;
  evaluator: string;
  evaluated_by: string;
  evaluated_at: string;
  threshold?: number;
  max_score?: number;
  offer_match?: OfferMatch & { offer?: Offer };
}

export interface OfferMatch {
  id: string;
  tenant_id: string;
  prospect_id: string;
  offer_id: string;
  offer_version: number | null;
  rationale: string;
  evidence_ids: string[];
  score: number;
  is_selected: boolean;
  matched_by: string;
  matched_at: string;
  offer?: Offer;
}

// ── outreach ───────────────────────────────────────────────────────────────

export interface Draft {
  id: string;
  tenant_id: string;
  prospect_id: string;
  offer_id: string | null;
  qualification_id: string | null;
  subject: string;
  body: string;
  version: number;
  status: DraftStatus;
  attributed_evidence_ids: string[];
  human_edited: boolean;
  profile_version: number | null;
  approved_by: string;
  approved_at: string | null;
  approval_note: string;
  rejected_by: string;
  rejected_reason: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface DraftVersion {
  id: string;
  tenant_id: string;
  draft_id: string;
  version: number;
  subject: string;
  body: string;
  change_reason: string;
  changed_by: string;
  is_human_edit: boolean;
  created_at: string;
}

export interface DraftDetail extends Draft {
  evidence: EvidenceItem[];
  qualification: Qualification | null;
  offer: Offer | null;
  versions: DraftVersion[];
  prospect: {
    id: string;
    full_name: string;
    email: string;
    company_name: string;
    status: string;
  } | null;
}

export interface SentMessage {
  id: string;
  tenant_id: string;
  draft_id: string;
  draft_version: number;
  prospect_id: string;
  sender_email: string;
  recipient_email: string;
  message_id: string;
  transport: string;
  delivery_status: SentStatus;
  attempt: number;
  error_code: string;
  error_message: string;
  authorized_by: string;
  queued_at: string;
  sent_at: string | null;
  status_updated_at: string;
}

export interface DeliveryEvent {
  id: string;
  tenant_id: string;
  sent_message_id: string;
  prospect_id: string;
  event_type: DeliveryEventType;
  provider: string;
  detail: string;
  payload: Record<string, unknown>;
  occurred_at: string;
  recorded_by: string;
}

export interface SuppressionRecord {
  id: string;
  tenant_id: string | null;
  email: string;
  domain: string;
  reason: string;
  note: string;
  suppressed_by: string;
  suppressed_at: string;
}

export interface SendingPolicy {
  require_approval: boolean;
  daily_limit: number;
  hourly_limit: number;
  max_attempts: number;
  send_window: string;
  allowed_senders: string[];
}

// ── white-label: branding + modules ────────────────────────────────────────

export interface BrandColors {
  primary: string;
  surface: string;
  ink: string;
}

export interface Branding {
  business_name: string;
  logo_url: string;
  favicon_url: string;
  colors: BrandColors;
  email_from_name: string;
  custom_domain: string;
  domain_verified: boolean;
}

export interface ModuleMeta {
  id: string;
  label: string;
  min_role: string;
  description: string;
}

export interface WorkspaceModules {
  enabled: string[];
  nav_order: string[];
  registry: ModuleMeta[];
  source?: "tenant" | "template" | "default";
  template?: TemplatePointer | null;
}

export interface TemplatePointer {
  id: string;
  version: number | null;
  applied_at: string | null;
  label: string | null;
}

export interface TemplateSummary {
  id: string;
  version: number;
  label: string;
  description: string;
}

export interface TemplateDoc extends TemplateSummary {
  modules: { enabled: string[]; nav_order: string[] };
  terminology: TemplateTerminology;
  pipeline_stages: { id: string; label: string }[];
  task_types: string[];
  ai_use_cases: string[];
  required_integrations: string[];
  role_defaults: Record<string, unknown>;
}

export interface TemplateTerminology {
  sections: Record<string, string>;
  nouns: Record<string, string>;
}

export interface EffectiveTemplate {
  template: TemplatePointer | null;
  modules: { enabled: string[]; nav_order: string[]; source: string };
  terminology: TemplateTerminology;
  pipeline_stages: { id: string; label: string }[];
  task_types: string[];
  ai_use_cases: string[];
  required_integrations: string[];
}

// ── conversations ──────────────────────────────────────────────────────────

export interface Conversation {
  id: string;
  tenant_id: string;
  prospect_id: string;
  subject: string;
  thread_id: string;
  state: ConversationState;
  intent: ReplyIntent;
  intent_confidence: number;
  requires_action: boolean;
  last_message_at: string | null;
  created_at: string;
}

export interface InboundReply {
  id: string;
  tenant_id: string;
  conversation_id: string;
  prospect_id: string;
  sent_message_id: string | null;
  sender_email: string;
  subject: string;
  body: string;
  thread_id: string;
  intent: ReplyIntent;
  intent_confidence: number;
  requires_action: boolean;
  recommended_action: string;
  received_by: string;
  received_at: string;
}

export interface ConversationDetail {
  conversation: Conversation;
  prospect: Prospect | null;
  replies: InboundReply[];
  outbound: SentMessage[];
}

// ── workflow runtime + audit ───────────────────────────────────────────────

export interface StageRun {
  id: string;
  tenant_id: string;
  run_key: string;
  stage: Stage;
  subject_type: string;
  subject_id: string;
  status: RunStatus;
  attempt: number;
  max_attempts: number;
  reason: string;
  needs_review: string[];
  from_status: string;
  to_status: string;
  error_code: string;
  error_message: string;
  recovery_action: string;
  retryable: boolean;
  triggered_by: string;
  input_snapshot: Record<string, unknown>;
  output_snapshot: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
}

export interface ActivityLog {
  id: string;
  tenant_id: string;
  actor: string;
  actor_role: string;
  action: string;
  entity_type: string;
  entity_id: string;
  prospect_id: string | null;
  stage: string;
  run_id: string | null;
  summary: string;
  reason: string;
  details: Record<string, unknown>;
  created_at: string;
}

// ── API envelopes ──────────────────────────────────────────────────────────

export interface StageOutcome<T = Record<string, unknown>> {
  stage: Stage;
  status: "succeeded" | "needs_review" | "failed";
  outputs: T;
  reason: string;
  needs_review: string[];
  from_status: string;
  to_status: string;
  run_id: string | null;
  attempt: number | null;
  error: {
    code: string;
    message: string;
    recovery_action: string;
    retryable: boolean;
  } | null;
  details: Record<string, unknown>;
  ok: boolean;
  recovery_action?: string;
  retryable?: boolean;
}

export interface ApiError {
  code: string;
  message: string;
  details: Record<string, unknown>;
  recovery_action: string;
  retryable: boolean;
}

export interface Readiness {
  tenant_id: string;
  overall_score: number;
  is_ready_for_activation: boolean;
  checklist: { key: string; status: string; weight: number; message: string }[];
  profile_version: number | null;
}

export interface AttentionItem {
  kind: string;
  severity: "danger" | "warn" | "info";
  stage: string;
  stage_label: string;
  subject_id: string;
  subject_type: string;
  title: string;
  detail: string;
  reason: string;
  recovery_action: string;
  retryable: boolean;
  attempt?: number;
  max_attempts?: number;
  run_id: string | null;
  href: string;
  draft_id?: string;
  conversation_id?: string;
  created_at: string | null;
}

export interface Overview {
  tenant_id: string;
  counts: Record<ProspectStatus, number>;
  total_prospects: number;
  funnel: { status: string; label: string; count: number }[];
  drafts: Record<DraftStatus, number>;
  delivery: Record<string, number>;
  stage_health: Record<string, { succeeded: number; needs_review: number; failed: number }>;
  attention: AttentionItem[];
  next_actions: {
    prospect_id: string;
    name: string;
    company: string;
    status: ProspectStatus;
    action: string;
    action_label: string;
    score: number;
    href: string;
  }[];
  sources: { source: string; count: number }[];
  conversion: {
    discovered_to_replied: number;
    discovered_to_qualified: number;
    sent_to_replied: number;
  };
  replies_received: number;
  open_conversations: number;
  cleared_replied: number;
}

export interface Handoff {
  from: string;
  from_label: string;
  to: string;
  to_label: string;
  carried: string[];
  blocked_by: string[];
  waiting: { count: number; label: string }[];
  health: { succeeded: number; needs_review: number; failed: number };
}

// ── contracts ──────────────────────────────────────────────────────────────

export interface ContractField {
  name: string;
  kind: string;
  required: boolean;
  description: string;
}

export interface ContractFailure {
  code: string;
  retryable: boolean;
  recovery_action: string;
  description: string;
}

export interface StageContract {
  stage: Stage;
  title: string;
  summary: string;
  requires: ContractField[];
  produces: ContractField[];
  transitions: [string, string][];
  failures: ContractFailure[];
  needs_review_when: string[];
  permission: string;
  max_attempts: number;
  notes: string;
}

export interface HandoffSpec {
  from: string;
  to: string;
  carried: string[];
  blocked_by: string[];
}

export interface ContractCatalog {
  stages: StageContract[];
  handoffs: HandoffSpec[];
}

// ── pagination ─────────────────────────────────────────────────────────────

export interface Page<T> {
  data: T[];
  total: number;
  limit: number;
  offset: number;
}
