"""Warmbly warmup-platform adapter (canonical, tenant-agnostic).

Warmbly is the self-hosted mailbox-warmup platform installed alongside
Slidein by ``install.sh`` (Phase 12). This adapter speaks its documented
REST API (https://docs.warmbly.com/api/reference/mailboxes/):

  * ``GET  /emails``                    list connected mailboxes (READ_EMAILS)
  * ``POST /emails/{id}/warmup/start``  enable warmup on a mailbox (WRITE_EMAILS)
  * ``GET  /emails/{id}/auth-check``    live SPF/DKIM/DMARC verdict (READ_EMAILS)

Contract rules, mirroring ``ReacherAdapter``:

  * ``WARMBLY_URL`` unset → state ``not_configured``: the warmup platform is
    not part of this deployment, and the caller decides what that means.
  * every transport failure degrades to ``unreachable`` — this adapter never
    raises and never fabricates a warmup or DNS verdict.
  * bearer auth from ``WARMBLY_API_TOKEN`` (Settings → API keys, scopes
    ``READ_EMAILS`` + ``WRITE_EMAILS``). Loopback endpoints may be plain
    HTTP (the installer binds Warmbly's API on 127.0.0.1:8180); anything
    else must be credentia-free HTTPS, same rule as Reacher.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import httpx


class WarmblyAdapter:
    name = "warmbly"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 3.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (
            base_url if base_url is not None else os.getenv("WARMBLY_URL", "")
        ).strip().rstrip("/")
        self.token = (
            token if token is not None else os.getenv("WARMBLY_API_TOKEN", "")
        ).strip()
        self.timeout = timeout
        self.client = client
        if self.base_url:
            parsed = urlparse(self.base_url)
            local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            if (
                not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.scheme not in ({"https", "http"} if local else {"https"})
            ):
                raise ValueError(
                    "Warmbly URL must be credentia-free HTTPS or loopback HTTP"
                )

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[str, Any]:
        """Call Warmbly. Returns ``(state, payload)`` where state is one of
        ``not_configured | unreachable | unauthorized | http_error | ok``."""
        if not self.base_url:
            return "not_configured", None
        try:
            if self.client is not None:
                response = await self.client.request(
                    method,
                    f"{self.base_url}{path}",
                    params=params,
                    json=json_body,
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method,
                        f"{self.base_url}{path}",
                        params=params,
                        json=json_body,
                        headers=self._headers(),
                    )
        except httpx.HTTPError:
            return "unreachable", None
        if response.status_code in (401, 403):
            return "unauthorized", None
        if response.status_code >= 400:
            try:
                detail = response.json()
            except ValueError:
                detail = {"message": response.text[:200]}
            return "http_error", {"status_code": response.status_code, "detail": detail}
        try:
            return "ok", response.json()
        except ValueError:
            return "ok", None

    async def health(self) -> dict[str, Any]:
        """Reachability probe. ``reachable`` only ever means a real 2xx."""
        state, payload = await self._request("GET", "/health")
        if state == "ok":
            return {"state": "ok", "reachable": True, "detail": ""}
        if state == "not_configured":
            return {"state": "not_configured", "reachable": False,
                    "detail": "WARMBLY_URL is not set"}
        if state == "unauthorized":
            return {"state": "unauthorized", "reachable": True,
                    "detail": "Warmbly rejected the API token (WARMBLY_API_TOKEN)"}
        return {"state": state, "reachable": False,
                "detail": f"Warmbly API at {self.base_url} is {state}"}

    async def list_mailboxes(self, *, limit: int = 100) -> dict[str, Any]:
        """Connected mailboxes, newest first (``GET /emails``)."""
        state, payload = await self._request(
            "GET", "/emails", params={"limit": limit}
        )
        if state != "ok":
            return {"state": state, "mailboxes": [], "detail": state}
        data = payload.get("data") if isinstance(payload, dict) else None
        return {
            "state": "ok",
            "mailboxes": data if isinstance(data, list) else [],
            "pagination": (payload or {}).get("pagination") or {},
            "detail": "",
        }

    async def warmup_start(self, mailbox_id: str) -> dict[str, Any]:
        """Enable warmup on one mailbox (``POST /emails/{id}/warmup/start``)."""
        state, payload = await self._request(
            "POST", f"/emails/{mailbox_id}/warmup/start"
        )
        if state != "ok":
            return {"state": state, "mailbox": None, "detail": state}
        return {"state": "ok", "mailbox": payload, "detail": ""}

    async def auth_check(self, mailbox_id: str) -> dict[str, Any]:
        """Live SPF/DKIM/DMARC verdict for the mailbox's sending domain
        (``GET /emails/{id}/auth-check``). Read-only; records nothing."""
        state, payload = await self._request(
            "GET", f"/emails/{mailbox_id}/auth-check"
        )
        if state != "ok":
            return {"state": state, "auth": None, "detail": state}
        return {"state": "ok", "auth": payload, "detail": ""}
