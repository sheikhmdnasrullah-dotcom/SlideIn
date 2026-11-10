"""Identity routes — one login for Console.

POST /v1/auth/login      {email, password}        -> session token (shown once)
POST /v1/auth/logout                              -> revoke the presented session
GET  /v1/auth/session                             -> who am I, which interfaces
POST /v1/auth/bootstrap  {email, password?, name?} -> first admin, only while no user exists
GET  /v1/auth/users                               -> workspace users (admin)
POST /v1/auth/users      {email, role, ...}       -> create a user (admin), password returned once

The Console BFF calls these routes: the browser only ever holds the HttpOnly
cookie, and every protected operation is still authorized here against the same
`require_role` ladder.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Body, Depends, Request

from ...db import session_scope
from ...errors import PermissionDenied, TenantForbiddenError, ValidationError
from ...identity import (
    HUMAN_ROLES,
    IdentityService,
    interfaces_for,
    session_response,
    user_payload,
)
from ...security import auth_mode, require_auth, require_role, presented_credential
from ...services.config import ConfigService

router = APIRouter()


def _password(body: dict) -> str:
    return str(body.get("password") or "")


@router.post("/auth/login", tags=["auth"])
async def login(body: dict = Body(...)) -> dict:
    """Exchange credentials for a session token both interfaces accept."""
    identifier = str(body.get("username") or body.get("email") or "").strip().lower()
    password = _password(body)

    # Local development (SLIDEIN_AUTH_MODE=disabled): no real user store yet, so
    # `admin`/`admin` is the documented local credential. On first login it
    # bootstraps the dev admin for ten_local; on any later login it authenticates
    # against the persisted account. This lets a local user sign in and reach the
    # Console + Dashboard without going through /auth/bootstrap.
    if auth_mode() == "disabled":
        tenant_id = (
            str(body.get("tenant_id") or "").strip()
            or os.getenv("SLIDEIN_DEFAULT_TENANT")
            or "ten_local"
        )
        if not identifier or not password:
            raise ValidationError(
                "Username/email and password are required",
                code="validation_error",
                recovery_action="provide_credentials",
            )
        async with session_scope() as session:
            identity = IdentityService(session)
            user = await identity.authenticate(identifier, password)
            if user is None:
                if await identity.count_users() > 0:
                    raise PermissionDenied(
                        "Username/email or password is incorrect",
                        code="not_authorized",
                        recovery_action="sign_in",
                    )
                await ConfigService(session).ensure_tenant(tenant_id, name=tenant_id)
                user, _raw = await identity.create_user(
                    tenant_id,
                    identifier,
                    role="admin",
                    name=str(body.get("name") or ""),
                    password=password,
                    must_change_password=False,
                )
            token, expires = await identity.create_session(user)
            return session_response(user, token, expires)

    if not identifier or not password:
        raise ValidationError(
            "Username/email and password are required",
            code="validation_error",
            recovery_action="provide_credentials",
        )
    async with session_scope() as session:
        identity = IdentityService(session)
        user = await identity.authenticate(identifier, password)
        if user is None:
            raise PermissionDenied(
                "Username/email or password is incorrect",
                code="not_authorized",
                recovery_action="sign_in",
            )
        token, expires = await identity.create_session(user)
        return session_response(user, token, expires)


@router.post("/auth/change-password", tags=["auth"])
async def change_password(request: Request, body: dict = Body(...)) -> dict:
    """Set a new password for the account and clear the must_change_password flag.

    Can be called either with an active session (Authorization: Bearer st_...)
    or by supplying { username, current_password, new_password }.
    """
    new_password = str(body.get("new_password") or "").strip()
    if not new_password or len(new_password) < 6:
        raise ValidationError(
            "New password must be at least 6 characters long",
            code="weak_password",
            recovery_action="provide_password",
        )

    token = presented_credential(request) or ""
    async with session_scope() as session:
        identity = IdentityService(session)
        user = None
        if token:
            res = await identity.get_session(token)
            if res:
                user = res[0]

        if user is None:
            identifier = str(body.get("username") or body.get("email") or "").strip().lower()
            current_password = str(body.get("current_password") or "")
            if not identifier or not current_password:
                raise PermissionDenied(
                    "Current password or active session is required to change password",
                    code="not_authorized",
                    recovery_action="provide_credentials",
                )
            user = await identity.authenticate(identifier, current_password)
            if user is None:
                raise PermissionDenied(
                    "Current password or username/email is incorrect",
                    code="not_authorized",
                    recovery_action="provide_credentials",
                )

        updated_user = await identity.change_password(user.id, new_password)
        new_token, expires = await identity.create_session(updated_user)
        payload = session_response(updated_user, new_token, expires)
        payload["message"] = "Password updated successfully"
        return payload


@router.post("/auth/logout", tags=["auth"])
async def logout(request: Request) -> dict:
    """Revoke the presented session. Idempotent: an already-revoked or
    missing token still reports success so sign-out always completes."""
    token = presented_credential(request) or ""
    if token:
        async with session_scope() as session:
            await IdentityService(session).revoke_session(token)
    return {"ok": True}


@router.get("/auth/session", tags=["auth"])
async def session_info(request: Request) -> dict:
    """The identity behind the presented session — used by both frontends
    to decide what to render. 401/403 when there is no live session.

    Local development with `SLIDEIN_AUTH_MODE=disabled` (set by `./dev`) does
    not require sign-in: the dev bypass resolves an admin on `ten_local` and
    this route serves it so the Console + Dashboard render on localhost.
    """
    auth = await require_auth(request)
    from ...security import auth_mode

    if not auth.is_session and auth_mode() != "disabled":
        raise PermissionDenied(
            "No user session on this request. Sign in to continue.",
            code="session_invalid",
            recovery_action="sign_in",
        )
    return {
        "auth": auth.to_dict(),
        "tenant_id": auth.tenant_id,
        "role": auth.role,
        "interfaces": interfaces_for(auth.role),
        "email": auth.email or "",
        "name": auth.name or "",
        "user_id": auth.user_id or "",
        "mode": "disabled" if auth.method == "disabled" else "session",
    }


@router.post("/auth/bootstrap", tags=["auth"])
async def bootstrap(body: dict = Body(...)) -> dict:
    """Create the first administrator of a fresh installation.

    Allowed exactly once: as soon as one user exists this endpoint closes
    itself, so a public installation cannot be taken over twice.
    """
    email = str(body.get("email") or "").strip().lower()
    password = _password(body)
    if not email or not password:
        raise ValidationError(
            "Email and password are required",
            code="validation_error",
            recovery_action="provide_credentials",
        )
    tenant_id = str(
        body.get("tenant_id") or os.getenv("SLIDEIN_DEFAULT_TENANT") or "ten_local"
    ).strip()
    async with session_scope() as session:
        identity = IdentityService(session)
        if await identity.count_users() > 0:
            raise ValidationError(
                "This installation already has users. Sign in instead.",
                code="already_initialized",
                recovery_action="sign_in",
            )
        await ConfigService(session).ensure_tenant(tenant_id, name=tenant_id)
        user, _raw = await identity.create_user(
            tenant_id, email, role="admin",
            name=str(body.get("name") or ""), password=password,
        )
        token, expires = await identity.create_session(user)
        payload = session_response(user, token, expires)
        payload["bootstrap"] = True
        return payload


@router.get("/auth/users", tags=["auth"])
async def list_users(auth=Depends(require_auth)) -> dict:
    """Everyone who can sign in to this workspace (admin only)."""
    require_role(auth, "admin")
    async with session_scope() as session:
        users = await IdentityService(session).list_users(auth.tenant_id)
    return {"users": users, "count": len(users)}


@router.post("/auth/users", tags=["auth"])
async def create_user(body: dict = Body(...), auth=Depends(require_auth)) -> dict:
    """Create a login for this workspace (admin only).

    `password` is optional: when omitted the service generates one and
    returns it exactly once — nothing recovers it afterwards.
    """
    require_role(auth, "admin")
    tenant_id = str(body.get("tenant_id") or auth.tenant_id).strip()
    if tenant_id != auth.tenant_id:
        raise TenantForbiddenError(
            f"Workspace {tenant_id!r} is not available to this credential",
            details={"requested": tenant_id},
            recovery_action="switch_workspace",
        )
    role = str(body.get("role") or "viewer").strip()
    if role not in HUMAN_ROLES:
        raise ValidationError(
            f"Role {role!r} is not a human role; use one of {', '.join(HUMAN_ROLES)}",
            code="validation_error",
            recovery_action="choose_role",
        )
    raw_given_pw = _password(body)
    must_change = bool(body.get("must_change_password", True if not raw_given_pw else False))
    identifier = str(body.get("username") or body.get("email") or "").strip().lower()
    async with session_scope() as session:
        identity = IdentityService(session)
        user, raw_password = await identity.create_user(
            tenant_id,
            identifier,
            role=role,
            name=str(body.get("name") or ""),
            password=raw_given_pw or None,
            must_change_password=must_change,
        )
        return {
            "user": user_payload(user),
            "password": raw_password,
            "interfaces": interfaces_for(role),
            "must_change_password": user.must_change_password,
            "note": "This password is shown once and cannot be retrieved again.",
        }


@router.get("/auth/state", tags=["auth"])
async def auth_state() -> dict:
    """What the sign-in screen needs before anyone types anything.

    Public on purpose: it only reveals whether the instance has been
    initialized yet (the bootstrap window), never who is in it.
    """
    async with session_scope() as session:
        remaining = await IdentityService(session).count_users()
    return {
        "bootstrap_available": remaining == 0,
        "interfaces": ["console"],
    }


__all__ = ["router"]
