"""Integration connections: registry, health, and safe live probes.

Only secret *references* are stored. Live probes resolve the actual
credential from the server secret store (env) at probe time and never
persist or log it. Probes never send mail or mutate the remote system.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import NotFoundError, ValidationError
from ..ids import new_id
from ..models import utcnow
from .models import IntegrationConnection
from .schemas import ConnectionInput

PROBE_TIMEOUT_SECONDS = 10


def _snapshot(row: IntegrationConnection) -> dict:
    return {
        "id": row.id,
        "provider": row.provider,
        "label": row.label,
        "secret_ref": row.secret_ref,
        "scopes": list(row.scopes),
        "status": row.status,
        "last_checked_at": (
            row.last_checked_at.isoformat() if row.last_checked_at else None
        ),
        "last_error": row.last_error,
    }


def _connection_secrets() -> dict:
    raw = os.getenv("SLIDEIN_CONNECTION_SECRETS") or "{}"
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _probe_smtp(secret: dict) -> tuple[bool, str]:
    """TCP + EHLO + STARTTLS + login. No message is sent."""
    import smtplib

    host = str(secret.get("host") or "").strip()
    port = int(secret.get("port") or 587)
    username = str(secret.get("username") or "")
    password = str(secret.get("password") or "")
    if not host or not username or not password:
        return False, "secret must include host, username, and password"
    try:
        with smtplib.SMTP(host, port, timeout=PROBE_TIMEOUT_SECONDS) as client:
            client.ehlo()
            try:
                client.starttls()
                client.ehlo()
            except smtplib.SMTPException:
                pass
            client.login(username, password)
    except Exception as exc:  # noqa: BLE001 - probe reports, never raises
        return False, f"{type(exc).__name__}: {exc}"
    return True, f"SMTP login ok as {username} (no mail sent)"


class ConnectionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_connections(self, tenant_id: str) -> list[dict]:
        rows = (
            await self.session.execute(
                select(IntegrationConnection)
                .where(IntegrationConnection.tenant_id == tenant_id)
                .order_by(IntegrationConnection.provider, IntegrationConnection.label)
            )
        ).scalars().all()
        return [_snapshot(r) for r in rows]

    async def register(
        self, tenant_id: str, payload: dict, *, actor: str = "operator"
    ) -> dict:
        try:
            data = ConnectionInput(**payload)
        except PydanticValidationError as exc:
            raise ValidationError(
                "Invalid connection record",
                code="connection_invalid",
                details={"errors": exc.errors(include_url=False)},
                recovery_action="fix_connection_record",
            ) from exc
        existing = (
            await self.session.execute(
                select(IntegrationConnection).where(
                    IntegrationConnection.tenant_id == tenant_id,
                    IntegrationConnection.provider == data.provider,
                    IntegrationConnection.label == data.label,
                )
            )
        ).scalars().first()
        if existing is None:
            row = IntegrationConnection(
                id=new_id("connection"), tenant_id=tenant_id,
                provider=data.provider, label=data.label,
                secret_ref=data.secret_ref, scopes=list(data.scopes),
            )
            self.session.add(row)
        else:
            existing.secret_ref = data.secret_ref
            existing.scopes = list(data.scopes)
            row = existing
        await self.session.flush()
        return _snapshot(row)

    async def revoke(self, tenant_id: str, connection_id: str) -> bool:
        row = await self.session.get(IntegrationConnection, connection_id)
        if row is None or row.tenant_id != tenant_id:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def probe(self, tenant_id: str, connection_id: str) -> dict:
        row = await self.session.get(IntegrationConnection, connection_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(f"Connection {connection_id!r} does not exist")
        checked_at: datetime = utcnow()
        if row.provider == "smtp":
            secret = _connection_secrets().get(row.secret_ref)
            if not isinstance(secret, dict):
                row.status = "unknown"
                row.last_error = (
                    f"secret {row.secret_ref!r} is not in the server secret store; "
                    "add it to SLIDEIN_CONNECTION_SECRETS, then probe again"
                )
            else:
                ok, detail = _probe_smtp(secret)
                row.status = "connected" if ok else "failing"
                row.last_error = "" if ok else detail
        else:
            row.status = "unknown"
            row.last_error = (
                f"live probe not implemented for provider {row.provider!r}; "
                "verify manually in the vendor console"
            )
        row.last_checked_at = checked_at
        await self.session.flush()
        return _snapshot(row)

    async def smtp_ready(self, tenant_id: str) -> tuple[bool, str]:
        rows = await self.list_connections(tenant_id)
        smtp = [r for r in rows if r["provider"] == "smtp"]
        if not smtp:
            return False, "no SMTP connection registered"
        if not any(r["secret_ref"] for r in smtp):
            return False, "SMTP connection has no secret reference"
        if not any(r["status"] == "connected" for r in smtp):
            return False, "no SMTP connection has passed a live probe"
        return True, "SMTP probed and connected"
