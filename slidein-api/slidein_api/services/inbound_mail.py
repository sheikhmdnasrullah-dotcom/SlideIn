"""Tenant-scoped Google Workspace inbound mail ingestion."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Callable

from sqlalchemy import select

from ..errors import ConfigError, SlideinError
from ..ids import new_id
from ..integrations.google_imap import GoogleImapClient
from ..models import InboundReceipt, Tenant
from .conversations import ConversationService

Fetcher = Callable[[dict], list[dict]]
_SECRET_REF = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")


class GoogleWorkspaceInboundService:
    def __init__(self, session, *, fetcher: Fetcher | None = None) -> None:
        self.session = session
        self.fetcher = fetcher

    async def mail_config(self, tenant_id: str) -> dict:
        tenant = await self.session.get(Tenant, tenant_id)
        raw = dict((tenant.settings or {}).get("mail") or {}) if tenant else {}
        return {
            "provider": raw.get("provider") or "kumomta",
            "enabled": bool(raw.get("enabled")),
            "imap_host": raw.get("imap_host") or "imap.gmail.com",
            "imap_port": int(raw.get("imap_port") or 993),
            "username": raw.get("username") or "",
            "secret_ref": raw.get("secret_ref") or "",
        }

    async def save_mail_config(self, tenant_id: str, payload: dict) -> dict:
        tenant = await self.session.get(Tenant, tenant_id)
        if tenant is None:
            raise ConfigError("Workspace not found", code="not_found")
        provider = str(payload.get("provider") or "kumomta")
        if provider not in {"kumomta", "google_workspace"}:
            raise ConfigError("Unsupported mail provider", code="provider_invalid")
        enabled = payload.get("enabled") is True
        config = {
            "provider": provider,
            "enabled": enabled and provider == "google_workspace",
            "imap_host": str(payload.get("imap_host") or "imap.gmail.com").strip(),
            "imap_port": int(payload.get("imap_port") or 993),
            "username": str(payload.get("username") or "").strip().lower(),
            "secret_ref": str(payload.get("secret_ref") or "").strip(),
        }
        if provider == "google_workspace" and enabled:
            if "@" not in config["username"] or not config["imap_host"]:
                raise ConfigError("Google Workspace email and IMAP host are required", code="mail_configuration")
            if not _SECRET_REF.fullmatch(config["secret_ref"]):
                raise ConfigError("A valid IMAP secret reference is required", code="mail_configuration")
        settings = dict(tenant.settings or {})
        settings["mail"] = config
        tenant.settings = settings
        await self.session.flush()
        return await self.mail_config(tenant_id)

    async def poll(self, tenant_id: str) -> dict:
        config = await self.mail_config(tenant_id)
        if config["provider"] != "google_workspace" or not config["enabled"]:
            return {"status": "disabled", "reason": "missing_configuration", "processed": 0}
        password = os.getenv(config["secret_ref"], "")
        if not password:
            return {"status": "disabled", "reason": "missing_configuration", "processed": 0}
        fetcher = self.fetcher or (
            lambda current: GoogleImapClient(current, password).fetch_unseen()
        )
        messages = await asyncio.to_thread(fetcher, config)
        stats = {"status": "ok", "processed": 0, "duplicates": 0, "failed": 0, "skipped": 0}
        for message in messages:
            external_id = str(message.get("external_id") or "").strip()
            if not external_id:
                stats["skipped"] += 1
                continue
            existing = (
                await self.session.execute(
                    select(InboundReceipt).where(
                        InboundReceipt.tenant_id == tenant_id,
                        InboundReceipt.provider == "google_workspace",
                        InboundReceipt.external_id == external_id,
                    )
                )
            ).scalars().first()
            if existing is not None:
                stats["duplicates"] += 1
                continue
            receipt = InboundReceipt(
                id=new_id("inbound_receipt"),
                tenant_id=tenant_id,
                provider="google_workspace",
                external_id=external_id,
            )
            try:
                result = await ConversationService(self.session).handle_reply(
                    tenant_id=tenant_id,
                    sender_email=str(message.get("sender_email") or ""),
                    subject=str(message.get("subject") or ""),
                    body=str(message.get("body") or ""),
                    in_reply_to=str(message.get("in_reply_to") or ""),
                    thread_id=str(message.get("thread_id") or ""),
                    actor="google_workspace_imap",
                )
                receipt.reply_id = result["reply_id"]
                receipt.status = "processed"
                stats["processed"] += 1
            except SlideinError as exc:
                receipt.status = "failed"
                receipt.error_code = exc.code
                stats["failed"] += 1
            self.session.add(receipt)
            await self.session.flush()
        return stats


__all__ = ["GoogleWorkspaceInboundService"]
