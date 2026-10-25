/**
 * Server actions: every workspace mutation goes through here. Each action
 * calls the typed BFF operation with the server API key (never the browser),
 * revalidates the affected sections, and returns a result the form can show.
 * No action invents behavior: failures carry the API's own message.
 */

"use server";

import "server-only";

import { revalidatePath } from "next/cache";

import { ApiRequestError } from "./client";
import { WORKSPACE_ID } from "./config";
import { operations } from "./operations";
import type { OsintResearchResult } from "./types";

export interface ActionResult {
  ok: boolean;
  message: string;
}

function failure(error: unknown): ActionResult {
  if (error instanceof ApiRequestError) {
    return { ok: false, message: error.error.message };
  }
  if (error instanceof Error) return { ok: false, message: error.message };
  return { ok: false, message: "Unexpected failure" };
}

function str(value: FormDataEntryValue | null): string {
  return typeof value === "string" ? value.trim() : "";
}

// ── discovery ──────────────────────────────────────────────────────────────

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function parseIngestCsv(text: string): { records: Record<string, string>[]; error?: string } {
  const records: Record<string, string>[] = [];
  const lines = text.split(/\r?\n/);
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index].trim();
    if (!line || line.startsWith("#")) continue;
    const cells = line.split(",").map((cell) => cell.trim());
    if (cells.length < 2) {
      return { records: [], error: `Line ${index + 1}: need at least "email, company".` };
    }
    const [email, company, firstName = "", lastName = "", jobTitle = "", domain = ""] = cells;
    if (!EMAIL_RE.test(email)) {
      return { records: [], error: `Line ${index + 1}: "${email}" is not an email.` };
    }
    if (!company) {
      return { records: [], error: `Line ${index + 1}: company is required.` };
    }
    records.push({
      email,
      company_name: company,
      first_name: firstName,
      last_name: lastName,
      job_title: jobTitle,
      company_domain: domain,
    });
  }
  if (records.length === 0) return { records: [], error: "Nothing to ingest: add at least one line." };
  if (records.length > 500) return { records: [], error: "At most 500 rows per batch." };
  return { records };
}

export async function discoverAction(
  _prev: ActionResult,
  formData: FormData,
): Promise<ActionResult> {
  const parsed = parseIngestCsv(str(formData.get("csv")));
  if (parsed.error) return { ok: false, message: parsed.error };
  try {
    const outcome = await operations.discover(WORKSPACE_ID, {
      records: parsed.records,
      source: "manual",
      source_ref: str(formData.get("source_ref")) || "workspace ingest",
    });
    const outputs = outcome.outputs as { created?: unknown[]; duplicates?: unknown[]; skipped?: unknown[] };
    const created = outputs.created?.length ?? 0;
    const duplicates = outputs.duplicates?.length ?? 0;
    const skipped = outputs.skipped?.length ?? 0;
    revalidatePath("/discovery");
    revalidatePath("/overview");
    if (outcome.status === "failed") {
      return { ok: false, message: outcome.reason || "Ingest failed." };
    }
    return {
      ok: true,
      message: `Ingested: ${created} created, ${duplicates} duplicates, ${skipped} skipped.`,
    };
  } catch (error) {
    return failure(error);
  }
}

// ── stage triggers ─────────────────────────────────────────────────────────

async function trigger(
  label: string,
  path: string,
  call: () => Promise<{ status: string; reason: string; needs_review: string[] }>,
): Promise<ActionResult> {
  try {
    const outcome = await call();
    revalidatePath(path);
    revalidatePath("/overview");
    if (outcome.status === "failed") {
      return { ok: false, message: outcome.reason || `${label} failed.` };
    }
    const review = outcome.needs_review.length > 0 ? ` Needs review: ${outcome.needs_review.join("; ")}` : "";
    return { ok: true, message: `${label} finished.${review}` };
  } catch (error) {
    return failure(error);
  }
}

export async function researchAction(prospectId: string): Promise<ActionResult> {
  return trigger("Research", "/research", () =>
    operations.research(WORKSPACE_ID, prospectId),
  );
}

export async function qualifyAction(prospectId: string): Promise<ActionResult> {
  return trigger("Qualification", "/qualification", () =>
    operations.qualify(WORKSPACE_ID, prospectId),
  );
}

