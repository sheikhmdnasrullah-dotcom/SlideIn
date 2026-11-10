"use server";

import { revalidatePath } from "next/cache";

import { client, workspacePath } from "@/lib/api/client";
import { WORKSPACE_ID } from "@/lib/api/config";
import { requireConsoleSession } from "@/lib/auth/session";

export async function connectWebsite(formData: FormData) {
  await requireConsoleSession();
  const domain = String(formData.get("domain") ?? "").trim();
  const provider = String(formData.get("provider") ?? "native");
  if (!domain) throw new Error("Enter the public HTTPS website domain.");
  await client.post(workspacePath("/websites", WORKSPACE_ID), { domain, provider });
  revalidatePath("/settings");
}
