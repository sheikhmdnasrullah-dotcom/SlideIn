import { Inbox, Search, FileText, Send, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * GlossTile: the marketing tile language, verbatim construction
 * (marketing-site/components/Hero/FloatingTiles.tsx): square, 28% radius,
 * white → #F4F4F5 gradient face, inner highlight, 4px #E9E9EB lip
 * underneath, object shadow, slight rotation. One small accent dot on
 * the icon. Decorative: always aria-hidden, never any text.
 */
const ICONS = {
  search: Search,
  inbox: Inbox,
  document: FileText,
  send: Send,
} satisfies Record<string, LucideIcon>;

export type GlossTileIcon = keyof typeof ICONS;

export function GlossTile({
  icon = "inbox",
  size = 88,
  float = true,
  children,
  className,
}: {
  icon?: GlossTileIcon;
  size?: number;
  float?: boolean;
  /** Replaces the icon slot (e.g. an existing logo or avatar). */
  children?: React.ReactNode;
  className?: string;
}) {
  const Icon = ICONS[icon];
  return (
    <div aria-hidden className={cn("relative", float && "tile-float", className)}>
      <div
        className="relative"
        style={{
          width: size,
          height: size,
          transform: float ? undefined : "rotate(-6deg)",
        }}
      >
        <div
          className="absolute inset-0 translate-y-[4px]"
          style={{ borderRadius: "28%", background: "var(--color-paper-200)" }}
        />
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{
            borderRadius: "28%",
            background:
              "linear-gradient(145deg, rgba(255,255,255,1) 0%, rgba(244,244,245,1) 100%)",
            border: "1px solid rgba(10,10,10,0.03)",
            boxShadow:
              "inset 0 1px 0 rgba(255,255,255,1), inset 0 -2px 4px rgba(0,0,0,0.04), var(--shadow-tile)",
          }}
        >
          {children ?? (
            <span className="relative flex items-center justify-center" style={{ width: "46%", height: "46%" }}>
              <Icon
                className="h-full w-full text-ink-strong"
                strokeWidth={1.5}
                aria-hidden
              />
              <span
                className="absolute right-[8%] top-[8%] rounded-full bg-flame-vivid"
                style={{ width: size * 0.07, height: size * 0.07 }}
              />
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
