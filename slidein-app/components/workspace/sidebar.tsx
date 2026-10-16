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
  Search,
  Settings2,
  UserCheck,
  Wand2,
  type LucideIcon,
} from "lucide-react";

import { SECTIONS, type SectionMeta } from "@/lib/workflow/metadata";
import { SECTION_MODULES, brandInitials, safeLogoUrl } from "@/lib/workflow/tenant";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  overview: LayoutDashboard,
  profile: Settings2,
  discovery: Compass,
  research: Search,
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
  className?: string;
}) {
  const pathname = usePathname();

  const visible = (section: SectionMeta) =>
    !enabledModules ||
    enabledModules.includes(SECTION_MODULES[section.id] ?? section.id);
  const sections = GROUP_ORDER.map((group) => ({
    group,
    label: GROUP_LABELS[group],
    items: SECTIONS.filter((section) => section.group === group && visible(section)),
  })).filter((group) => group.items.length > 0);

  const displayName = brandName?.trim() || "Slidein";
  const logo = safeLogoUrl(logoUrl);

  return (
    <aside
      data-slot="sidebar"
      className={cn(
        "flex h-full w-[15rem] shrink-0 flex-col border-r border-rule bg-surface",
        className,
      )}
    >
      <div className="flex h-12 items-center gap-2 border-b border-rule px-4">
        {logo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={logo} alt="" className="size-6 rounded-xs object-contain" />
        ) : (
          <span className="flex size-6 items-center justify-center rounded-xs bg-flame-vivid font-mono text-2xs font-semibold text-on-flame">
            {brandInitials(displayName)}
          </span>
        )}
        <span className="truncate font-display-soft text-sm text-ink-strong">
          {displayName}
        </span>
      </div>

      <nav className="flex grow flex-col gap-4 overflow-y-auto px-2 py-3">
        {sections.map((group) => (
          <div key={group.group} className="flex flex-col gap-0.5">
            <span className="px-2 pb-1 font-label text-ink-faint">{group.label}</span>
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
                    "group flex items-center gap-2 rounded-sm px-2 py-1.5 text-[0.8125rem] transition-colors",
                    active
                      ? "bg-flame-wash text-flame ring-1 ring-flame-ring"
                      : "text-ink-muted hover:bg-surface-2 hover:text-ink-strong",
                  )}
                >
                  <Icon className="size-3.5 shrink-0" aria-hidden />
                  <span className="truncate">{label}</span>
                  {typeof count === "number" && count > 0 && (
                    <span className="ml-auto font-value text-2xs tabular-nums text-status-warn">
                      {count}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="flex flex-col gap-1 border-t border-rule px-4 py-3">
        <span className="font-label text-ink-faint">Workspace</span>
        <span className="font-value text-2xs text-ink-muted">{workspaceId}</span>
        <Link
          href="/contracts"
          className="rounded-xs text-2xs text-ink-faint underline decoration-rule-strong underline-offset-2 hover:text-ink-strong focus-ring"
        >
          Stage contracts
        </Link>
      </div>
    </aside>
  );
}
