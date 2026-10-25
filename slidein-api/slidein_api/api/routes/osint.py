"""OSINT routes: OpenOSINT enrichment for a prospect.

Workspace routes plus a health probe:

* ``POST /tenants/{id}/prospects/{pid}/osint`` — run lookups, persist
  evidence rows, return what each lookup did (operator + research module).
* ``GET  /tenants/{id}/prospects/{pid}/osint`` — the evidence rows the
  OSINT collector filed for this prospect.
* ``POST /tenants/{id}/osint/research`` — ad-hoc research: run lookups
  against a free-form query (name / email / handle / domain) without a
  prospect record; stateless, returns results + Google dork links.
* ``GET  /osint/health`` — is the CLI reachable from this deployment?

The pipeline's research stage can also pull OSINT in directly by passing
``connector: "openosint"`` to ``POST …/research``; these routes exist for
targeted, on-demand lookups outside that stage.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Body, Depends, HTTPException
from starlette import status as http_status

from ...db import session_scope
from ...errors import NotFoundError, SlideinError
from ...integrations.openosint import DEFAULT_LOOKUPS, LOOKUP_SPECS, OpenOSINTAdapter
from ...security import AuthContext, require_auth, require_role, resolve_workspace
from ...services.discovery import DiscoveryService
from ...services.osint import (
    OSINTService,
    default_lookups_for,
    detect_target_type,
    dorks_for,
    query_targets,
)
from ...services.suppression import SuppressionService
from ..deps import module_gate

router = APIRouter()


def _error(exc: SlideinError) -> HTTPException:
    code = exc.code
    status = (
        http_status.HTTP_404_NOT_FOUND
        if code in ("not_found", "tenant_forbidden", "prospect_not_found")
        else http_status.HTTP_403_FORBIDDEN
        if code == "not_authorized"
        else http_status.HTTP_409_CONFLICT
        if code in ("suppressed", "invalid_transition")
        else http_status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(status_code=status, detail=exc.to_dict())


def _validated_lookups(payload: dict) -> list[str] | None:
    """Normalise the optional ``lookups`` body field (None = type default)."""
    lookups = payload.get("lookups")
    if lookups is None:
        return None
    if not isinstance(lookups, list) or not all(isinstance(item, str) for item in lookups):
        raise _error(
            SlideinError(
                "'lookups' must be a list of lookup names",
                code="prospect_invalid",
                details={"allowed": sorted(LOOKUP_SPECS)},
                recovery_action="fix_prospect_record",
            )
        )
    unknown = [name for name in lookups if name not in LOOKUP_SPECS]
    if unknown:
        raise _error(
            SlideinError(
                f"Unknown lookup(s): {', '.join(sorted(unknown))}",
                code="prospect_invalid",
                details={"allowed": sorted(LOOKUP_SPECS)},
                recovery_action="fix_prospect_record",
            )
        )
    return lookups


@router.get("/osint/health", tags=["osint"])
async def osint_health(_: AuthContext = Depends(require_auth)) -> dict:
    """Adapter health — never fails the request, degrades to a status."""
    info = OpenOSINTAdapter().health()
    return {
        "adapter": info.adapter,
        "status": info.status.value,
        "detail": info.detail,
        "default_lookups": list(DEFAULT_LOOKUPS),
        "lookups": [
            {
                "name": name,
                "tool": spec.tool,
                "active": spec.active,
                "description": spec.description,
            }
            for name, spec in LOOKUP_SPECS.items()
        ],
    }


@router.post("/tenants/{tenant_id}/prospects/{prospect_id}/osint", tags=["osint"])
async def run_osint(
    tenant_id: str,
    prospect_id: str,
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Run OpenOSINT lookups for one prospect and file the evidence.

    Body: ``{"lookups": ["dns", ...], "allow_active": false}`` — lookups
    defaults to the passive set; ``allow_active`` opts into the noisy
    email/username enumerations for this call only.
    """
    require_role(auth, "operator")
    lookups = _validated_lookups(payload)
    allow_active = bool(payload.get("allow_active", False))

    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "research")
        prospect = await DiscoveryService(session).get_prospect(auth.tenant_id, prospect_id)
        if prospect is None:
            raise _error(
                NotFoundError(
                    f"Prospect {prospect_id!r} does not exist in this workspace",
                    code="prospect_not_found",
                    recovery_action="return_to_discovery",
                )
            )
        blocked = await SuppressionService(session).is_suppressed(
            auth.tenant_id, prospect.email
        )
        if blocked is not None:
            raise _error(
                SlideinError(
                    f"{prospect.email} is suppressed ({blocked['reason']})",
                    code="suppressed",
                    details={"suppression": blocked},
                    recovery_action="review_suppression",
                )
            )
        try:
            result = await OSINTService(session).enrich_prospect(
                tenant_id=auth.tenant_id,
                prospect=prospect,
                lookups=lookups,
                allow_active=allow_active,
                actor=f"user:{auth.role}",
            )
        except SlideinError as exc:
            raise _error(exc)
    return result


