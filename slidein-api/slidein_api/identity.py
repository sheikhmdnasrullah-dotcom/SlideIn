"""Identity for the unified system: users, sessions and issued API keys.

One client instance has one identity store. A person signs in once and
the resulting session is accepted by **both** interfaces — Console
(`workspace.*`) and Dashboard (`app.*`) forward it to this API, which is
the only place that decides who someone is and what they may do.

Design rules:
  * passwords are hashed with `hashlib.scrypt` (stdlib, no new deps);
  * session tokens are random and stored only as a SHA-256 digest;
  * a human role is one of `viewer | operator | admin` — the same ladder
    `security.require_role` already enforces, so session callers hit
    exactly the same guards as API-key callers;
  * `service` remains machine-only and can never be a human role;
  * interface access is derived, never stored: `operator`/`admin` may use
    Console and Dashboard, `viewer` only Dashboard.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .errors import PermissionDenied, ValidationError
from .models import ApiKey, User, UserSession, utcnow

#: Marker prefix so `security.authenticate` can tell a session token from
#: an API key without a database round trip.
SESSION_PREFIX = "st_"
#: Marker prefix for keys issued from the database (env keys keep their
#: own free-form shape).
API_KEY_PREFIX = "sk_live_"

#: Roles a human account may hold.
HUMAN_ROLES = ("viewer", "operator", "admin")
#: Roles that may open Console. Dashboard is open to every human role.
CONSOLE_ROLES = ("operator", "admin")

_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32

_PASSWORD_ALPHABET = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def interfaces_for(role: str) -> list[str]:
    """Which interfaces this role may open (stored nowhere, always derived)."""
    if role in CONSOLE_ROLES:
        return ["console", "dashboard"]
    if role in HUMAN_ROLES:
        return ["dashboard"]
    return []


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = (stored or "").split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def generate_password(length: int = 14) -> str:
    """A one-time password shown once at provisioning. Unambiguous alphabet."""
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def new_session_token() -> str:
    return SESSION_PREFIX + secrets.token_urlsafe(32)


def new_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def session_ttl() -> timedelta:
    days = int(os.getenv("SLIDEIN_SESSION_DAYS") or "14")
    return timedelta(days=max(1, days))


def user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "tenant_id": user.tenant_id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "interfaces": interfaces_for(user.role),
        "is_active": user.is_active,
        "created_at": _iso(user.created_at),
        "last_login_at": _iso(user.last_login_at),
    }


class IdentityService:
    """All identity reads/writes for one unit of work."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- users ---------------------------------------------------------------

    async def count_users(self, tenant_id: str | None = None) -> int:
        stmt = select(func.count()).select_from(User)
        if tenant_id:
            stmt = stmt.where(User.tenant_id == tenant_id)
        return int((await self.session.execute(stmt)).scalar_one())

    async def get_user(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == (email or "").strip().lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_users(self, tenant_id: str) -> list[dict]:
        stmt = (
            select(User)
            .where(User.tenant_id == tenant_id)
            .order_by(User.created_at.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [user_payload(row) for row in rows]

    async def create_user(
        self,
        tenant_id: str,
        email: str,
        role: str,
        name: str = "",
        password: str | None = None,
    ) -> tuple[User, str]:
        """Create a human account and return it with the raw password.

        The raw password is returned exactly once — it is never stored or
        logged in clear text.
        """
        clean_email = (email or "").strip().lower()
        if not clean_email or "@" not in clean_email:
            raise ValidationError(
                "A valid email address is required",
                code="validation_error",
                recovery_action="provide_email",
            )
        if role not in HUMAN_ROLES:
            raise ValidationError(
                f"Role {role!r} is not a human role; use one of {', '.join(HUMAN_ROLES)}",
                code="validation_error",
                recovery_action="choose_role",
            )
        if await self.get_user_by_email(clean_email):
            raise ValidationError(
                f"A user with email {clean_email} already exists",
                code="user_exists",
                recovery_action="use_existing_user",
            )
        raw_password = password or generate_password()
        user = User(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            email=clean_email,
            name=(name or "").strip(),
            role=role,
            password_hash=hash_password(raw_password),
        )
        self.session.add(user)
        await self.session.flush()
        return user, raw_password

    async def authenticate(self, email: str, password: str) -> User | None:
        """Password check. Returns None for unknown, inactive or wrong —
        the caller cannot distinguish those cases."""
        user = await self.get_user_by_email(email)
        if user is None:
            # Keep the timing profile of a real verification.
            verify_password(password or "", hash_password("timing-equalizer"))
            return None
        if not user.is_active:
            return None
        if not verify_password(password or "", user.password_hash):
            return None
        user.last_login_at = utcnow()
        await self.session.flush()
        return user

    # -- sessions ------------------------------------------------------------

    async def create_session(self, user: User) -> tuple[str, datetime]:
        token = new_session_token()
        expires = utcnow() + session_ttl()
        self.session.add(
            UserSession(
                token_hash=token_digest(token),
                user_id=user.id,
                tenant_id=user.tenant_id,
                expires_at=expires,
            )
        )
        await self.session.flush()
        return token, expires

    async def get_session(self, token: str) -> tuple[User, UserSession] | None:
        """Resolve a raw token. Expired, revoked and inactive are all None."""
        if not token or not token.startswith(SESSION_PREFIX):
            return None
        row = await self.session.get(UserSession, token_digest(token))
        if row is None or row.revoked_at is not None:
            return None
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= utcnow():
            return None
        user = await self.session.get(User, row.user_id)
        if user is None or not user.is_active:
            return None
        return user, row

    async def revoke_session(self, token: str) -> bool:
        row = await self.session.get(UserSession, token_digest(token))
        if row is None or row.revoked_at is not None:
            return False
        row.revoked_at = utcnow()
        await self.session.flush()
        return True

    async def revoke_user_sessions(self, user_id: str) -> int:
        stmt = select(UserSession).where(
            UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        for row in rows:
            row.revoked_at = utcnow()
        await self.session.flush()
        return len(rows)

    async def prune_sessions(self) -> int:
        """Drop expired/revoked rows so the table stays bounded."""
        stmt = select(UserSession).where(
            (UserSession.revoked_at.is_not(None)) | (UserSession.expires_at < utcnow())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        for row in rows:
            await self.session.delete(row)
        return len(rows)

    # -- issued API keys -----------------------------------------------------

    async def create_api_key(
        self, tenant_id: str, role: str = "operator", label: str = ""
    ) -> tuple[str, str]:
        """Issue a workspace API key. Returns (id, raw_key) — the raw key
        is shown once."""
        if role not in ("viewer", "operator", "admin"):
            raise ValidationError(
                f"Role {role!r} cannot be issued to an API key",
                code="validation_error",
                recovery_action="choose_role",
            )
        raw = new_api_key()
        row = ApiKey(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            label=(label or "").strip(),
            role=role,
            key_hash=token_digest(raw),
        )
        self.session.add(row)
        await self.session.flush()
        return row.id, raw

    async def verify_api_key(self, presented: str) -> tuple[str, str] | None:
        if not presented:
            return None
        row = (await self.session.execute(
            select(ApiKey).where(ApiKey.key_hash == token_digest(presented))
        )).scalar_one_or_none()
        if row is None or row.revoked_at is not None:
            return None
        row.last_used_at = utcnow()
        await self.session.flush()
        return row.tenant_id, row.role

    async def list_api_keys(self, tenant_id: str) -> list[dict]:
        stmt = select(ApiKey).where(ApiKey.tenant_id == tenant_id).order_by(ApiKey.created_at.asc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            {
                "id": row.id,
                "tenant_id": row.tenant_id,
                "label": row.label,
                "role": row.role,
                "created_at": _iso(row.created_at),
                "revoked": row.revoked_at is not None,
                "last_used_at": _iso(row.last_used_at),
            }
            for row in rows
        ]

    async def revoke_api_key(self, tenant_id: str, key_id: str) -> bool:
        row = await self.session.get(ApiKey, key_id)
        if row is None or row.tenant_id != tenant_id or row.revoked_at is not None:
            return False
        row.revoked_at = utcnow()
        await self.session.flush()
        return True

    # -- provisioning helpers -------------------------------------------------

    async def has_owner(self, tenant_id: str) -> bool:
        """Is there at least one active Console-capable user for this
        workspace? Drives the setup `owner_ready` stage."""
        stmt = select(func.count()).select_from(User).where(
            User.tenant_id == tenant_id,
            User.is_active.is_(True),
            User.role.in_(CONSOLE_ROLES),
        )
        return int((await self.session.execute(stmt)).scalar_one()) > 0

    async def ensure_owner(
        self, tenant_id: str, email: str, name: str = ""
    ) -> tuple[User, str] | None:
        """Create the workspace's owner login unless one already exists.

        Returns `(user, raw_password)` when a user was created and `None`
        when the workspace already has one — so provisioning is idempotent.
        """
        if await self.has_owner(tenant_id):
            return None
        if await self.get_user_by_email(email or ""):
            return None
        return await self.create_user(tenant_id, email or "", role="admin", name=name)


def session_response(
    user: User, token: str, expires: datetime
) -> dict:
    """The payload both frontends store after a successful login."""
    return {
        "token": token,
        "expires_at": _iso(expires),
        "user": user_payload(user),
        "tenant_id": user.tenant_id,
        "role": user.role,
        "interfaces": interfaces_for(user.role),
    }


def require_session_role(role: str, minimum: str) -> None:
    """Same ladder as `security.require_role`, for callers that hold a
    role string rather than an AuthContext."""
    rank = {name: index for index, name in enumerate(("viewer", "service", "operator", "admin"))}
    if rank.get(role, 0) < rank.get(minimum, 0):
        raise PermissionDenied(
            f"Role {role!r} cannot perform this action; requires {minimum!r}",
            details={"role": role, "required": minimum},
            recovery_action="request_authorization",
        )


__all__ = [
    "API_KEY_PREFIX",
    "CONSOLE_ROLES",
    "HUMAN_ROLES",
    "IdentityService",
    "SESSION_PREFIX",
    "generate_password",
    "hash_password",
    "interfaces_for",
    "new_api_key",
    "new_session_token",
    "session_response",
    "user_payload",
    "verify_password",
]
