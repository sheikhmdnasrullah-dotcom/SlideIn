"use client";

/**
 * Workspace action forms: the only client components that mutate. Every
 * mutation shows its own result inline — success or the API's own failure
 * message — so no action can fail silently.
 */

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/form";
import type {
  ActionResult,
} from "@/lib/api/actions";
import {
  addSuppressionAction,
  applyTemplateAction,
  approveDraftAction,
  discoverAction,
  rejectDraftAction,
  saveBrandingAction,
  saveIcpAction,
  saveModulesAction,
  saveOfferAction,
  saveProfileAction,
} from "@/lib/api/actions";
import type {
  Branding,
  BusinessProfile,
  ModuleMeta,
  TemplatePointer,
  TemplateSummary,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

const IDLE: ActionResult = { ok: true, message: "" };

function ResultLine({ result }: { result: ActionResult }) {
  if (!result.message) return null;
  return (
    <p
      role={result.ok ? "status" : "alert"}
      className={cn(
        "text-2xs leading-relaxed",
        result.ok ? "text-status-live" : "text-status-danger",
      )}
    >
      {result.message}
    </p>
  );
}

/** One-click server-action trigger with inline result (research, send…). */
export function TriggerButton({
  invoke,
  id,
  label,
  variant = "outline",
  size = "sm",
  confirm,
  className,
}: {
  invoke: (id: string) => Promise<ActionResult>;
  id: string;
  label: string;
  variant?: "default" | "secondary" | "outline" | "ghost" | "danger" | "quiet";
  size?: "sm" | "md" | "lg" | "icon" | "icon-sm";
  confirm?: string;
  className?: string;
}) {
  const [pending, startTransition] = React.useTransition();
  const [result, setResult] = React.useState<ActionResult>(IDLE);
  return (
    <span className={cn("inline-flex flex-col items-start gap-1", className)}>
      <Button
        type="button"
        variant={variant}
        size={size}
        disabled={pending}
        onClick={() => {
          if (confirm && !window.confirm(confirm)) return;
          startTransition(async () => setResult(await invoke(id)));
        }}
      >
        {pending ? "Working…" : label}
      </Button>
      {result.message && <ResultLine result={result} />}
    </span>
  );
}

function useFormAction(
  action: (prev: ActionResult, form: FormData) => Promise<ActionResult>,
) {
  return React.useActionState(action, IDLE);
}

// ── discovery ingest ───────────────────────────────────────────────────────

export function IngestForm() {
  const [result, formAction, pending] = useFormAction(discoverAction);
  return (
    <form action={formAction} className="flex flex-col gap-3">
      <Field
        label="Prospects (CSV, one per line)"
        hint='Format: email, company, first name, last name, title, domain. Lines starting with # are ignored.'
      >
        <Textarea
          name="csv"
          required
          rows={6}
          placeholder={"ada@analytical.example, Analytical Engines, Ada, Lovelace, Founder, analytical.example"}
          className="font-mono text-xs"
        />
      </Field>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Source reference" className="min-w-48 grow">
          <Input name="source_ref" placeholder="e.g. founder list 2026-10" />
        </Field>
        <Button type="submit" disabled={pending}>
          {pending ? "Ingesting…" : "Ingest prospects"}
        </Button>
      </div>
      <ResultLine result={result} />
    </form>
  );
}

// ── draft review ───────────────────────────────────────────────────────────

export function ApproveForm({ draftId }: { draftId: string }) {
  const [result, formAction, pending] = useFormAction(approveDraftAction);
  return (
    <form action={formAction} className="flex flex-col gap-2">
      <input type="hidden" name="draft_id" value={draftId} />
      <Field label="Approval note (optional)">
        <Input name="note" placeholder="Why this is good to send" />
      </Field>
      <div>
        <Button type="submit" disabled={pending}>
          {pending ? "Approving…" : "Approve draft"}
        </Button>
      </div>
      <ResultLine result={result} />
    </form>
  );
}

export function RejectForm({ draftId }: { draftId: string }) {
  const [result, formAction, pending] = useFormAction(rejectDraftAction);
  return (
    <form action={formAction} className="flex flex-col gap-2">
      <input type="hidden" name="draft_id" value={draftId} />
      <Field label="Reason (required)">
        <Input name="reason" required placeholder="What is wrong with this draft" />
      </Field>
      <div>
        <Button type="submit" variant="danger" disabled={pending}>
          {pending ? "Rejecting…" : "Reject draft"}
        </Button>
      </div>
      <ResultLine result={result} />
    </form>
  );
}

// ── suppression ────────────────────────────────────────────────────────────

export function SuppressionForm() {
  const [result, formAction, pending] = useFormAction(addSuppressionAction);
  return (
    <form action={formAction} className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Email">
          <Input name="email" type="email" required placeholder="never@example.com" />
        </Field>
        <Field label="Reason">
          <Input name="reason" placeholder="manual" />
        </Field>
        <Field label="Note">
          <Input name="note" placeholder="Why suppressed" />
        </Field>
      </div>
      <div>
        <Button type="submit" variant="secondary" disabled={pending}>
          {pending ? "Suppressing…" : "Suppress email"}
        </Button>
      </div>
      <ResultLine result={result} />
    </form>
  );
}

// ── configuration ──────────────────────────────────────────────────────────

export function ProfileForm({ profile }: { profile: BusinessProfile | null }) {
  const [result, formAction, pending] = useFormAction(saveProfileAction);
  return (
    <form action={formAction} className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Legal name">
          <Input name="legal_name" required defaultValue={profile?.legal_name ?? ""} />
        </Field>
        <Field label="Website URL">
          <Input name="website_url" required defaultValue={profile?.website_url ?? ""} />
        </Field>
        <Field label="Industry">
          <Input name="industry" required defaultValue={profile?.industry ?? ""} />
        </Field>
        <Field label="Brand voice">
          <Input name="brand_voice" defaultValue={profile?.brand_voice ?? ""} />
        </Field>
      </div>
      <Field label="Company description">
        <Textarea name="company_description" rows={2} defaultValue={profile?.company_description ?? ""} />
      </Field>
      <Field label="Core value proposition">
        <Textarea name="core_value_prop" rows={2} defaultValue={profile?.core_value_prop ?? ""} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Markets served (comma separated)">
          <Input name="markets_served" defaultValue={(profile?.markets_served ?? []).join(", ")} />
        </Field>
        <Field label="Target roles (comma separated)">
          <Input name="target_roles" defaultValue={(profile?.target_roles ?? []).join(", ")} />
        </Field>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Change reason" className="min-w-48 grow">
          <Input name="reason" placeholder="workspace update" />
        </Field>
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : profile ? "Save new version" : "Create profile"}
        </Button>
      </div>
      <ResultLine result={result} />
    </form>
  );
}

