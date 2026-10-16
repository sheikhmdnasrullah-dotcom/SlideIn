import { NextResponse } from "next/server";

import { ApiRequestError } from "@/lib/api/client";
import { operations } from "@/lib/api/operations";
import { WORKSPACE_ID } from "@/lib/api/config";


async function post(request: Request) {
  try {
    const body = await request.json().catch(() => ({}));
    return NextResponse.json(await operations.saveOffer(WORKSPACE_ID, body));
  } catch (error) {
    if (error instanceof ApiRequestError) {
      return NextResponse.json({ error: error.error }, { status: error.status });
    }
    return NextResponse.json(
      {
        error: {
          code: "unknown",
          message: error instanceof Error ? error.message : "Unexpected failure",
          recovery_action: "retry_stage",
          retryable: true,
          details: {},
        },
      },
      { status: 500 },
    );
  }
}


export const POST = post;
