import { NextResponse } from "next/server";

import { ApiRequestError, operations } from "@/lib/api/client";
import { WORKSPACE_ID } from "@/lib/api/config";


async function get(request: Request, { params }: { params: Promise<Record<string, string>> }) {
  try {
    const {prospectId} = await params;
    return NextResponse.json(await operations.prospect(WORKSPACE_ID, prospectId));
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


export const GET = get;