@router.get("/tenants/{tenant_id}/prospects/{prospect_id}/osint", tags=["osint"])
async def list_osint_evidence(
    tenant_id: str,
    prospect_id: str,
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Evidence rows filed by the OSINT collector for this prospect."""
    async with session_scope() as session:
        await module_gate(
            session, auth.tenant_id, "research", "qualification", "personalization"
        )
        prospect = await DiscoveryService(session).get_prospect(auth.tenant_id, prospect_id)
        if prospect is None:
            raise _error(
                NotFoundError(
                    f"Prospect {prospect_id!r} does not exist in this workspace",
                    code="prospect_not_found",
                    recovery_action="return_to_discovery",
                )
            )
        rows = await OSINTService(session).list_evidence(
            auth.tenant_id, prospect_id
        )
    return {"prospect_id": prospect_id, "evidence": rows, "count": len(rows)}


@router.post("/tenants/{tenant_id}/osint/research", tags=["osint"])
async def research_ad_hoc(
    tenant_id: str,
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Ad-hoc research — run OpenOSINT against a free-form query.

    Body: ``{"query": "Jane Doe | jane@acme.com | acme.com | @handle",
    "lookups": [...], "allow_active": false}``. The query type is detected
    automatically and drives the default lookup set; nothing is persisted —
    use the per-prospect route to file evidence. ``dorks`` returns
    clickable Google searches per platform (no SERP key needed).
    """
    require_role(auth, "operator")
    query = str(payload.get("query") or "").strip()
    if not query:
        raise _error(
            SlideinError(
                "'query' is required",
                code="prospect_invalid",
                details={"allowed": sorted(LOOKUP_SPECS)},
                recovery_action="fix_prospect_record",
            )
        )
    explicit = _validated_lookups(payload)
    allow_active = bool(payload.get("allow_active", False))

    target_type = detect_target_type(query)
    selected = list(explicit) if explicit is not None else list(
        default_lookups_for(target_type)
    )
    targets = query_targets(query, target_type)
    runnable = [name for name in selected if targets.get(name)]

    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "research")

    started = time.monotonic()
    results = await OpenOSINTAdapter().run_lookups(
        targets, runnable, allow_active=allow_active
    )
    rows = [{**item.summary(), "lines": item.lines} for item in results]
    for name in selected:
        if not targets.get(name):
            rows.append(
                {
                    "lookup": name,
                    "tool": LOOKUP_SPECS[name].tool,
                    "target": "",
                    "ok": False,
                    "error": f"lookup {name!r} has no target for a {target_type} query",
                    "lines": [],
                    "duration_ms": 0,
                }
            )
    return {
        "query": query,
        "target_type": target_type,
        "allow_active": allow_active,
        "targets": {name: targets[name] for name in selected if targets.get(name)},
        "lookups": rows,
        "dorks": dorks_for(query),
        "succeeded": [item.lookup for item in results if item.ok],
        "failed": [item.lookup for item in results if not item.ok],
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


__all__ = ["router"]