export async function personalizeAction(prospectId: string): Promise<ActionResult> {
  return trigger("Personalization", "/personalization", () =>
    operations.personalize(WORKSPACE_ID, prospectId),
  );
}

// ── osint ──────────────────────────────────────────────────────────────────

export interface OsintResearchActionResult extends ActionResult {
  data?: OsintResearchResult;
}

export async function osintAction(prospectId: string): Promise<ActionResult> {
  try {
    const outcome = await operations.runProspectOsint(WORKSPACE_ID, prospectId, {});
    revalidatePath(`/discovery/${prospectId}`);
    const failed = outcome.lookups.filter((row) => !row.ok).map((row) => row.lookup);
    if (outcome.evidence_count === 0) {
      return {
        ok: false,
        message:
          failed.length > 0
            ? `OSINT produced no evidence (failed: ${failed.join(", ")}).`
            : "OSINT produced no evidence.",
      };
    }
    const suffix = failed.length > 0 ? ` Failed: ${failed.join(", ")}.` : "";
    return {
      ok: true,
      message: `OSINT filed ${outcome.evidence_count} evidence rows (${outcome.verified_count} verified).${suffix}`,
    };
  } catch (error) {
    return failure(error);
  }
}

export async function runOsintResearchAction(
  _prev: OsintResearchActionResult,
  formData: FormData,
): Promise<OsintResearchActionResult> {
  try {
    const query = str(formData.get("query"));
    if (!query) {
      return { ok: false, message: "Enter a name, email, handle, or domain to research." };
    }
    const allowActive = formData.get("allow_active") === "on";
    const lookups = formData
      .getAll("lookups")
      .map((value) => String(value))
      .filter(Boolean);
    const data = await operations.osintResearch(WORKSPACE_ID, {
      query,
      allow_active: allowActive,
      ...(lookups.length > 0 ? { lookups } : {}),
    });
    const seconds = (data.elapsed_ms / 1000).toFixed(1);
    const detail =
      data.failed.length > 0
        ? `${data.succeeded.length}/${data.lookups.length} lookups succeeded — ${data.failed.join(", ")} failed.`
        : `${data.lookups.length} lookup${data.lookups.length === 1 ? "" : "s"} succeeded.`;
    return { ok: data.succeeded.length > 0, message: `Finished in ${seconds}s — ${detail}`, data };
  } catch (error) {
    return { ...failure(error) };
  }
}

// ── autopilot ───────────────────────────────────────────────────────────────

export async function toggleAutopilotAction(
  _prev: ActionResult,
  formData: FormData,
): Promise<ActionResult> {
  const which = str(formData.get("switch"));
  const next = str(formData.get("value")) === "true";
  if (which !== "enabled" && which !== "auto_approve" && which !== "send_enabled") {
    return { ok: false, message: "Unknown autopilot switch." };
  }
  try {
    await operations.setAutopilot(WORKSPACE_ID, { [which]: next });
    revalidatePath("/overview");
    const label =
      which === "enabled" ? "autopilot" : which === "auto_approve" ? "auto-approve" : "sending";
    return { ok: true, message: `${label} ${next ? "on" : "off"}.` };
  } catch (error) {
    return failure(error);
  }
}

export async function runAutopilotNowAction(): Promise<ActionResult> {
  try {
    const outcome = await operations.runAutopilot(WORKSPACE_ID);
    revalidatePath("/overview");
    const stats = outcome.tick.stats;
    const touched = Object.entries(stats)
      .filter(([, count]) => count > 0)
      .map(([key, count]) => `${count} ${key}`)
      .join(", ");
    if (outcome.tick.status !== "ok") {
      return { ok: false, message: `Tick ${outcome.tick.status}.${touched ? ` Did: ${touched}.` : ""}` };
    }
    return {
      ok: true,
      message: touched ? `Tick finished — ${touched}.` : "Tick finished — nothing to do.",
    };
  } catch (error) {
    return failure(error);
  }
}

// ── drafts ─────────────────────────────────────────────────────────────────

