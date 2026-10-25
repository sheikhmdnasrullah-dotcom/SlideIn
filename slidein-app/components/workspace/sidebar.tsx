"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity as ActivityIcon,
  Compass,
  FileText,
  Inbox,
  LayoutDashboard,
  MoreHorizontal,
  ScanSearch,
  Search,
  Settings2,
  UserCheck,
  Wand2,
  type LucideIcon,
} from "lucide-react";

import { SECTIONS, type SectionMeta } from "@/lib/workflow/metadata";
import { SECTION_MODULES, brandInitials, safeLogoUrl } from "@/lib/workflow/tenant";
import { GlossTile } from "@/components/system/gloss-tile";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  overview: LayoutDashboard,
  profile: Settings2,
  discovery: Compass,
  research: Search,
  osint: ScanSearch,
  qualification: UserCheck,
  personalization: Wand2,
  outreach: FileText,
  conversations: Inbox,
  activity: ActivityIcon,
};

const GROUP_LABELS: Record<SectionMeta["group"], string> = {
  setup: "Setup",
  pipeline: "Workflow",
  history: "History",
};

const GROUP_ORDER: SectionMeta["group"][] = ["setup", "pipeline", "history"];

/**
 * WorkflowSidebar: the persistent navigation, ordered by the workflow itself.
 * The nav is not a menu — it is the stage order, so a link always means "go
 * to the next stage that works on this record".
 */
export function WorkflowSidebar({
  attentionCounts,
  workspaceId,
  brandName,
  logoUrl,
  enabledModules,
  sectionLabels,
  moduleOrder,
  className,
}: {
  attentionCounts?: Record<string, number>;
  workspaceId: string;
  brandName?: string;
  logoUrl?: string | null;
  /** When present, sections whose module is off are hidden (API still enforces). */
  enabledModules?: string[] | null;
  /** Template terminology overrides for section labels. */
  sectionLabels?: Record<string, string> | null;
  /** Saved adaptive workspace order (module ids); sorts sections within groups. */
  moduleOrder?: string[] | null;
  className?: string;
}) {
  const pathname = usePathname();

  const visible = (section: SectionMeta) =>
    !enabledModules ||
    enabledModules.includes(SECTION_MODULES[section.id] ?? section.id);
  const sectionRank = (section: SectionMeta) => {
    if (!moduleOrder?.length) return Number.MAX_SAFE_INTEGER;
    const module = SECTION_MODULES[section.id] ?? section.id;
    const idx = moduleOrder.indexOf(module);
    return idx === -1 ? Number.MAX_SAFE_INTEGER : idx;
  };
  const sections = GROUP_ORDER.map((group) => ({
    group,
    label: GROUP_LABELS[group],
    items: SECTIONS.filter((section) => section.group === group && visible(section))
      .map((section, i) => ({ section, i }))
      .sort((a, b) =>
        sectionRank(a.section) - sectionRank(b.section) || a.i - b.i)
      .map((x) => x.section),
  })).filter((group) => group.items.length > 0);

  const displayName = brandName?.trim() || "Slidein";
  const logo = safeLogoUrl(logoUrl);
  const qualifier = displayName.includes(" ") ? displayName.split(/\s+/).slice(1).join(" ") : "";

  return (
    <aside
      data-slot="sidebar"
      className={cn(
        "flex h-full w-[264px] shrink-0 flex-col border-r border-rule bg-sidebar-fill",
        className,
      )}
    >
      <div className="flex items-center gap-3 px-4 pt-5 pb-4">
        {logo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={logo} alt="" className="size-9 rounded-[11px] object-contain" />
        ) : (
          <GlossTile size={36} float={false}>
            <span className="font-sans text-[13px] font-semibold text-ink-strong">
              {brandInitials(displayName)}
            </span>
          </GlossTile>
        )}
        <span className="truncate font-sans text-[15px] leading-[22px] font-semibold text-ink-strong">
          {displayName}
        </span>
        <span className="truncate font-label text-ink-faint">
          {qualifier}
        </span>
      </div>

      <nav className="flex grow flex-col gap-4 overflow-y-auto px-3 py-2">
        {sections.map((group) => (
          <div key={group.group} className="flex flex-col gap-0.5">
            <span className="px-3 pt-2 pb-2 font-label text-ink-faint">{group.label}</span>
            {group.items.map((section) => {
              const Icon = ICONS[section.id] ?? MoreHorizontal;
              const active =
                pathname === section.href || pathname.startsWith(`${section.href}/`);
              const count = attentionCounts?.[section.id];
              const label = sectionLabels?.[section.id]?.trim() || section.label;
              return (
                <Link
                  key={section.id}
                  href={section.href}
                  title={section.description}
                  data-active={active || undefined}
                  className={cn(
                    "group flex h-10 items-center gap-3 rounded-[12px] px-3 font-sans text-sm font-medium transition-colors duration-[220ms",
                    active
                      ? "bg-flame-wash text-ink-strong"
                      : "text-ink-muted hover:bg-hover-tint hover:text-ink-strong",
                  )}
                >
                  <Icon
                    className={cn(
                      "size-[18px] shrink-0",
                      active ? "text-ink-strong" : "text-ink-muted",
                    )}
                    aria-hidden
                  />
                  <span className="truncate">{label}</span>
                  {typeof count === "number" && count > 0 && (
                    <span
                      className="ml-auto font-value text-xs tabular-nums text-status-warn"
                      data-metric
                    >
                      {count}
                    </span>
                  )}
                  {active && (
                    <span
                      aria-hidden
                      className={cn(
                        "size-1.5 shrink-0 rounded-full bg-flame-vivid",
                        typeof count === "number" && count > 0 ? "" : "ml-auto",
                      )}
                    />
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="flex flex-col gap-1 border-t border-rule px-4 py-4">
        <span className="font-label text-ink-faint">Workspace</span>
        <span className="font-code text-xs text-ink-muted">{workspaceId}</span>
        <Link
          href="/contracts"
          className="w-fit rounded-xs text-xs text-ink-faint underline decoration-rule-strong underline-offset-2 hover:text-ink-strong focus-ring"
        >
          Stage contracts
        </Link>
      </div>
    </aside>
  );
}
