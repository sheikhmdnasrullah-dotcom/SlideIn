/**
 * CLIENT WORDMARK
 * ---------------------------------------------------------------------------
 * The workspace identity is a live-text wordmark, not an icon mark. It
 * renders the client's business name in the accent axis colour, so it
 * inverts with the theme the same way the SlideIn wordmark does. The
 * qualifier is the remainder of the business name (or the domain parent).
 *
 * When no client is configured the caller passes the SlideIn fallback
 * values and this component renders identically to LogoWordmark.
 */

import { cn } from "@/lib/utils";

export function ClientWordmark({
  className,
  size = "15px",
  name = "SlideIn",
  qualifier = "Venture",
}: {
  className?: string;
  size?: string | number;
  name?: string;
  qualifier?: string;
}) {
  return (
    <span
      className={cn("client-wordmark", className)}
      style={{ fontSize: size }}
    >
      <span className="client-wordmark-name" aria-hidden>
        {name}
      </span>
      <span className="client-wordmark-sub" aria-hidden>
        {qualifier}
      </span>
      <span className="sr-only">
        {name} {qualifier}
      </span>
    </span>
  );
}

export default ClientWordmark;