export async function approveDraftAction(
  _prev: ActionResult,
  formData: FormData,
): Promise<ActionResult> {
  const draftId = str(formData.get("draft_id"));
  if (!draftId) return { ok: false, message: "Missing draft id." };
  try {
    await operations.approveDraft(WORKSPACE_ID, draftId, str(formData.get("note")) || undefined);
    revalidatePath("/outreach");
    revalidatePath("/overview");
    return { ok: true, message: "Draft approved. It can now be sent." };
  } catch (error) {
    return failure(error);
  }
}

export async function rejectDraftAction(
  _prev: ActionResult,
  formData: FormData,
): Promise<ActionResult> {
  const draftId = str(formData.get("draft_id"));
  const reason = str(formData.get("reason"));
  if (!draftId) return { ok: false, message: "Missing draft id." };
  if (!reason) return { ok: false, message: "A reason is required to reject." };
  try {
    await operations.rejectDraft(WORKSPACE_ID, draftId, reason);
    revalidatePath("/outreach");
    revalidatePath("/overview");
    return { ok: true, message: "Draft rejected." };
  } catch (error) {
    return failure(error);
  }
}

export async function sendDraftAction(draftId: string): Promise<ActionResult> {
  try {
    await operations.sendDraft(WORKSPACE_ID, draftId);
    revalidatePath("/outreach");
    revalidatePath("/overview");
    return { ok: true, message: "Send requested. Delivery events will appear below." };
  } catch (error) {
    return failure(error);
  }
}

export async function revokeApprovalAction(draftId: string): Promise<ActionResult> {
  try {
    await operations.revokeApproval(WORKSPACE_ID, draftId);
    revalidatePath("/outreach");
    revalidatePath("/overview");
    return { ok: true, message: "Approval revoked. The draft is back to pending review." };
  } catch (error) {
    return failure(error);
  }
}

// ── suppression ────────────────────────────────────────────────────────────

export async function addSuppressionAction(
  _prev: ActionResult,
  formData: FormData,
): Promise<ActionResult> {
  const email = str(formData.get("email"));
  if (!EMAIL_RE.test(email)) return { ok: false, message: "Enter a valid email to suppress." };
  try {
    await operations.addSuppression(WORKSPACE_ID, {
      email,
      reason: str(formData.get("reason")) || "manual",
      note: str(formData.get("note")) || undefined,
    });
    revalidatePath("/outreach");
    return { ok: true, message: `${email} suppressed. It will never be sent to.` };
  } catch (error) {
    return failure(error);
  }
}

export async function removeSuppressionAction(id: string): Promise<ActionResult> {
  try {
    await operations.removeSuppression(WORKSPACE_ID, id);
    revalidatePath("/outreach");
    return { ok: true, message: "Suppression removed." };
  } catch (error) {
    return failure(error);
  }
}

// ── conversations ──────────────────────────────────────────────────────────

export async function closeConversationAction(id: string): Promise<ActionResult> {
  try {
    await operations.closeConversation(WORKSPACE_ID, id);
    revalidatePath("/conversations");
    revalidatePath("/overview");
    return { ok: true, message: "Conversation closed." };
  } catch (error) {
    return failure(error);
  }
}

export async function reopenConversationAction(id: string): Promise<ActionResult> {
  try {
    await operations.reopenConversation(WORKSPACE_ID, id);
    revalidatePath("/conversations");
    revalidatePath("/overview");
    return { ok: true, message: "Conversation reopened." };
  } catch (error) {
    return failure(error);
  }
}

// ── configuration ──────────────────────────────────────────────────────────

function stringList(value: string): string[] {
  return value.split(/[\n,]+/).map((part) => part.trim()).filter(Boolean);
}

export async function saveProfileAction(
  _prev: ActionResult,
  formData: FormData,
): Promise<ActionResult> {
  const body = {
    legal_name: str(formData.get("legal_name")),
    website_url: str(formData.get("website_url")),
    industry: str(formData.get("industry")),
    company_description: str(formData.get("company_description")),
    core_value_prop: str(formData.get("core_value_prop")),
    markets_served: stringList(str(formData.get("markets_served"))),
    target_roles: stringList(str(formData.get("target_roles"))),
    brand_voice: str(formData.get("brand_voice")),
    reason: str(formData.get("reason")) || "workspace update",
  };
  if (!body.legal_name || !body.website_url || !body.industry) {
    return { ok: false, message: "Legal name, website, and industry are required." };
  }
  try {
    await operations.saveProfile(WORKSPACE_ID, body);
    revalidatePath("/profile");
    revalidatePath("/overview");
    return { ok: true, message: "Business profile saved as a new version." };
  } catch (error) {
    return failure(error);
  }
}

