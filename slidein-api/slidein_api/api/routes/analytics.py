"""Website connections, consented lead capture, and local network context."""

from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel

from ...db import session_scope
from ...integrations.geoip import GeoIP2Resolver
from ...security import AuthContext, require_role, resolve_workspace
from ...services.websites import WebsiteService
from ..deps import module_gate

router = APIRouter()


class NetworkContextRequest(BaseModel):
    ip: str


def _website(row) -> dict:
    return {
        "id": row.id, "domain": row.domain, "site_key": row.site_key,
        "provider": row.provider, "status": row.status,
        "snippet_url": f"/v1/public/website-snippet/{row.site_key}.js",
        "capture_url": f"/v1/public/website-events/{row.site_key}",
    }


@router.post("/tenants/{tenant_id}/websites", tags=["analytics"])
async def connect_website(
    tenant_id: str, payload: dict = Body(...), auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "settings")
        row, created = await WebsiteService(session).connect(
            auth.tenant_id, domain=str(payload.get("domain") or ""),
            provider=str(payload.get("provider") or "native"),
        )
        return {"website": _website(row), "created": created, "remote_deployment": False}


@router.get("/tenants/{tenant_id}/websites", tags=["analytics"])
async def list_websites(tenant_id: str, auth: AuthContext = Depends(resolve_workspace)) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "settings")
        rows = await WebsiteService(session).list(auth.tenant_id)
        return {"websites": [_website(row) for row in rows], "count": len(rows)}


@router.post("/public/website-events/{site_key}", tags=["analytics"])
async def capture_website_event(site_key: str, payload: dict = Body(...)) -> dict:
    """Public write-only endpoint; consent and page origin are validated."""
    async with session_scope() as session:
        return await WebsiteService(session).capture(site_key, payload)


@router.get("/public/website-snippet/{site_key}.js", tags=["analytics"])
async def website_snippet(site_key: str, request: Request) -> Response:
    # The key selects the write-only connection; it is not a read credential.
    endpoint = str(request.base_url).rstrip("/") + f"/v1/public/website-events/{site_key}"
    script = f"""
(function () {{
  'use strict';
  var ENDPOINT = {json.dumps(endpoint)};
  function sessionId() {{
    var key = 'slidein_session_id';
    var value = sessionStorage.getItem(key);
    if (!value) {{ value = crypto.randomUUID(); sessionStorage.setItem(key, value); }}
    return value;
  }}
  function send(payload) {{
    payload.event_id = crypto.randomUUID();
    payload.session_id = sessionId();
    payload.page_url = window.location.href.split('#')[0];
    var body = JSON.stringify(payload);
    if (navigator.sendBeacon && navigator.sendBeacon(ENDPOINT, new Blob([body], {{type:'application/json'}}))) return;
    fetch(ENDPOINT, {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:body, keepalive:true, credentials:'omit'}}).catch(function(){{}});
  }}
  window.SlideinLeadCapture = {{
    trackPage: function (consent) {{ if (consent === true) send({{event_type:'page_view', consent:true}}); return false; }}
  }};
  document.querySelectorAll('form[data-slidein-lead-capture]').forEach(function (form) {{
    form.addEventListener('submit', function () {{
      var email = form.querySelector('input[type="email"]');
      var consent = form.querySelector('input[data-slidein-consent]');
      if (!email || !email.value || !consent || !consent.checked) return;
      var first = form.querySelector('[name="first_name"]');
      var last = form.querySelector('[name="last_name"]');
      var company = form.querySelector('[name="company_name"]');
      send({{event_type:'form_submit', consent:true, email:email.value,
        first_name:first ? first.value : '', last_name:last ? last.value : '',
        company_name:company ? company.value : ''}});
    }});
  }});
}})();
"""
    return Response(script, media_type="application/javascript", headers={"Cache-Control": "no-store"})


@router.post("/tenants/{tenant_id}/analytics/network-context", tags=["analytics"])
async def network_context(
    tenant_id: str,
    payload: NetworkContextRequest = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Read a local MMDB only; never resolve a person or infer an employer."""
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "settings")
    resolver = GeoIP2Resolver()
    try:
        result = resolver.resolve(payload.ip)
    finally:
        resolver.close()
    return {"tenant_id": auth.tenant_id, "result": result, "network_io": False}


__all__ = ["router"]
