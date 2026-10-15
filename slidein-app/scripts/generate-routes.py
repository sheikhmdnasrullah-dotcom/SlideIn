"""
Generate the Next.js route handlers for the Slidein client workspace.

Each handler is a thin proxy onto `lib/api/operations.ts` — workspace
scoping and the API key stay server-side. Keeping every route in one
pattern means no handler may invent its own error shape: a failure always
comes back as the backend's `{error: {...}}` envelope, code, recovery
action and retryability intact.

Run from the repo root:  python3 slidein-app/scripts/generate-routes.py
"""

from __future__ import annotations

import textwrap
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
DYNAMIC_KEYS = ["prospectId", "draftId", "conversationId", "offerId", "icpId", "suppressionId"]

#: (route path, {method: operations call})
ROUTES: list[tuple[str, dict[str, str]]] = [
    # reads ---------------------------------------------------------------
    ("overview", {"GET": "operations.overview(WORKSPACE_ID, Number(search.get('attention_limit')) || 10)"}),
    ("handoffs", {"GET": "operations.handoffs(WORKSPACE_ID)"}),
    ("profile", {
        "GET": "operations.profile(WORKSPACE_ID)",
        "POST": "operations.saveProfile(WORKSPACE_ID, body)",
    }),
    ("prospects", {"GET": "operations.prospects(WORKSPACE_ID, Object.fromEntries(search))"}),
    ("drafts", {"GET": "operations.drafts(WORKSPACE_ID, Object.fromEntries(search))"}),
    ("qualifications", {
        "GET": "operations.qualifications(WORKSPACE_ID, search.get('qualified_only') === 'true')"
    }),
    ("sent", {"GET": "operations.sentMessages(WORKSPACE_ID, search.get('status') ?? undefined)"}),
    ("conversations", {
        "GET": (
            "operations.conversations(WORKSPACE_ID, {\n"
            "        requires_action: search.get('requires_action') === 'true' ? true : undefined,\n"
            "        intent: search.get('intent') ?? undefined,\n"
            "      })"
        )
    }),
    ("activity", {"GET": "operations.activity(WORKSPACE_ID, Object.fromEntries(search))"}),
    ("runs", {"GET": "operations.runs(WORKSPACE_ID, Object.fromEntries(search))"}),
    ("suppression", {
        "GET": "operations.suppression(WORKSPACE_ID)",
        "POST": "operations.addSuppression(WORKSPACE_ID, body)",
    }),
    ("policy", {
        "GET": "operations.policy(WORKSPACE_ID)",
        "PUT": "operations.savePolicy(WORKSPACE_ID, body)",
    }),
    ("contracts", {"GET": "operations.contracts()"}),
    ("prospects/[prospectId]", {"GET": "operations.prospect(WORKSPACE_ID, prospectId)"}),
    ("prospects/[prospectId]/evidence", {"GET": "operations.evidence(WORKSPACE_ID, prospectId)"}),
    ("drafts/[draftId]", {"GET": "operations.draft(WORKSPACE_ID, draftId)"}),
    ("conversations/[conversationId]", {
        "GET": "operations.conversation(WORKSPACE_ID, conversationId)",
    }),
    # writes --------------------------------------------------------------
    ("discover", {"POST": "operations.discover(WORKSPACE_ID, body)"}),
    ("offers", {"POST": "operations.saveOffer(WORKSPACE_ID, body)"}),
    ("offers/[offerId]", {"DELETE": "operations.deactivateOffer(WORKSPACE_ID, offerId)"}),
    ("icps", {"POST": "operations.saveIcp(WORKSPACE_ID, body)"}),
    ("icps/[icpId]", {"DELETE": "operations.deactivateIcp(WORKSPACE_ID, icpId)"}),
    ("prospects/[prospectId]/research", {"POST": "operations.research(WORKSPACE_ID, prospectId, body)"}),
    ("prospects/[prospectId]/qualify", {"POST": "operations.qualify(WORKSPACE_ID, prospectId, body)"}),
    ("prospects/[prospectId]/personalize", {
        "POST": "operations.personalize(WORKSPACE_ID, prospectId, body)"
    }),
    ("drafts/[draftId]/approve", {"POST": "operations.approveDraft(WORKSPACE_ID, draftId, body.note)"}),
    ("drafts/[draftId]/edit", {"POST": "operations.editDraft(WORKSPACE_ID, draftId, body)"}),
    ("drafts/[draftId]/reject", {"POST": "operations.rejectDraft(WORKSPACE_ID, draftId, body.reason)"}),
    ("drafts/[draftId]/revoke-approval", {"POST": "operations.revokeApproval(WORKSPACE_ID, draftId)"}),
    ("drafts/[draftId]/send", {"POST": "operations.sendDraft(WORKSPACE_ID, draftId, body)"}),
    ("suppression/[suppressionId]", {
        "DELETE": "operations.removeSuppression(WORKSPACE_ID, suppressionId)"
    }),
    ("conversations/[conversationId]/close", {
        "POST": "operations.closeConversation(WORKSPACE_ID, conversationId)"
    }),
    ("conversations/[conversationId]/reopen", {
        "POST": "operations.reopenConversation(WORKSPACE_ID, conversationId)"
    }),
    ("webhooks/inbound", {"POST": "operations.inboundReply(WORKSPACE_ID, body)"}),
    ("events", {"POST": "operations.recordEvent(WORKSPACE_ID, body)"}),
]

HANDLER = '''
async function {method}(request: Request{dynamic}) {{
  const {{ search }} = new URL(request.url);
  try {{
    {body}
    const payload = await {call};
    return NextResponse.json(payload);
  }} catch (error) {{
    return errorResponse(error);
  }}
}}
'''

HEADER = '''import { NextResponse } from "next/server";

import { ApiRequestError, operations } from "@/lib/api/client";
import { WORKSPACE_ID } from "@/lib/api/config";

/** One error shape for every route: the backend's envelope, unchanged. */
function errorResponse(error: unknown) {
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
'''


def handler(method: str, call: str, dynamic: bool) -> str:
    signature = ", { params }: { params: Promise<Record<string, string>> }" if dynamic else ""
    keys = [key for key in DYNAMIC_KEYS if key in call]
    lines: list[str] = []
    if method in ("POST", "PUT"):
        lines.append("const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;")
    if keys:
        lines.append("const { %s } = await params;" % ", ".join(keys))
    body = "\n    ".join(lines)
    return HANDLER.format(method=method.lower(), dynamic=signature, body=body, call=call)


def render(route: str, methods: dict[str, str]) -> str:
    dynamic = "[" in route
    parts = [HEADER]
    for method, call in methods.items():
        parts.append(handler(method, call, dynamic))
        parts.append(f"\nexport const {method} = {method.lower()};\n")
    return textwrap.dedent("\n".join(parts)).rstrip() + "\n"


def main() -> None:
    for route, methods in ROUTES:
        target = APP_ROOT / "api" / route / "route.ts"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(route, methods))
    print(f"wrote {len(ROUTES)} route handlers")


if __name__ == "__main__":
    main()