export async function saveOfferAction(
  _prev: ActionResult,
  formData: FormData,
): Promise<ActionResult> {
  const body = {
    name: str(formData.get("name")),
    summary: str(formData.get("summary")),
    pain_points_solved: stringList(str(formData.get("pain_points_solved"))),
    target_persona: str(formData.get("target_persona")),
    proof_points: stringList(str(formData.get("proof_points"))),
  };
  if (!body.name || !body.summary) {
    return { ok: false, message: "Offer name and summary are required." };
  }
  try {
    await operations.saveOffer(WORKSPACE_ID, body);
    revalidatePath("/profile");
    return { ok: true, message: "Offer saved." };
  } catch (error) {
    return failure(error);
  }
}

export async function saveIcpAction(
  _prev: ActionResult,
  formData: FormData,
): Promise<ActionResult> {
  const threshold = Number(str(formData.get("qualify_threshold")) || "70");
  const body = {
    name: str(formData.get("name")),
    industries: stringList(str(formData.get("industries"))),
    company_size_min: Number(str(formData.get("company_size_min")) || "1"),
    company_size_max: Number(str(formData.get("company_size_max")) || "5000"),
    geographies: stringList(str(formData.get("geographies"))),
    target_roles: stringList(str(formData.get("target_roles"))),
    required_signals: stringList(str(formData.get("required_signals"))),
    exclusion_keywords: stringList(str(formData.get("exclusion_keywords"))),
    qualify_threshold: Number.isFinite(threshold) ? threshold : 70,
  };
  if (!body.name) return { ok: false, message: "ICP name is required." };
  try {
    await operations.saveIcp(WORKSPACE_ID, body);
    revalidatePath("/profile");
    return { ok: true, message: "ICP saved." };
  } catch (error) {
    return failure(error);
  }
}

// ── white-label ────────────────────────────────────────────────────────────

export async function saveBrandingAction(
  _prev: ActionResult,
  formData: FormData,
): Promise<ActionResult> {
  const body: Record<string, unknown> = {
    business_name: str(formData.get("business_name")),
    logo_url: str(formData.get("logo_url")),
    favicon_url: str(formData.get("favicon_url")),
    email_from_name: str(formData.get("email_from_name")),
    custom_domain: str(formData.get("custom_domain")),
    colors: {
      primary: str(formData.get("color_primary")),
      surface: str(formData.get("color_surface")),
      ink: str(formData.get("color_ink")),
    },
  };
  try {
    await operations.saveBranding(WORKSPACE_ID, body);
    revalidatePath("/profile");
    revalidatePath("/", "layout");
    return { ok: true, message: "Branding saved. The workspace now wears it." };
  } catch (error) {
    return failure(error);
  }
}

export async function saveModulesAction(
  _prev: ActionResult,
  formData: FormData,
): Promise<ActionResult> {
  const enabled = formData.getAll("enabled").map((value) => String(value));
  try {
    await operations.saveModules(WORKSPACE_ID, { enabled });
    revalidatePath("/profile");
    revalidatePath("/", "layout");
    return { ok: true, message: "Modules updated." };
  } catch (error) {
    return failure(error);
  }
}

export async function applyTemplateAction(
  _prev: ActionResult,
  formData: FormData,
): Promise<ActionResult> {
  const templateId = str(formData.get("template_id"));
  if (!templateId) return { ok: false, message: "Choose a template first." };
  try {
    const effective = await operations.applyTemplate(WORKSPACE_ID, {
      template_id: templateId,
    });
    revalidatePath("/profile");
    revalidatePath("/", "layout");
    const label = effective.template?.label ?? templateId;
    return { ok: true, message: `Applied "${label}". Your existing settings were kept.` };
  } catch (error) {
    return failure(error);
  }
}
