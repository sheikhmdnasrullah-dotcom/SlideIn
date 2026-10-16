import { PageHeader } from "@/components/system/page-header";
import { Section } from "@/components/system/section";
import { Surface } from "@/components/system/surface";
import { EmptyState } from "@/components/system/states";
import { StatusBadge } from "@/components/system/status-badge";
import { formatDate } from "@/components/system/format";
import { PageFailure } from "@/components/workspace/page-failure";
import {
  BrandingForm,
  IcpForm,
  ModulesForm,
  OfferForm,
  ProfileForm,
  TemplateForm,
} from "@/components/workspace/action-forms";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";

export const dynamic = "force-dynamic";

export default async function ProfilePage() {
  let profile;
  let branding;
  let modules;
  let catalog;
  let tenantTemplate;
  try {
    [profile, branding, modules, catalog, tenantTemplate] = await Promise.all([
      operations.profile(WORKSPACE_ID),
      operations.branding(WORKSPACE_ID),
      operations.modules(WORKSPACE_ID),
      operations.templates(),
      operations.tenantTemplate(WORKSPACE_ID),
    ]);
  } catch (error) {
    return <PageFailure error={error} module="settings" />;
  }

  return (
    <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-6">
      <PageHeader
        eyebrow="Setup · business profile"
        title="Business Profile"
        meta={
          profile.profile
            ? `v${profile.profile.version} · readiness ${profile.readiness.overall_score}%`
            : "not configured"
        }
      />

      <Section
        title="Readiness"
        description="What the workflow needs before it can run end to end."
        tone="raised"
        divided
        bodyClassName="px-6 pt-4 pb-6"
        meta={profile.readiness.is_ready_for_activation ? "ready" : "not ready"}
      >
        <div className="flex flex-col gap-1.5">
          {profile.readiness.checklist.map((item) => (
            <div key={item.key} className="flex items-baseline gap-3 text-2xs">
              <StatusBadge
                tone={item.status === "ready" || item.status === "pass" || item.status === "ok" ? "live" : item.status === "warn" ? "warn" : item.status === "fail" ? "danger" : "neutral"}
                label={item.status}
              />
              <span className="text-ink-muted">{item.message}</span>
            </div>
          ))}
          {profile.readiness.checklist.length === 0 && (
            <p className="text-2xs text-ink-muted">No checklist items.</p>
          )}
        </div>
      </Section>

      <Section
        title="Profile"
        description="The versioned business configuration handed to Discovery. Saving creates a new version; downstream records keep pointing at the version that authorized them."
      >
        <Surface variant="raised">
          <ProfileForm profile={profile.profile} />
        </Surface>
      </Section>

      <Section title="Offers" meta={`${profile.offers.length} offers`}>
        {profile.offers.length > 0 && (
          <Surface variant="raised" className="mb-4 divide-y divide-rule">
            {profile.offers.map((offer) => (
              <div key={offer.id} className="px-4 py-2.5">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-[0.8125rem] text-ink-strong">{offer.name}</span>
                  <span className="text-2xs text-ink-muted">v{offer.version}</span>
                </div>
                <p className="max-w-prose pt-1 text-2xs leading-relaxed text-ink-muted">{offer.summary}</p>
              </div>
            ))}
          </Surface>
        )}
        <Surface variant="raised">
          <OfferForm />
        </Surface>
      </Section>

      <Section title="Ideal customer profiles" meta={`${profile.icps.length} ICPs`}>
        {profile.icps.length > 0 && (
          <Surface variant="raised" className="mb-4 divide-y divide-rule">
            {profile.icps.map((icp) => (
              <div key={icp.id} className="px-4 py-2.5">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-[0.8125rem] text-ink-strong">{icp.name}</span>
                  <span className="text-2xs text-ink-muted">
                    threshold {icp.qualify_threshold} · v{icp.version}
                  </span>
                </div>
                <p className="max-w-prose pt-1 text-2xs leading-relaxed text-ink-muted">
                  {icp.industries.join(", ") || "No industries listed."}
                </p>
              </div>
            ))}
          </Surface>
        )}
        <Surface variant="raised">
          <IcpForm />
        </Surface>
      </Section>

      <Section
        title="Branding"
        description="How this workspace presents itself: sidebar name, logo, theme, and sender identity. Changes apply immediately."
      >
        <Surface variant="raised">
          <BrandingForm branding={branding.branding} />
        </Surface>
        <p className="pt-3 text-2xs text-ink-muted">
          Custom domain: {branding.branding.custom_domain || "none"}
          {branding.branding.custom_domain &&
            (branding.branding.domain_verified ? " · verified" : " · unverified")}
        </p>
      </Section>

      <Section
        title="Modules"
        description="Switch workflow sections on or off. The API enforces this too — a disabled module refuses requests, it is not just hidden."
        meta={`source: ${modules.source ?? "default"}`}
      >
        <Surface variant="raised">
          <ModulesForm registry={modules.registry} enabled={modules.enabled} />
        </Surface>
      </Section>

      <Section
        title="Workspace template"
        description="A versioned starting point for wording and layout. Applying only fills in what this workspace has not customized — your settings, brand, and data are never overwritten."
        meta={tenantTemplate.template ? `${tenantTemplate.template.label} · v${tenantTemplate.template.version}` : "none applied"}
      >
        <Surface variant="raised">
          <TemplateForm catalog={catalog.templates} current={tenantTemplate.template} />
        </Surface>
        {Object.keys(tenantTemplate.terminology.sections ?? {}).length > 0 && (
          <Surface variant="inset" className="mt-4 px-4 py-2">
            <h3 className="font-label pb-1 text-ink-muted">Effective wording</h3>
            <div className="flex flex-wrap gap-x-6 gap-y-1">
              {Object.entries(tenantTemplate.terminology.sections).map(([section, label]) => (
                <span key={section} className="text-2xs text-ink-muted">
                  <span className="font-code text-ink-muted">{section}</span> → {label}
                </span>
              ))}
            </div>
          </Surface>
        )}
      </Section>

      <Section title="Configuration versions" meta={`${profile.config_versions.length} versions`}>
        {profile.config_versions.length === 0 ? (
          <Surface variant="raised">
            <EmptyState icon="document" title="No versions recorded" description="Saving configuration creates immutable versions here." />
          </Surface>
        ) : (
          <Surface variant="inset" className="divide-y divide-rule px-4 py-1">
            {profile.config_versions.slice(0, 25).map((version) => (
              <div key={version.id} className="flex items-baseline justify-between gap-3 py-1.5 text-2xs">
                <span className="font-medium text-ink-strong">
                  {version.entity_type} · v{version.version}
                </span>
                <span className="text-ink-muted">
                  {version.actor}{version.reason ? ` · ${version.reason}` : ""} · {formatDate(version.created_at)}
                </span>
              </div>
            ))}
          </Surface>
        )}
      </Section>
    </div>
  );
}
