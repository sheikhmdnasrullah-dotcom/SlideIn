"""Authentication, workspace scoping and role permissions.

Every request is authenticated, bound to exactly one workspace, and
carries a role. A caller that presents a key belonging to workspace A
gets 404 (not 403) when it asks for workspace B, so the API never
confirms that another workspace exists.

Two credentials resolve to the same `AuthContext`:
  * a **session token** (`st_…`, from the shared HttpOnly cookie) — a
    signed-in person; carries `user_id`/`email` as well as the role;
  * an **API key** (env `SLIDEIN_API_KEYS` or a key issued at
    provisioning) — a server or integration.

Both hit the same `require_role` ladder, so Console and Dashboard cannot
see different permission rules than the API itself.

Local development can set `SLIDEIN_AUTH_MODE=disabled`, which resolves
every request to the first configured workspace as `admin`. Nothing else
changes: routes still apply the same guards, so a permissions bug still
shows up in tests.
"""

from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass
from typing import Mapping

from fastapi import Request
from fastapi.security.utils import get_authorization_scheme_param

from .errors import PermissionDenied, TenantForbiddenError

ROLES = ("viewer", "service", "operator", "admin")

#: Cookie both interfaces read (HttpOnly, set by each frontend's BFF).
SESSION_COOKIE = "slidein_session"


@dataclass(frozen=True)
class AuthContext:
    tenant_id: str
    role: str
    key_fingerprint: str
    method: str = "api_key"
    #: Present only for session callers — the human behind the request.
    user_id: str | None = None
    email: str | None = None
    name: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def can_write(self) -> bool:
        return self.role in ("service", "operator", "admin")

    @property
    def is_session(self) -> bool:
        return self.method == "session"

    def to_dict(self) -> dict:
        payload = {
            "tenant_id": self.tenant_id,
            "role": self.role,
            "method": self.method,
        }
        if self.user_id:
            payload["user_id"] = self.user_id
            payload["email"] = self.email or ""
            payload["name"] = self.name or ""
        return payload


def auth_mode() -> str:
    return (os.getenv("SLIDEIN_AUTH_MODE") or "enforced").strip().lower()


