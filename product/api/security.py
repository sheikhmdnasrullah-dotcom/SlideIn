"""
Acquisition OS — API authentication and tenant isolation.

Implements the contract from product/API_SPEC.md §1: every endpoint under
/v1/organizations/{org_id} requires an org-scoped API key, and the key's
organization must match the organization in the path (tenant binding).

Design notes
------------
* Authentication is a *global* dependency so future routers cannot be added
  without credentials by accident (secure by default: forgetting auth is
  impossible, opting out must be explicit).
* Tenant binding is applied per router via ``require_org_access``, which reads
  the resolved path parameter.
* The key store is pluggable. The initial implementation reads
  ``PRODUCT_API_KEYS`` (a JSON object of ``org_id -> api_key``); swap in a
  database-backed store when persistence lands, without touching routes.
* A mismatched key is reported as 404 (organization "not found") so callers
  cannot probe which organization IDs exist.

Environment
-----------
PRODUCT_API_KEYS      JSON object mapping org_id -> API key. Required when
                      authentication is enforced.
PRODUCT_AUTH_MODE     "enforced" (default) or "disabled". "disabled" is for
                      local development only and must never be used in
                      production deployments.
"""

from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import Depends, HTTPException, Request, status

# Paths that stay reachable without credentials: operational probes and the
# OpenAPI documents. None of them expose tenant data.
PUBLIC_PATH_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json")

_AUTH_MODE_ENV = "PRODUCT_AUTH_MODE"
_API_KEYS_ENV = "PRODUCT_API_KEYS"


@dataclass(frozen=True)
class AuthContext:
    """The authenticated caller for a request."""

    org_id: str
    key_fingerprint: str  # short, non-reversible id for audit logging
    method: str = "api_key"

    @property
    def is_authenticated(self) -> bool:
        return self.method == "api_key"


class ApiKeyStore:
    """Maps org-scoped API keys to organizations.

    Verification compares against every configured key in constant time so
    response timing does not reveal which organization a candidate key
    belongs to.
    """

    def __init__(self, keys: Dict[str, str]):
        if not isinstance(keys, dict):
            raise TypeError("api key store expects a dict of org_id -> key")
        self._keys: Dict[str, str] = {
            str(org): str(key) for org, key in keys.items() if str(key)
        }

    @classmethod
    def from_env(cls, raw: Optional[str] = None) -> "ApiKeyStore":
        """Build a store from PRODUCT_API_KEYS (JSON object)."""
        payload = os.getenv(_API_KEYS_ENV, "") if raw is None else raw
        payload = (payload or "").strip()
        if not payload:
            return cls({})
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"{_API_KEYS_ENV} must be a JSON object of org_id -> api_key"
            ) from exc
        if not isinstance(data, dict):
            raise RuntimeError(
                f"{_API_KEYS_ENV} must be a JSON object of org_id -> api_key"
            )
        return cls(data)

    @property
    def org_ids(self) -> frozenset:
        return frozenset(self._keys)

    def verify(self, presented: str) -> Optional[str]:
        """Return the owning org_id for a valid key, else None."""
        if not presented:
            return None
        matched: Optional[str] = None
        presented_bytes = presented.encode("utf-8")
        for org_id, key in self._keys.items():
            if hmac.compare_digest(presented_bytes, key.encode("utf-8")):
                matched = org_id
        return matched

    def __len__(self) -> int:
        return len(self._keys)


_store: Optional[ApiKeyStore] = None


def get_key_store() -> ApiKeyStore:
    """Process-wide key store (lazy so tests can override before first use)."""
    global _store
    if _store is None:
        _store = ApiKeyStore.from_env()
    return _store


def set_key_store(store: Optional[ApiKeyStore]) -> None:
    """Replace the key store (used by tests). Pass None to reset."""
    global _store
    _store = store


def auth_mode() -> str:
    mode = os.getenv(_AUTH_MODE_ENV, "enforced").strip().lower()
    return mode if mode in ("enforced", "disabled") else "enforced"


def _fingerprint(key: str) -> str:
    return "key_" + key[-4:] if len(key) >= 4 else "key_****"


def _unauthenticated(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHENTICATED", "message": detail, "details": []},
        headers={"WWW-Authenticate": "Bearer"},
    )


def extract_bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("Authorization", "")
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    value = value.strip()
    return value or None


async def authenticate(request: Request) -> Optional[AuthContext]:
    """Global dependency: resolve the caller's credentials.

    * Public paths -> None (no tenant data is served there).
    * Auth disabled (explicit opt-out) -> permissive context derived from the
      path; only allowed for local development.
    * Otherwise a valid org-scoped API key is required.
    """
    path = request.url.path
    if any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES):
        return None

    token = extract_bearer_token(request)

    if auth_mode() == "disabled":
        # Explicit developer opt-out. Still surfaces the path organization so
        # downstream handlers behave identically to enforced mode.
        org_from_path = request.path_params.get("org_id", "")
        return AuthContext(org_id=str(org_from_path), key_fingerprint="auth-disabled", method="disabled")

    if token is None:
        raise _unauthenticated(
            "Missing bearer token. Supply Authorization: Bearer <org API key>."
        )

    org_id = get_key_store().verify(token)
    if org_id is None:
        # Deliberately identical message for unknown vs malformed keys.
        raise _unauthenticated("Invalid API key")

    return AuthContext(org_id=org_id, key_fingerprint=_fingerprint(token))


async def require_org_access(
    request: Request,
    auth: Optional[AuthContext] = Depends(authenticate),
) -> AuthContext:
    """Router-level dependency: bind the authenticated key to the path org.

    Register it via
    ``app.include_router(router, prefix="/v1/organizations/{org_id}", dependencies=[Depends(require_org_access)])``.
    """
    if auth is None:
        # Only reachable for public paths; those never carry an org binding.
        raise _unauthenticated("Authentication required")

    org_id = request.path_params.get("org_id")
    if org_id is None:
        # Router mounted without an org in the path: nothing to bind, but the
        # caller is still authenticated.
        return auth

    if auth.method != "disabled" and auth.org_id != str(org_id):
        # 404 rather than 403: do not confirm that another tenant exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ORG_NOT_FOUND", "message": "Organization not found", "details": []},
        )
    return auth