export function OfferForm() {
  const [result, formAction, pending] = useFormAction(saveOfferAction);
  return (
    <form action={formAction} className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Offer name">
          <Input name="name" required placeholder="e.g. Free acquisition audit" />
        </Field>
        <Field label="Target persona">
          <Input name="target_persona" placeholder="e.g. Mortgage officers" />
        </Field>
      </div>
      <Field label="Summary">
        <Textarea name="summary" required rows={2} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Pain points solved (comma separated)">
          <Input name="pain_points_solved" />
        </Field>
        <Field label="Proof points (comma separated)">
          <Input name="proof_points" />
        </Field>
      </div>
      <div>
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : "Save offer"}
        </Button>
      </div>
      <ResultLine result={result} />
    </form>
  );
}

export function IcpForm() {
  const [result, formAction, pending] = useFormAction(saveIcpAction);
  return (
    <form action={formAction} className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="ICP name">
          <Input name="name" required placeholder="e.g. Scaling brokerages" />
        </Field>
        <Field label="Qualify threshold (0–100)">
          <Input name="qualify_threshold" type="number" min={0} max={100} defaultValue="70" />
        </Field>
        <Field label="Industries (comma separated)">
          <Input name="industries" />
        </Field>
        <Field label="Geographies (comma separated)">
          <Input name="geographies" />
        </Field>
        <Field label="Min company size">
          <Input name="company_size_min" type="number" min={1} defaultValue="1" />
        </Field>
        <Field label="Max company size">
          <Input name="company_size_max" type="number" min={1} defaultValue="5000" />
        </Field>
        <Field label="Target roles (comma separated)">
          <Input name="target_roles" />
        </Field>
        <Field label="Required signals (comma separated)">
          <Input name="required_signals" />
        </Field>
      </div>
      <Field label="Exclusion keywords (comma separated)">
        <Input name="exclusion_keywords" />
      </Field>
      <div>
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : "Save ICP"}
        </Button>
      </div>
      <ResultLine result={result} />
    </form>
  );
}

