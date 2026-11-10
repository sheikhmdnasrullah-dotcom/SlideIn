"""The 14-day mailbox warmup rule, powered by Warmbly.

The rule: a tenant's live (non dry-run) campaign sends stay blocked until
every sending mailbox has completed a 14-day Warmbly warmup on a sending
domain whose SPF/DKIM/DMARC are set up.

Lifecycle:

  * ``start()`` — recorded automatically when initial setup saves the sending
    identity (the moment the sender domain exists and the DNS/DKIM
    connection is part of the workspace), or explicitly via
    ``POST /v1/tenants/{id}/warmup/start``. Idempotent: the 14-day clock is
    never reset by a repeat call. It best-effort enables Warmbly warmup on
    every connected mailbox that matches the workspace senders.
  * ``status()`` — the local 14-day clock plus a live Warmbly read (mailboxes
    connected, warmup anchors, DNS auth verdict). An unreachable Warmbly
    reports ``unreachable`` and blocks — it never reports "ready".
  * ``enforce()`` — the gate, called from the send path for live transports.
    Dry-run transport is never gated: recording a dispatch is not sending.

Enforcement mode (``SLIDEIN_WARMUP_ENFORCE``):

  * ``auto`` (default) — enforced iff ``WARMBLY_URL`` is configured. A dev
    box without the warmup platform keeps working and says so in status;
    every ``install.sh`` deployment writes ``WARMBLY_URL``, so the rule holds
    in production.
  * ``required`` — always enforced, Warmbly or not (staging hardening).
  * ``off`` — explicitly disabled (local development only).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import SlideinError
from ..integrations.warmbly import WarmblyAdapter

logger = logging.getLogger("slidein.warmup")

#: The rule: this many days of Warmbly warmup before live campaigns.
WARMUP_REQUIRED_DAYS = 14

SETTINGS_KEY = "mailbox_warmup"


class WarmupIncompleteError(SlideinError):
    """Raised when a live send is attempted before the warmup rule is met."""

    code = "mailbox_warmup_incomplete"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _days_since(moment: datetime | None, now: datetime) -> int:
    if moment is None:
        return 0
    return max(0, int((now - moment).total_seconds() // 86400))


def enforcement_mode() -> str:
    raw = (os.getenv("SLIDEIN_WARMUP_ENFORCE") or "auto").strip().lower()
    if raw in {"off", "disabled", "0", "false"}:
        return "off"
    if raw in {"required", "on", "1", "true"}:
        return "required"
    return "auto"


def is_enforced() -> bool:
    mode = enforcement_mode()
    if mode == "off":
        return False
    if mode == "required":
        return True
    return bool((os.getenv("WARMBLY_URL") or "").strip())


class WarmupService:
    """Reads and writes the per-tenant warmup rule state and enforces it."""

    def __init__(self, session: AsyncSession, *, adapter: WarmblyAdapter | None = None) -> None:
        self.session = session
        self._injected_adapter = adapter

    # -- state -------------------------------------------------------------

    async def _tenant(self, tenant_id: str):
        from ..models import Tenant

        return await self.session.get(Tenant, tenant_id)

    async def _block(self, tenant_id: str) -> dict:
        tenant = await self._tenant(tenant_id)
        stored = dict(tenant.settings or {}) if tenant else {}
        block = stored.get(SETTINGS_KEY)
        return dict(block) if isinstance(block, dict) else {}

    async def _save_block(self, tenant_id: str, block: dict) -> None:
        tenant = await self._tenant(tenant_id)
        if tenant is None:
            return
        settings = dict(tenant.settings or {})
        settings[SETTINGS_KEY] = block
        tenant.settings = settings
        await self.session.flush()

    async def _senders(self, tenant_id: str) -> list[str]:
        """Configured sending identities for this workspace, in policy order."""
        from .outreach import OutreachService

        policy = await OutreachService(self.session).policy(tenant_id)
        senders: list[str] = []
        for raw in policy.get("allowed_senders") or []:
            email = str(raw or "").strip().lower()
            if email and email not in senders:
                senders.append(email)
        return senders

    def _warmbly(self) -> WarmblyAdapter:
        if self._injected_adapter is not None:
            return self._injected_adapter
        return WarmblyAdapter()

    # -- lifecycle ---------------------------------------------------------

    async def start(
        self, tenant_id: str, *, actor: str, mailboxes: list[str] | None = None
    ) -> dict:
        """Start (or resume syncing) the 14-day warmup clock. Idempotent:
        a repeat call syncs Warmbly again but never resets the clock."""
        block = await self._block(tenant_id)
        if not block.get("started_at"):
            senders = (
                [str(m).strip().lower() for m in mailboxes if str(m).strip()]
                if mailboxes is not None
                else await self._senders(tenant_id)
            )
            if not senders:
                # Nothing to warm yet: no sending identity is configured, so
                # there is no rule to start. The send path fails on "no
                # sending identity" before any warmup question arises.
                return await self.status(tenant_id, refresh=False)
            started = _now()
            block = {
                "status": "warming",
                "days_required": WARMUP_REQUIRED_DAYS,
                "started_at": _iso(started),
                "due_at": _iso(started + timedelta(days=WARMUP_REQUIRED_DAYS)),
                "started_by": actor,
                "mailboxes": [{"email": email} for email in senders],
                "warmbly": {"state": "not_checked", "checked_at": ""},
            }
            await self._save_block(tenant_id, block)
        block = await self._sync_warmbly(tenant_id, block, actor=actor)
        await self._save_block(tenant_id, block)
        return await self.status(tenant_id, refresh=False)

    async def maybe_start_after_setup(self, tenant_id: str, *, actor: str) -> dict | None:
        """Auto-start hook for initial setup: fires once the sending identity
        (sender → domain architecture) is saved. Never raises."""
        try:
            senders = await self._senders(tenant_id)
            if not senders:
                return None
            return await self.start(tenant_id, actor=actor, mailboxes=senders)
        except Exception:  # pragma: no cover - setup must not fail on warmup
            logger.warning(
                "mailbox warmup auto-start failed for %s", tenant_id, exc_info=True
            )
            return None

    async def _sync_warmbly(self, tenant_id: str, block: dict, *, actor: str) -> dict:
        """Best-effort sync: connect the workspace's senders to Warmbly's
        warmup records. Every failure is recorded, never raised."""
        adapter = self._warmbly()
        checked_at = _iso(_now())
        if not adapter.configured:
            block["warmbly"] = {
                "state": "not_configured",
                "checked_at": checked_at,
                "detail": "WARMBLY_URL is not set; the warmup platform is not part of this deployment",
            }
            return block

        listing = await adapter.list_mailboxes()
        if listing["state"] != "ok":
            block["warmbly"] = {
                "state": listing["state"],
                "checked_at": checked_at,
                "detail": listing.get("detail") or listing["state"],
            }
            return block

        wanted = {
            str(entry.get("email") or "").strip().lower()
            for entry in block.get("mailboxes") or []
            if str(entry.get("email") or "").strip()
        }
        by_email: dict[str, dict] = {}
        for mailbox in listing["mailboxes"]:
            email = str(mailbox.get("email") or "").strip().lower()
            if email in wanted and email not in by_email:
                by_email[email] = mailbox

        records: list[dict] = []
        warming = 0
        for email in sorted(wanted):
            mailbox = by_email.get(email)
            if mailbox is None:
                records.append({"email": email, "in_warmbly": False})
                continue
            record = {
                "email": email,
                "in_warmbly": True,
                "warmbly_id": str(mailbox.get("id") or ""),
                "mailbox_status": str(mailbox.get("status") or ""),
                "warmup_enabled": bool(mailbox.get("warmup")),
                "warmup_started_at": mailbox.get("warmup") or "",
                "warmup_paused": bool(mailbox.get("warmup_paused_at")),
                "auth_state": str(mailbox.get("auth_state") or "unknown"),
                "auth_failing_since": mailbox.get("auth_failing_since") or "",
            }
            if record["warmup_enabled"] and not record["warmup_paused"]:
                if not record["warmup_started_at"]:
                    started = await adapter.warmup_start(record["warmbly_id"])
                    if started["state"] == "ok":
                        refreshed = started["mailbox"] or {}
                        record["warmup_enabled"] = True
                        record["warmup_started_at"] = (
                            str(refreshed.get("warmup") or "") or _iso(_now())
                        )
                    else:
                        record["warmup_error"] = started.get("detail") or started["state"]
            if record["warmup_enabled"] and not record["warmup_paused"]:
                warming += 1
            records.append(record)
        block["mailboxes"] = records
        block["warmbly"] = {
            "state": "ok",
            "checked_at": checked_at,
            "connected": sum(1 for r in records if r.get("in_warmbly")),
            "warming": warming,
            "detail": "",
        }
        return block

    # -- read --------------------------------------------------------------

    async def status(self, tenant_id: str, *, refresh: bool = False) -> dict[str, Any]:
        """The rule's state: local clock + Warmbly evidence + verdict."""
        mode = enforcement_mode()
        enforced = is_enforced()
        block = await self._block(tenant_id)
        now = _now()

        if refresh and enforced:
            try:
                block = await self._sync_warmbly(tenant_id, block, actor="system")
                await self._save_block(tenant_id, block)
            except Exception:  # pragma: no cover - never fail a read on sync
                logger.warning("warmbly sync failed for %s", tenant_id, exc_info=True)

        started_at = _parse(block.get("started_at"))
        due_at = _parse(block.get("due_at"))
        elapsed_days = _days_since(started_at, now)
        clock_ready = bool(started_at) and elapsed_days >= WARMUP_REQUIRED_DAYS
        days_remaining = max(0, WARMUP_REQUIRED_DAYS - elapsed_days)

        records = [dict(r) for r in block.get("mailboxes") or []]
        warmbly = dict(block.get("warmbly") or {})
        senders = [str(r.get("email") or "") for r in records if r.get("email")]
        if not senders:
            senders = await self._senders(tenant_id)

        blockers: list[dict] = []
        warnings: list[dict] = []

        if mode == "off":
            warnings.append({
                "code": "warmup_enforcement_off",
                "message": "Mailbox warmup enforcement is explicitly disabled (SLIDEIN_WARMUP_ENFORCE=off).",
                "recovery_action": "configure_warmup_enforcement",
            })
        elif not enforced:
            warnings.append({
                "code": "warmbly_not_configured",
                "message": "Warmbly is not part of this deployment (WARMBLY_URL unset), so the 14-day warmup rule cannot be enforced.",
                "recovery_action": "configure_warmbly",
            })
        else:
            if not started_at:
                blockers.append({
                    "code": "mailbox_warmup_not_started",
                    "message": (
                        f"Mailbox warmup has not started; live campaigns require "
                        f"{WARMUP_REQUIRED_DAYS} days of Warmbly warmup first."
                    ),
                    "recovery_action": "start_mailbox_warmup",
                })
            wb_state = str(warmbly.get("state") or "not_checked")
            if wb_state in {"unreachable", "unauthorized", "http_error", "error"}:
                blockers.append({
                    "code": f"warmbly_{wb_state}" if wb_state != "http_error" else "warmbly_http_error",
                    "message": (
                        "Warmbly cannot be reached, so warmup progress cannot be verified: "
                        f"{warmbly.get('detail') or wb_state}."
                    ),
                    "recovery_action": "check_warmbly",
                })
            elif wb_state == "not_configured":
                blockers.append({
                    "code": "warmbly_not_configured",
                    "message": (
                        "Warmbly enforcement is required but WARMBLY_URL is not set, "
                        "so warmup cannot be verified."
                    ),
                    "recovery_action": "configure_warmbly",
                })
            if wb_state == "ok":
                missing = [r for r in records if not r.get("in_warmbly")]
                if senders and missing:
                    blockers.append({
                        "code": "warmbly_mailboxes_missing",
                        "message": (
                            "These sending mailboxes are not connected in Warmbly: "
                            + ", ".join(str(r.get("email")) for r in missing) + "."
                        ),
                        "recovery_action": "connect_warmbly_mailboxes",
                    })
                for record in records:
                    if not record.get("in_warmbly"):
                        continue
                    label = str(record.get("email") or "")
                    if not record.get("warmup_enabled"):
                        blockers.append({
                            "code": "mailbox_warmup_disabled",
                            "message": f"Warmup is not enabled for {label} in Warmbly.",
                            "recovery_action": "start_mailbox_warmup",
                        })
                        continue
                    if record.get("warmup_paused"):
                        blockers.append({
                            "code": "mailbox_warmup_paused",
                            "message": f"Warmup is paused for {label} in Warmbly.",
                            "recovery_action": "resume_mailbox_warmup",
                        })
                        continue
                    anchor = _parse(record.get("warmup_started_at"))
                    warmed = _days_since(anchor, now)
                    if warmed < WARMUP_REQUIRED_DAYS:
                        blockers.append({
                            "code": "mailbox_warmup_in_progress",
                            "message": (
                                f"{label} has {warmed} of {WARMUP_REQUIRED_DAYS} warmup days "
                                f"({WARMUP_REQUIRED_DAYS - warmed} to go)."
                            ),
                            "recovery_action": "wait_for_mailbox_warmup",
                        })
                    if str(record.get("auth_state") or "") == "failing":
                        blockers.append({
                            "code": "dns_auth_failing",
                            "message": (
                                f"Sending-domain DNS authentication (SPF/DMARC) is failing for {label}; "
                                "fix the DNS records, then re-run the Warmbly auth check."
                            ),
                            "recovery_action": "fix_dns_records",
                        })
        ready = not blockers if enforced else True
        if not started_at:
            warmup_state = "not_started"
        elif clock_ready or (enforced and warmbly.get("state") == "ok" and not blockers):
            warmup_state = "complete"
        else:
            warmup_state = "warming"

        return {
            "tenant_id": tenant_id,
            "enforcement": mode,
            "enforced": enforced,
            "ready": ready,
            "status": warmup_state,
            "days_required": WARMUP_REQUIRED_DAYS,
            "started_at": block.get("started_at") or "",
            "due_at": block.get("due_at") or "",
            "day": elapsed_days,
            "days_remaining": days_remaining,
            "clock_ready": clock_ready,
            "mailboxes": records,
            "warmbly": warmbly,
            "blockers": blockers,
            "warnings": warnings,
        }

    # -- the gate ----------------------------------------------------------

    async def enforce(self, tenant_id: str, *, transport_name: str) -> None:
        """Raise ``WarmupIncompleteError`` when a live dispatch would violate
        the rule. Dry-run and an uninforced deployment pass through."""
        if transport_name in ("", "dry_run", "base"):
            return
        if not is_enforced():
            return
        state = await self.status(tenant_id, refresh=True)
        if state["ready"]:
            return
        blockers = state["blockers"] or [{
            "code": "mailbox_warmup_incomplete",
            "message": (
                f"Mailbox warmup must complete before live sending "
                f"({state['days_remaining']} of {WARMUP_REQUIRED_DAYS} days remaining)."
            ),
            "recovery_action": "wait_for_mailbox_warmup",
        }]
        first = blockers[0]
        raise WarmupIncompleteError(
            "Mailbox warmup must complete before live campaigns: " + first["message"],
            details={"warmup": state},
            recovery_action=str(first.get("recovery_action") or "wait_for_mailbox_warmup"),
        )