def _parse_keys(raw: str | None) -> dict[str, dict[str, str]]:
    """`SLIDEIN_API_KEYS` is JSON: ``{"ten_x": {"key": "...", "role": "admin"}}``."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(parsed, Mapping):
        return {}
    out: dict[str, dict[str, str]] = {}
    for tenant_id, entry in parsed.items():
        if isinstance(entry, str):
            # Shorthand: {"ten_x": "secret"} → operator role.
            out[str(tenant_id)] = {"key": entry, "role": "operator"}
        elif isinstance(entry, Mapping):
            key = str(entry.get("key") or entry.get("api_key") or "")
            role = str(entry.get("role") or "operator")
            if key:
                out[str(tenant_id)] = {"key": key, "role": role}
    return out


def configured_keys() -> dict[str, dict[str, str]]:
    return _parse_keys(os.getenv("SLIDEIN_API_KEYS"))


def _fingerprint(key: str) -> str:
    return "…" + key[-4:] if len(key) > 4 else "…"


class KeyStore:
    """Constant-time verification against every configured key."""

    def __init__(self, keys: Mapping[str, Mapping[str, str]]) -> None:
        self._keys: dict[str, dict[str, str]] = {
            str(k): {"key": str(v["key"]), "role": str(v.get("role", "operator"))}
            for k, v in dict(keys).items()
        }

    def verify(self, presented: str) -> tuple[str, str] | None:
        """Return (tenant_id, role) or None. No early exit, no oracle."""
        match: tuple[str, str] | None = None
        for tenant_id, entry in self._keys.items():
            if hmac.compare_digest(presented, entry["key"]):
                match = (tenant_id, entry["role"])
        return match

    @property
    def tenant_ids(self) -> list[str]:
        return sorted(self._keys)

    def __len__(self) -> int:
        return len(self._keys)


_store: KeyStore | None = None


def get_key_store() -> KeyStore:
    global _store
    if _store is None:
        _store = KeyStore(configured_keys())
    return _store


def set_key_store(store: KeyStore | None) -> None:
    global _store
    _store = store


def _default_workspace() -> tuple[str, str]:
    """The workspace used when auth is disabled (local development)."""
    keys = configured_keys()
    if keys:
        tenant_id = sorted(keys)[0]
        return tenant_id, keys[tenant_id].get("role", "admin")
    return (os.getenv("SLIDEIN_DEFAULT_TENANT") or "ten_local", "admin")


def presented_credential(request: Request) -> str | None:
    """The bearer token, or the session cookie when no bearer is present.

    Either way the value is a session token (`st_…`) or an API key; the
    caller decides which store to ask.
    """
    scheme, credentials = get_authorization_scheme_param(request.headers.get("authorization"))
    if credentials and scheme.lower() == "bearer":
        return credentials
    cookie = request.cookies.get(SESSION_COOKIE) or ""
    if cookie.startswith("st_"):
        return cookie
    return None


async def _session_context(request: Request, token: str) -> AuthContext | None:
    """Resolve a session token to the signed-in user."""
    from .identity import IdentityService, SESSION_PREFIX

    if not token.startswith(SESSION_PREFIX):
        return None
    from .db import session_scope

    async with session_scope() as session:
        resolved = await IdentityService(session).get_session(token)
    if resolved is None:
        raise PermissionDenied(
            "Your session has expired. Sign in again.",
            code="session_invalid",
            recovery_action="sign_in",
        )
    user, _row = resolved
    return AuthContext(
        tenant_id=user.tenant_id,
        role=user.role,
        key_fingerprint=user.email or f"user:{user.id[:8]}",
        method="session",
        user_id=user.id,
        email=user.email,
        name=user.name,
    )


async def authenticate(request: Request) -> AuthContext | None:
    """Resolve the caller: session token first (a signed-in person), then
    API key (a server or integration), then the dev bypass.

    Public paths return None and are handled by `require_auth` in the
    routes that need them.
    """
    path = request.url.path
    if path.startswith(("/health", "/docs", "/redoc", "/openapi.json", "/v1/contracts")):
        return None

    token = presented_credential(request)

    # 1. A signed-in person — accepted from either interface.
    if token:
        session_ctx = await _session_context(request, token)
        if session_ctx is not None:
            request.state.auth = session_ctx
            return session_ctx

    # 2. A machine credential: env key first, then a key issued at provisioning.
    if token:
        match = get_key_store().verify(token)
        if match is None:
            from .db import session_scope
            from .identity import IdentityService

            async with session_scope() as session:
                match = await IdentityService(session).verify_api_key(token)
        if match is not None:
            tenant_id, role = match
            request.state.auth = AuthContext(
                tenant_id=tenant_id, role=role, key_fingerprint=_fingerprint(token)
            )
            return request.state.auth
        if auth_mode() != "disabled":
            raise PermissionDenied(
                "The presented API key is not valid",
                code="not_authorized",
                recovery_action="request_authorization",
            )

    # 3. Dev bypass — no credential at all.
    if auth_mode() == "disabled":
        tenant_id, role = _default_workspace()
        header_tenant = request.headers.get("x-slidein-tenant")
        # In dev mode an explicit header may switch workspace, so the UI can
        # exercise multi-workspace behaviour without keys.
        if header_tenant and header_tenant in configured_keys():
            tenant_id, role = header_tenant, "admin"
        request.state.auth = AuthContext(
            tenant_id=tenant_id, role=role, key_fingerprint="auth-disabled", method="disabled"
        )
        return request.state.auth

    raise PermissionDenied(
        "A bearer API key is required",
        code="not_authorized",
        recovery_action="request_authorization",
    )


async def require_auth(request: Request) -> AuthContext:
    auth = getattr(request.state, "auth", None)
    if auth is None:
        auth = await authenticate(request)
    if auth is None:
        raise PermissionDenied(
            "This endpoint requires authentication",
            code="not_authorized",
            recovery_action="request_authorization",
        )
    return auth


async def resolve_workspace(request: Request, tenant_id: str | None = None) -> AuthContext:
    """Bind the request to exactly one workspace.

    The workspace in the path (or `X-Slidein-Tenant`) must be the one the
    key belongs to; otherwise 404, so the API never leaks existence.
    """
    auth = await require_auth(request)
    requested = tenant_id or request.headers.get("x-slidein-tenant")
    if requested and requested != auth.tenant_id and auth.method != "disabled":
        raise TenantForbiddenError(
            f"Workspace {requested!r} is not available to this API key",
            details={"requested": requested},
            recovery_action="switch_workspace",
        )
    return auth


def require_role(auth: AuthContext, minimum: str) -> None:
    """Enforce a minimum role.

    `service` is a machine credential, not a rung on the ladder: a
    service-role caller may only do service work, and a human may never
    assume it.
    """
    if minimum == "service":
        if auth.role != "service":
            raise PermissionDenied(
                f"Role {auth.role!r} cannot perform this action; requires 'service'",
                details={"role": auth.role, "required": "service"},
                recovery_action="request_authorization",
            )
        return
    if auth.role == "service":
        raise PermissionDenied(
            "Role 'service' cannot perform this action; requires a human role",
            details={"role": auth.role, "required": minimum},
            recovery_action="request_authorization",
        )
    rank = {role: index for index, role in enumerate(ROLES)}
    if rank.get(auth.role, 0) < rank.get(minimum, 0):
        raise PermissionDenied(
            f"Role {auth.role!r} cannot perform this action; requires {minimum!r}",
            details={"role": auth.role, "required": minimum},
            recovery_action="request_authorization",
        )


def role_for_actor(auth: AuthContext) -> str:
    return auth.role


__all__ = [
    "AuthContext",
    "KeyStore",
    "ROLES",
    "SESSION_COOKIE",
    "authenticate",
    "auth_mode",
    "configured_keys",
    "get_key_store",
    "require_auth",
    "require_role",
    "resolve_workspace",
    "set_key_store",
]