// ── white-label ────────────────────────────────────────────────────────────

export function BrandingForm({ branding }: { branding: Branding }) {
  const [result, formAction, pending] = useFormAction(saveBrandingAction);
  return (
    <form action={formAction} className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Business name">
          <Input name="business_name" defaultValue={branding.business_name} />
        </Field>
        <Field label="Email from-name">
          <Input name="email_from_name" defaultValue={branding.email_from_name} />
        </Field>
        <Field label="Logo URL (https)">
          <Input name="logo_url" type="url" defaultValue={branding.logo_url} />
        </Field>
        <Field label="Favicon URL (https)">
          <Input name="favicon_url" type="url" defaultValue={branding.favicon_url} />
        </Field>
        <Field label="Custom domain">
          <Input name="custom_domain" defaultValue={branding.custom_domain} />
        </Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Primary">
            <Input name="color_primary" defaultValue={branding.colors.primary} />
          </Field>
          <Field label="Surface">
            <Input name="color_surface" defaultValue={branding.colors.surface} />
          </Field>
          <Field label="Ink">
            <Input name="color_ink" defaultValue={branding.colors.ink} />
          </Field>
        </div>
      </div>
      <div>
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : "Save branding"}
        </Button>
      </div>
      <ResultLine result={result} />
    </form>
  );
}

export function TemplateForm({
  catalog,
  current,
}: {
  catalog: TemplateSummary[];
  current: TemplatePointer | null;
}) {
  const [result, formAction, pending] = useFormAction(applyTemplateAction);
  return (
    <form action={formAction} className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <Field
          label="Workspace template"
          hint={
            current
              ? `Current: ${current.label ?? current.id} (v${current.version ?? "?"})`
              : "No template applied yet."
          }
          className="min-w-64 grow"
        >
          <Select name="template_id" defaultValue={current?.id ?? ""} required>
            <option value="" disabled>
              Choose a template…
            </option>
            {catalog.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.label} (v{entry.version})
              </option>
            ))}
          </Select>
        </Field>
        <Button type="submit" disabled={pending}>
          {pending ? "Applying…" : "Apply template"}
        </Button>
      </div>
      <ResultLine result={result} />
    </form>
  );
}

export function ModulesForm({
  registry,
  enabled,
}: {
  registry: ModuleMeta[];
  enabled: string[];
}) {
  const [result, formAction, pending] = useFormAction(saveModulesAction);
  return (
    <form action={formAction} className="flex flex-col gap-3">
      <div className="grid gap-2 sm:grid-cols-3">
        {registry.map((module) => (
          <Checkbox
            key={module.id}
            name="enabled"
            value={module.id}
            defaultChecked={enabled.includes(module.id)}
            disabled={module.id === "settings" || pending}
            label={
              <span>
                {module.label}
                {module.id === "settings" ? " (always on)" : ""}
              </span>
            }
          />
        ))}
      </div>
      {/* settings is load-bearing: always submitted so it can never drop. */}
      <input type="hidden" name="enabled" value="settings" />
      <div>
        <Button type="submit" variant="secondary" disabled={pending}>
          {pending ? "Saving…" : "Save modules"}
        </Button>
      </div>
      <ResultLine result={result} />
    </form>
  );
}
