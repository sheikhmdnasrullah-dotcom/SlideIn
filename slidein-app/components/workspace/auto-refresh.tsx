"use client";

/**
 * AutoRefresh: revalidates the current server-rendered page on an interval
 * so background work (the Autopilot loop, inbound replies) shows up without
 * the client doing anything. Pauses while the tab is hidden — a sleeping
 * client must not pay for polling.
 */

import * as React from "react";
import { useRouter } from "next/navigation";

export function AutoRefresh({ seconds = 60 }: { seconds?: number }) {
  const router = useRouter();
  React.useEffect(() => {
    const timer = setInterval(() => {
      if (!document.hidden) router.refresh();
    }, Math.max(5, seconds) * 1000);
    return () => clearInterval(timer);
  }, [router, seconds]);
  return null;
}
