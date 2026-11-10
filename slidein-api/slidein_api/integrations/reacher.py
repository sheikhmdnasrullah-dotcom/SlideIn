"""Reacher email verification with explicit, secret-safe outcomes."""

from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx

from ..errors import ProviderError


class ReacherAdapter:
    name = "reacher"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        secret: str | None = None,
        timeout: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (
            base_url if base_url is not None else os.getenv("REACHER_URL", "")
        ).strip().rstrip("/")
        self.secret = secret if secret is not None else os.getenv("REACHER_SECRET", "")
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
                raise ValueError("Reacher URL must be credentialed-free HTTPS or loopback HTTP")

    async def verify(self, email: str) -> dict:
        if not self.base_url:
            raise ProviderError(
                "Reacher is not configured",
                code="source_unavailable",
                details={"missing": ["REACHER_URL"]},
                recovery_action="configure_provider",
            )
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout)
        headers = {"x-reacher-secret": self.secret} if self.secret else {}
        try:
            response = await client.post(
                f"{self.base_url}/v0/check_email",
                json={"to_email": email},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(
                "Reacher could not verify the recipient",
                code="source_unavailable",
                details={"provider": self.name, "error_type": type(exc).__name__},
                recovery_action="retry_stage",
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        if not isinstance(payload, dict):
            raise ProviderError(
                "Reacher returned a malformed response",
                code="source_unavailable",
                details={"provider": self.name},
                recovery_action="retry_stage",
            )
        verdict = str(payload.get("is_reachable") or "unknown").lower()
        if verdict not in {"safe", "risky", "invalid", "unknown"}:
            raise ProviderError(
                "Reacher returned an unknown verdict",
                code="source_unavailable",
                details={"provider": self.name},
                recovery_action="retry_stage",
            )
        return {
            "collector": self.name,
            "status": verdict,
            "verified": True,
            "consent_verified": False,
        }


__all__ = ["ReacherAdapter"]
