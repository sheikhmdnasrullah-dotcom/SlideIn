import type * as React from "react";
import type { Metadata } from "next";

import "./globals.css";
import { Providers } from "@/components/providers/query-provider";
import { WORKSPACE_ID } from "@/lib/api/config";

export const metadata: Metadata = {
  title: "Slidein — client workspace",
  description:
    "Find the right people. Understand their business. Reach out personally. Start more conversations.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full">
        <Providers>
          <div data-workspace={WORKSPACE_ID} className="flex h-full min-h-0">
            {children}
          </div>
        </Providers>
      </body>
    </html>
  );
}
