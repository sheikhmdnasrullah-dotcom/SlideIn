/**
 * Every operation the client workspace can perform, mapped 1:1 onto the
 * Slidein workflow API. Server components and route handlers share these, so
 * the initial render and every mutation go through the same contract.
 */

import "server-only";

import { client, workspacePath } from "./client";
import type {
  ActivationStatus,
  ActivityLog,
  AutopilotStatus,
  Branding,
  BusinessProfile,
  ConfigVersionRecord,
  ContractCatalog,
  Conversation,
  ConversationDetail,
  DeliveryEvent,
  Draft,
  DraftDetail,
  EffectiveTemplate,
  EvidenceItem,
  FactoryConnection,
  Handoff,
  Icp,
  Offer,
  OsintEnrichOutcome,
  OsintHealth,
  OsintResearchResult,
  Overview,
  Page,
  Prospect,
  ProspectStatus,
  Qualification,
  Readiness,
  SafeTestReport,
  SendingPolicy,
  SentMessage,
  SetupReport,
  SetupStatus,
  StageOutcome,
  StageRun,
  SuppressionRecord,
  TemplateDoc,
  TemplateSummary,
  WorkspaceModules,
  WorkspaceConfig,
} from "./types";

const page = <T,>(value: Page<T> | undefined, fallback: Page<T>): Page<T> => value ?? fallback;

const emptyPage = <T,>(): Page<T> => ({ data: [], total: 0, limit: 0, offset: 0 });

export const operations = {
  // ── contracts ───────────────────────────────────────────────────────────
  contracts(): Promise<ContractCatalog> {
    return client.get<ContractCatalog>("/v1/contracts");
  },

  // ── configuration ───────────────────────────────────────────────────────
  profile(workspaceId: string) {
    return client.get<{
      profile: BusinessProfile | null;
      offers: Offer[];
      icps: Icp[];
      config_versions: ConfigVersionRecord[];
      readiness: Readiness;
    }>(workspacePath("/profile", workspaceId));
  },
  saveProfile(workspaceId: string, body: Record<string, unknown>) {
    return client.post<{ profile: BusinessProfile; readiness: Readiness }>(
      workspacePath("/profile", workspaceId),
      body,
    );
  },
  saveOffer(workspaceId: string, body: Record<string, unknown>) {
    return client.post<{ offer: Offer; readiness: Readiness }>(
      workspacePath("/offers", workspaceId),
      body,
    );
  },
  deactivateOffer(workspaceId: string, offerId: string) {
    return client.del<{ deactivated: boolean; readiness: Readiness }>(
      workspacePath(`/offers/${offerId}`, workspaceId),
    );
  },
  saveIcp(workspaceId: string, body: Record<string, unknown>) {
    return client.post<{ icp: Icp; readiness: Readiness }>(
      workspacePath("/icps", workspaceId),
      body,
    );
  },
  deactivateIcp(workspaceId: string, icpId: string) {
    return client.del<{ deactivated: boolean; readiness: Readiness }>(
      workspacePath(`/icps/${icpId}`, workspaceId),
    );
  },
  readiness(workspaceId: string) {
    return client.get<Readiness>(workspacePath("/readiness", workspaceId));
  },
  configVersions(workspaceId: string, entityType?: string) {
    return client.get<{ config_versions: ConfigVersionRecord[] }>(
      workspacePath("/config-versions", workspaceId),
      { entity_type: entityType },
    );
  },
  branding(workspaceId: string) {
    return client.get<{ branding: Branding }>(
      workspacePath("/branding", workspaceId),
    );
  },
  saveBranding(workspaceId: string, body: Record<string, unknown>) {
    return client.put<{ branding: Branding }>(
      workspacePath("/branding", workspaceId),
      body,
    );
  },
  modules(workspaceId: string) {
    return client.get<WorkspaceModules>(workspacePath("/modules", workspaceId));
  },
  /** Adaptive workspace config — saved, versioned, per-tenant. Drives nav order. */
  workspaceConfig() {
    return client.get<WorkspaceConfig>("/v1/workspace/config");
  },
  saveModules(workspaceId: string, body: Record<string, unknown>) {
    return client.put<WorkspaceModules>(
      workspacePath("/modules", workspaceId),
      body,
    );
  },
  templates() {
    return client.get<{ templates: TemplateSummary[] }>("/v1/templates");
  },
  templateDoc(templateId: string) {
    return client.get<{ template: TemplateDoc }>(`/v1/templates/${templateId}`);
  },
  tenantTemplate(workspaceId: string) {
    return client.get<EffectiveTemplate>(workspacePath("/template", workspaceId));
  },
  applyTemplate(workspaceId: string, body: Record<string, unknown>) {
    return client.post<EffectiveTemplate>(
      workspacePath("/template", workspaceId),
      body,
    );
  },

  // ── discovery ───────────────────────────────────────────────────────────
  discover(workspaceId: string, body: Record<string, unknown>) {
    return client.post<StageOutcome>(workspacePath("/discover", workspaceId), body);
  },
  prospects(
    workspaceId: string,
    query?: {
      limit?: number;
      offset?: number;
      status?: string;
      search?: string;
      min_score?: number;
      source?: string;
    },
  ) {
    return client
      .get<Page<Prospect>>(workspacePath("/prospects", workspaceId), query)
      .then((value) => page(value, emptyPage<Prospect>()));
  },
  prospect(workspaceId: string, prospectId: string) {
    return client.get<Prospect>(workspacePath(`/prospects/${prospectId}`, workspaceId));
  },
  prospectEvidence(workspaceId: string, prospectId: string) {
    return client.get<{ evidence: EvidenceItem[]; qualification: Qualification | null }>(
      workspacePath(`/prospects/${prospectId}/evidence`, workspaceId),
    );
  },

  // ── research ────────────────────────────────────────────────────────────
  research(workspaceId: string, prospectId: string, body: Record<string, unknown> = {}) {
    return client.post<StageOutcome>(
      workspacePath(`/prospects/${prospectId}/research`, workspaceId),
      body,
    );
  },
  evidence(workspaceId: string, prospectId: string) {
    return client.get<{ evidence: EvidenceItem[] }>(
      workspacePath(`/prospects/${prospectId}/evidence`, workspaceId),
    );
  },

  // ── osint ───────────────────────────────────────────────────────────────
  osintHealth() {
    return client.get<OsintHealth>("/v1/osint/health");
  },
  osintResearch(workspaceId: string, body: Record<string, unknown>) {
    return client.post<OsintResearchResult>(
      workspacePath("/osint/research", workspaceId),
      body,
    );
  },
  prospectOsint(workspaceId: string, prospectId: string) {
    return client.get<{ prospect_id: string; evidence: EvidenceItem[]; count: number }>(
      workspacePath(`/prospects/${prospectId}/osint`, workspaceId),
    );
  },
  runProspectOsint(workspaceId: string, prospectId: string, body: Record<string, unknown> = {}) {
    return client.post<OsintEnrichOutcome>(
      workspacePath(`/prospects/${prospectId}/osint`, workspaceId),
      body,
    );
  },

  // ── autopilot ───────────────────────────────────────────────────────────
  autopilot(workspaceId: string) {
    return client.get<AutopilotStatus>(workspacePath("/autopilot", workspaceId));
  },
  setAutopilot(
    workspaceId: string,
    body: { enabled?: boolean; auto_approve?: boolean; send_enabled?: boolean },
  ) {
    return client.post<AutopilotStatus>(workspacePath("/autopilot", workspaceId), body);
  },
  runAutopilot(workspaceId: string) {
    return client.post<{ tick: { status: string; stats: Record<string, number> } }>(
      workspacePath("/autopilot/run", workspaceId),
    );
  },

  // ── qualification ───────────────────────────────────────────────────────
  qualify(workspaceId: string, prospectId: string, body: Record<string, unknown> = {}) {
    return client.post<StageOutcome<Qualification>>(
      workspacePath(`/prospects/${prospectId}/qualify`, workspaceId),
      body,
    );
  },
  qualifications(workspaceId: string, qualifiedOnly = false, limit = 100) {
    return client
      .get<Page<Qualification>>(workspacePath("/qualifications", workspaceId), {
        qualified_only: qualifiedOnly,
        limit,
      })
      .then((value) => page(value, emptyPage<Qualification>()));
  },

  // ── personalization ─────────────────────────────────────────────────────
  personalize(workspaceId: string, prospectId: string, body: Record<string, unknown> = {}) {
    return client.post<StageOutcome<Draft>>(
      workspacePath(`/prospects/${prospectId}/personalize`, workspaceId),
      body,
    );
  },
  drafts(
    workspaceId: string,
    query?: { status?: string; prospect_id?: string; limit?: number },
  ) {
    return client
      .get<Page<Draft>>(workspacePath("/drafts", workspaceId), query)
      .then((value) => page(value, emptyPage<Draft>()));
  },
  draft(workspaceId: string, draftId: string) {
    return client.get<DraftDetail>(workspacePath(`/drafts/${draftId}`, workspaceId));
  },
  editDraft(
    workspaceId: string,
    draftId: string,
    body: { subject: string; body: string; change_reason?: string },
  ) {
    return client.post<{ draft: Draft; detail: DraftDetail }>(
      workspacePath(`/drafts/${draftId}/edit`, workspaceId),
      body,
    );
  },
  approveDraft(workspaceId: string, draftId: string, note?: string) {
    return client.post<{ draft: Draft }>(workspacePath(`/drafts/${draftId}/approve`, workspaceId), {
      note,
    });
  },
  revokeApproval(workspaceId: string, draftId: string) {
    return client.post<{ draft: Draft }>(
      workspacePath(`/drafts/${draftId}/revoke-approval`, workspaceId),
    );
  },
  rejectDraft(workspaceId: string, draftId: string, reason: string) {
    return client.post<{ draft: Draft }>(
      workspacePath(`/drafts/${draftId}/reject`, workspaceId),
      { reason },
    );
  },

  // ── outreach ────────────────────────────────────────────────────────────
  sendDraft(
    workspaceId: string,
    draftId: string,
    body: { approved?: boolean; sender_email?: string } = {},
  ) {
    return client.post<StageOutcome>(workspacePath(`/drafts/${draftId}/send`, workspaceId), body);
  },
  policy(workspaceId: string) {
    return client.get<{ policy: SendingPolicy }>(workspacePath("/policy", workspaceId));
  },
  savePolicy(workspaceId: string, body: Record<string, unknown>) {
    return client.put<{ policy: SendingPolicy }>(workspacePath("/policy", workspaceId), body);
  },
  suppression(workspaceId: string) {
    return client
      .get<Page<SuppressionRecord>>(workspacePath("/suppression", workspaceId), { limit: 200 })
      .then((value) => page(value, emptyPage<SuppressionRecord>()));
  },
  addSuppression(workspaceId: string, body: { email: string; reason?: string; note?: string }) {
    return client.post<{ record: SuppressionRecord }>(
      workspacePath("/suppression", workspaceId),
      body,
    );
  },
  removeSuppression(workspaceId: string, suppressionId: string) {
    return client.del<{ removed: boolean }>(
      workspacePath(`/suppression/${suppressionId}`, workspaceId),
    );
  },
  sentMessages(workspaceId: string, status?: string) {
    return client.get<{
      data: SentMessage[];
      total: number;
      counts: Record<string, number>;
    }>(workspacePath("/sent", workspaceId), { status, limit: 100 });
  },
  recordEvent(workspaceId: string, body: Record<string, unknown>) {
    return client.post<{ event: DeliveryEvent; sent_message: SentMessage }>(
      workspacePath("/events", workspaceId),
      body,
    );
  },

  // ── conversations ───────────────────────────────────────────────────────
  conversations(
    workspaceId: string,
    query?: { requires_action?: boolean; intent?: string; limit?: number },
  ) {
    return client
      .get<Page<Conversation>>(workspacePath("/conversations", workspaceId), query)
      .then((value) => page(value, emptyPage<Conversation>()));
  },
  conversation(workspaceId: string, conversationId: string) {
    return client.get<ConversationDetail>(
      workspacePath(`/conversations/${conversationId}`, workspaceId),
    );
  },
  closeConversation(workspaceId: string, conversationId: string) {
    return client.post<{ conversation: Conversation }>(
      workspacePath(`/conversations/${conversationId}/close`, workspaceId),
    );
  },
  reopenConversation(workspaceId: string, conversationId: string) {
    return client.post<{ conversation: Conversation }>(
      workspacePath(`/conversations/${conversationId}/reopen`, workspaceId),
    );
  },
  inboundReply(workspaceId: string, body: Record<string, unknown>) {
    return client.post<StageOutcome>("/v1/webhooks/inbound", body);
  },

  // ── overview + activity ─────────────────────────────────────────────────
  overview(workspaceId: string, attentionLimit = 10) {
    return client.get<Overview>(workspacePath("/overview", workspaceId), {
      attention_limit: attentionLimit,
    });
  },
  handoffs(workspaceId: string) {
    return client.get<{ handoffs: Handoff[] }>(workspacePath("/overview/handoffs", workspaceId));
  },
  activity(
    workspaceId: string,
    query?: { limit?: number; offset?: number; stage?: string; prospect_id?: string },
  ) {
    return client
      .get<Page<ActivityLog>>(workspacePath("/activity", workspaceId), query)
      .then((value) => page(value, emptyPage<ActivityLog>()));
  },
  runs(
    workspaceId: string,
    query?: { limit?: number; stage?: string; run_status?: string; subject_id?: string },
  ) {
    return client
      .get<{ data: StageRun[]; total: number; failed: StageRun[]; needs_review: StageRun[] }>(
        workspacePath("/runs", workspaceId),
        query,
      )
      .then((value) => ({
        data: value?.data ?? [],
        total: value?.total ?? 0,
        failed: value?.failed ?? [],
        needs_review: value?.needs_review ?? [],
      }));
  },
  replies(workspaceId: string, conversationId: string) {
    return client
      .get<ConversationDetail>(
        workspacePath(`/conversations/${conversationId}`, workspaceId),
      )
      .then((detail) => detail.replies);
  },
  draftVersions(workspaceId: string, draftId: string) {
    return client
      .get<DraftDetail>(workspacePath(`/drafts/${draftId}`, workspaceId))
      .then((detail) => detail.versions);
  },
  prospectStatusCounts(workspaceId: string): Promise<Record<ProspectStatus, number>> {
    return client
      .get<Overview>(workspacePath("/overview", workspaceId))
      .then((overview) => overview.counts);
  },

  // ── client setup ─────────────────────────────────────────────────────────
  /** The six named stages, open questions, blockers, and proposed blueprint. */
  setupStatus(workspaceId: string) {
    return client.get<SetupStatus>(workspacePath("/setup", workspaceId));
  },
  setupGenerate(workspaceId: string, body: Record<string, unknown>) {
    return client.post<SetupReport>(workspacePath("/setup/generate", workspaceId), body);
  },
  setupAnswers(workspaceId: string, answers: Record<string, string>) {
    return client.post<SetupReport>(workspacePath("/setup/answers", workspaceId), { answers });
  },
  /** The intake endpoint (`POST /v1/setup/client`): a client's transcript or
   * notes in, business profile + first workflow + readiness out. */
  setupClient(payload: {
    materials?: { source_ref: string; text: string }[];
    notes?: string;
  }) {
    return client.post<{
      profile: { business_name: string | null; missing: string[]; contradictions: string[] };
      workspace: { version: number; module_order: string[] };
      first_workflow: { steps: string[]; approval_gate: boolean };
      readiness: { state: string; blockers: string[]; questions: string[]; next_action: string };
    }>("/v1/setup/client", payload);
  },

  // ── factory: connect, validate, test, activate ───────────────────────────
  factoryConnections(workspaceId: string) {
    return client
      .get<{ data: FactoryConnection[]; total: number }>(
        workspacePath("/factory/connections", workspaceId),
      )
      .then((value) => value?.data ?? []);
  },
  probeConnection(workspaceId: string, connectionId: string) {
    return client
      .post<{ connection: FactoryConnection }>(
        workspacePath(`/factory/connections/${connectionId}/probe`, workspaceId),
      )
      .then((value) => value?.connection);
  },
  factoryValidation(workspaceId: string) {
    return client.get<{
      tenant_id: string;
      ready: boolean;
      failed_required: string[];
      stages: import("./types").ValidationStage[];
    }>(workspacePath("/factory/validation", workspaceId));
  },
  factoryActivation(workspaceId: string) {
    return client.get<ActivationStatus>(workspacePath("/factory/activation", workspaceId));
  },
  activateWorkspace(workspaceId: string) {
    return client.post<ActivationStatus>(
      workspacePath("/factory/activation/activate", workspaceId),
    );
  },
  factoryTest(workspaceId: string, mode: "sample" | "synthetic" = "synthetic") {
    return client.post<SafeTestReport>(workspacePath("/factory/test", workspaceId), { mode });
  },
};

export type Operations = typeof operations;
