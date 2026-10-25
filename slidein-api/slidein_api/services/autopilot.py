"""Autopilot — the autonomous background agent loop.

Runs inside the API process (started from the FastAPI lifespan, no client
required) and advances every enabled workspace through the SAME stage
contracts, services and gates the dashboard uses:

    ingest → research → qualify → personalize → approve → send → engage

Nothing here bypasses a safety: every stage goes through `StageRunner`
(contract validation, permissions, StageRun + ActivityLog audit rows) and
`OutreachService.send_draft` (approval policy, suppression, rate limits,
deliverability guard). The loop is additive — KumoMTA stays the MTA, the
deliverability engine stays the approved bulk path, and the transport
defaults to `dry_run` unless `SLIDEIN_TRANSPORT` says otherwise.

Configuration (env, all optional):

============================  ====================================================
``SLIDEIN_AUTOPILOT``         ``0`` disables the whole loop. Default ``1``.
``SLIDEIN_AUTOPILOT_INTERVAL`` Seconds between ticks. Default ``300``.
``SLIDEIN_AUTOPILOT_BATCH``   Prospects advanced per stage per tick. Default ``10``.
``SLIDEIN_AUTOPILOT_MAX_SENDS`` Dispatches per tick. Default ``5``.
``SLIDEIN_AUTOPILOT_INGEST``  Comma-separated CSV paths polled every tick.
``SLIDEIN_AUTOPILOT_CONNECTOR`` Research connector chain. Default ``openosint,website``.
============================  ====================================================

Per-workspace switches (dashboard → Overview → Autopilot card, persisted in
`autopilot_state`): `enabled`, `auto_approve`, `send_enabled`.
"""

from __future__ import annotations

import csv
import logging
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..contracts import StageName
from ..db import session_scope
from ..errors import SlideinError
from ..models import (
    AutopilotState,
    Conversation,
    DraftStatus,
    MessageDraft,
    Prospect,
    ProspectStatus,
    Tenant,
    utcnow,
)
from ..runtime import StageRunner
from .config import ConfigService
from .discovery import DiscoveryService
from .outreach import OutreachService
from .personalization import PersonalizationService
from .qualification import QualificationService
from .research import ResearchService

logger = logging.getLogger("slidein.autopilot")

ACTOR = "service:autopilot"
ACTOR_ROLE = "operator"

#: CSV columns accepted from ingest sources (unknown columns ignored).
CSV_FIELDS = (
    "first_name", "last_name", "email", "phone", "company_name",
    "company_domain", "job_title", "location", "linkedin_url",
)

_STEPS = ("discovery", "research", "qualification", "personalization", "outreach")


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: str = "1") -> bool:
    return _env(name, default).lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(_env(name, str(default))))
    except ValueError:
        return default


@dataclass(frozen=True)
class AutopilotConfig:
    """Effective loop configuration for one process (env-derived)."""

    master_enabled: bool = True
    interval_seconds: int = 300
    batch: int = 10
    max_sends: int = 5
    ingest_paths: tuple[str, ...] = ()
    connector_chain: tuple[str, ...] = ("openosint", "website")

    @classmethod
    def from_env(cls) -> "AutopilotConfig":
        paths = tuple(
            p.strip()
            for p in _env("SLIDEIN_AUTOPILOT_INGEST", "").split(",")
            if p.strip()
        )
        chain = tuple(
            p.strip()
            for p in _env("SLIDEIN_AUTOPILOT_CONNECTOR", "openosint,website").split(",")
            if p.strip()
        )
        return cls(
            master_enabled=_env_bool("SLIDEIN_AUTOPILOT", "1"),
            interval_seconds=_env_int("SLIDEIN_AUTOPILOT_INTERVAL", 300),
            batch=_env_int("SLIDEIN_AUTOPILOT_BATCH", 10),
            max_sends=_env_int("SLIDEIN_AUTOPILOT_MAX_SENDS", 5),
            ingest_paths=paths,
            connector_chain=chain or ("website",),
        )


def transport_kind() -> str:
    """What the send step would use right now (payload config is empty)."""
    return (_env("SLIDEIN_TRANSPORT", "") or "dry_run").lower()


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

async def get_state(session: AsyncSession, tenant_id: str) -> AutopilotState:
    row = await session.get(AutopilotState, tenant_id)
    if row is None:
        # The FK points at tenants: make sure the workspace row exists first
        # (bare workspaces are legal — the loop just reports them as blocked).
        await ConfigService(session).ensure_tenant(tenant_id)
        row = AutopilotState(tenant_id=tenant_id)
        session.add(row)
        await session.flush()
    return row


async def save_state(session: AsyncSession, tenant_id: str, updates: dict) -> AutopilotState:
    row = await get_state(session, tenant_id)
    for key, value in updates.items():
        setattr(row, key, value)
    row.updated_by = ACTOR
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# Ingest (find & capture → DiscoveryService is the only creator of records)
# ---------------------------------------------------------------------------

def _read_csv_records(path: Path) -> tuple[list[dict], int]:
    """Rows → prospect records; returns (records, skipped_row_count)."""
    records: list[dict] = []
    skipped = 0
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for raw in csv.DictReader(fh):
            row = {
                key: str(raw.get(key) or "").strip()
                for key in CSV_FIELDS
            }
            if not row["email"] or "@" not in row["email"]:
                skipped += 1
                continue
            if row.get("company_size"):
                try:
                    row["company_size"] = int(row["company_size"])
                except ValueError:
                    row["company_size"] = None
            else:
                row["company_size"] = None
            records.append(row)
    return records, skipped


async def _ingest_sources(session: AsyncSession, tenant_id: str, cfg: AutopilotConfig, stats: Counter) -> None:
    """Pull configured CSV lead files into the workspace (idempotent)."""
    if not cfg.ingest_paths:
        return
    config = ConfigService(session)
    active_icp = await config.active_icp(tenant_id)
    if active_icp is None:
        stats["ingest_blocked"] += 1
        stats["ingest_block_icp_missing"] += 1
        logger.info("autopilot ingest blocked for %s: icp_missing", tenant_id)
        return
    profile = await config.active_profile(tenant_id)
    if profile is None:
        stats["ingest_blocked"] += 1
        stats["ingest_block_profile_missing"] += 1
        return

    for raw_path in cfg.ingest_paths:
        path = Path(raw_path).expanduser()
        if not path.is_file():
            stats["ingest_missing"] += 1
            logger.warning("autopilot ingest source missing: %s", path)
            continue
        try:
            records, skipped = _read_csv_records(path)
        except OSError as exc:
            logger.warning("autopilot cannot read %s: %s", path, exc)
            stats["ingest_errors"] += 1
            continue
        stats["ingest_skipped"] += skipped
        if not records:
            continue
        outcome = await DiscoveryService(session).create_records(
            tenant_id,
            icp_id=active_icp["id"],
            records=records,
            source="autopilot",
            source_ref=str(path),
            profile_id=profile["id"],
            profile_version=profile["version"],
            created_by=ACTOR,
        )
        stats["ingested"] += int(outcome.get("created", 0) or 0)
        stats["ingest_duplicates"] += int(outcome.get("duplicates", 0) or 0)
        from .suppression import SuppressionService

        await SuppressionService(session).seed_defaults(tenant_id)


# ---------------------------------------------------------------------------
# Stage executors — same logic the pipeline routes run, actor = autopilot
# ---------------------------------------------------------------------------

async def _research_prospect(
    session: AsyncSession, tenant_id: str, prospect_id: str, cfg: AutopilotConfig
) -> dict:
    """Run the research stage; tries the connector chain in order."""
    discovery = DiscoveryService(session)
    prospect = await discovery.get_prospect(tenant_id, prospect_id)
    if prospect is None:
        raise SlideinError(
            f"Prospect {prospect_id!r} disappeared before research",
            code="prospect_not_found",
            recovery_action="return_to_discovery",
        )

    async def executor(stage_payload: dict, sess) -> dict:
        from_status = prospect.status
        already_advanced = from_status not in ("discovered", "researched")
        if not already_advanced:
            await discovery.apply_transition(
                prospect,
                to_status="researching",
                reason="research started by autopilot",
                actor=ACTOR,
                stage=StageName.RESEARCH.value,
            )

        last_error: SlideinError | None = None
        result: dict | None = None
        for connector in cfg.connector_chain:
            try:
                result = await ResearchService(sess).collect_evidence(
                    tenant_id=tenant_id,
                    prospect=prospect,
                    depth="standard",
                    connector=connector,
                    actor=ACTOR,
                )
                break
            except SlideinError as exc:
                last_error = exc
                logger.info(
                    "autopilot research connector %s failed on %s: %s",
                    connector, prospect.email, exc.code,
                )
        if result is None:
            raise last_error or SlideinError(
                "No research connector produced evidence",
                code="source_unavailable",
                recovery_action="retry_stage",
            )

        to_status = from_status
        if not already_advanced:
            await discovery.apply_transition(
                prospect,
                to_status="researched",
                reason=f"research completed with {result['evidence_count']} evidence item(s)",
                actor=ACTOR,
                stage=StageName.RESEARCH.value,
            )
            to_status = "researched"
        return {
            "status": "succeeded",
            "outputs": result,
            "needs_review": [] if result["verified_count"] else ["no verified evidence"],
            "from_status": from_status,
            "to_status": to_status,
        }

    runner = StageRunner(session)
    return runner_outcome_dict(
        await runner.run(
            StageName.RESEARCH,
            tenant_id=tenant_id,
            payload={"prospect_id": prospect_id, "depth": "standard", "claims": []},
            actor=ACTOR,
            role=ACTOR_ROLE,
            subject_id=prospect_id,
            executor=executor,
        )
    )


async def _qualify_prospect(session: AsyncSession, tenant_id: str, prospect_id: str) -> dict:
    async def executor(stage_payload: dict, sess) -> dict:
        discovery = DiscoveryService(sess)
        config = ConfigService(sess)
        prospect = await discovery.get_prospect(tenant_id, prospect_id)
        if prospect is None:
            raise SlideinError(
                f"Prospect {prospect_id!r} does not exist",
                code="prospect_not_found",
                recovery_action="return_to_discovery",
            )

        research = ResearchService(sess)
        evidence_rows = await research.list_evidence(tenant_id, prospect_id)
        if not evidence_rows:
            raise SlideinError(
                "Research has not produced any evidence for this prospect",
                code="stage_prerequisite",
                details={"stage": "research"},
                recovery_action="run_prerequisite_stage",
            )

        icp_rec = await config.get_icp(tenant_id, prospect.icp_id) if prospect.icp_id else None
        if icp_rec is None:
            icp_rec = await config.active_icp(tenant_id)
            if icp_rec is None:
                raise SlideinError(
                    "No active ICP to qualify against",
                    code="icp_missing",
                    recovery_action="define_icp",
                )

        from_status = prospect.status
        result = await QualificationService(sess).record(
            tenant_id=tenant_id,
            prospect=prospect,
            icp=icp_rec,
            evidence_rows=evidence_rows,
            actor=ACTOR,
        )
        prospect.qualification_score = result["score"]
        prospect.icp_id = icp_rec["id"]
        prospect.icp_version = icp_rec.get("version")
        if result.get("offer_match"):
            prospect.offer_id = result["offer_match"]["offer_id"]
        await sess.flush()

        if from_status != "researched":
            raise SlideinError(
                f"Qualification requires the prospect to be researched (it is {from_status!r})",
                code="stage_prerequisite",
                details={"stage": "research", "prospect_status": from_status},
                recovery_action="run_prerequisite_stage",
            )

        to_status = "qualified" if result["is_qualified"] else "disqualified"
        await discovery.apply_transition(
            prospect,
            to_status=to_status,
            reason=result["explanation"][:500],
            actor=ACTOR,
            stage=StageName.QUALIFY.value,
        )
        return {
            "status": "succeeded",
            "outputs": result,
            "needs_review": [],
            "from_status": from_status,
            "to_status": to_status,
        }

    runner = StageRunner(session)
    return runner_outcome_dict(
        await runner.run(
            StageName.QUALIFY,
            tenant_id=tenant_id,
            payload={"prospect_id": prospect_id},
            actor=ACTOR,
            role=ACTOR_ROLE,
            subject_id=prospect_id,
            executor=executor,
        )
    )


async def _personalize_prospect(session: AsyncSession, tenant_id: str, prospect_id: str) -> dict:
    async def executor(stage_payload: dict, sess) -> dict:
        discovery = DiscoveryService(sess)
        prospect = await discovery.get_prospect(tenant_id, prospect_id)
        if prospect is None:
            raise SlideinError(
                f"Prospect {prospect_id!r} does not exist",
                code="prospect_not_found",
                recovery_action="return_to_discovery",
            )
        if prospect.status != "qualified":
            raise SlideinError(
                f"Personalization requires a qualified prospect (status is {prospect.status!r})",
                code="stage_prerequisite",
                details={"stage": "qualify", "prospect_status": prospect.status},
                recovery_action="run_prerequisite_stage",
            )
        result = await PersonalizationService(sess).generate_draft(
            tenant_id=tenant_id,
            prospect=prospect,
            actor=ACTOR,
        )
        await discovery.apply_transition(
            prospect,
            to_status="draft_ready",
            reason=f"draft v{result['version']} prepared",
            actor=ACTOR,
            stage=StageName.PERSONALIZE.value,
        )
        return {
            "status": "succeeded",
            "outputs": result,
            "needs_review": [],
            "from_status": "qualified",
            "to_status": "draft_ready",
        }

    runner = StageRunner(session)
    return runner_outcome_dict(
        await runner.run(
            StageName.PERSONALIZE,
            tenant_id=tenant_id,
            payload={"prospect_id": prospect_id},
            actor=ACTOR,
            role=ACTOR_ROLE,
            subject_id=prospect_id,
            executor=executor,
        )
    )


async def _send_draft(session: AsyncSession, tenant_id: str, draft_id: str) -> dict:
    async def executor(stage_payload: dict, sess) -> dict:
        outreach = OutreachService(sess)
        result = await outreach.send_draft(
            tenant_id=tenant_id,
            draft_id=draft_id,
            actor=ACTOR,
            sender_email=str(stage_payload.get("sender_email") or ""),
            transport_config={},  # env-resolved (SLIDEIN_TRANSPORT / KUMO_*)
        )
        return {
            "status": "succeeded",
            "outputs": result,
            "needs_review": [],
            "from_status": DraftStatus.APPROVED.value,
            "to_status": ProspectStatus.IN_CAMPAIGN.value,
        }

    runner = StageRunner(session)
    return runner_outcome_dict(
        await runner.run(
            StageName.OUTREACH,
            tenant_id=tenant_id,
            payload={"draft_id": draft_id, "approved": True},
            actor=ACTOR,
            role=ACTOR_ROLE,
            subject_type="draft",
            subject_id=draft_id,
            executor=executor,
        )
    )


def runner_outcome_dict(outcome) -> dict:
    return {
        "status": outcome.status,
        "needs_review": outcome.needs_review,
        "to_status": outcome.to_status,
        "error_code": outcome.error_code,
        "error_message": outcome.error_message,
    }


# ---------------------------------------------------------------------------
# The tick
# ---------------------------------------------------------------------------

async def _enabled_steps(session: AsyncSession, tenant_id: str) -> set[str]:
    from .templates import TemplateService

    effective = await TemplateService(session).effective(tenant_id)
    return set(effective["modules"]["enabled"])


async def tick(tenant_id: str, cfg: AutopilotConfig | None = None) -> dict:
    """Advance one workspace one step everywhere it can. Never raises."""
    cfg = cfg or AutopilotConfig.from_env()
    stats: Counter = Counter()
    if not cfg.master_enabled:
        return {"status": "disabled", "stats": {}}

    try:
        async with session_scope() as session:
            state = await get_state(session, tenant_id)
            if not state.enabled:
                return {"status": "workspace_disabled", "stats": {}}
            steps = await _enabled_steps(session, tenant_id)
            auto_approve = state.auto_approve
            send_enabled = state.send_enabled
    except SlideinError as exc:
        return {"status": "blocked", "error": exc.code, "stats": {}}

    try:
        async with session_scope() as session:
            if "discovery" in steps:
                await _ingest_sources(session, tenant_id, cfg, stats)

            if "research" in steps:
                ids = await _ids(session, Prospect.tenant_id == tenant_id, Prospect.status == "discovered", limit=cfg.batch)
                for pid in ids:
                    await _advance(session, stats, "researched", _research_prospect(session, tenant_id, pid, cfg), pid)

            if "qualification" in steps:
                ids = await _ids(session, Prospect.tenant_id == tenant_id, Prospect.status == "researched", limit=cfg.batch)
                for pid in ids:
                    outcome = await _stage(session, stats, _qualify_prospect(session, tenant_id, pid), pid)
                    if outcome and outcome.get("to_status") == "qualified":
                        stats["qualified"] += 1
                    elif outcome and outcome.get("to_status") == "disqualified":
                        stats["disqualified"] += 1

            if "personalization" in steps:
                ids = await _ids(session, Prospect.tenant_id == tenant_id, Prospect.status == "qualified", limit=cfg.batch)
                for pid in ids:
                    await _advance(session, stats, "drafts", _personalize_prospect(session, tenant_id, pid), pid)

            if "outreach" in steps and auto_approve:
                draft_ids = await _draft_ids(session, tenant_id, DraftStatus.PENDING_REVIEW.value, limit=cfg.batch)
                outreach = OutreachService(session)
                for did in draft_ids:
                    try:
                        await outreach.approve_draft(
                            tenant_id=tenant_id, draft_id=did, actor=ACTOR,
                            note="autopilot auto-approval (evidence-backed draft)",
                        )
                        stats["approved"] += 1
                    except SlideinError as exc:
                        stats["approve_failed"] += 1
                        logger.info("autopilot approve failed %s: %s", did, exc.code)

            if "outreach" in steps and send_enabled:
                draft_ids = await _draft_ids(session, tenant_id, DraftStatus.APPROVED.value, limit=cfg.max_sends)
                for did in draft_ids:
                    outcome = await _send_draft(session, tenant_id, did)
                    if outcome["status"] in ("succeeded", "needs_review"):
                        stats["sent"] += 1
                    else:
                        stats["send_failed"] += 1

            # Engage: replies arrive via the inbound webhook; surface counts.
            stats["replied"] = await _count(session, Prospect.tenant_id == tenant_id, Prospect.status == "replied")
            stats["opted_out"] = await _count(session, Prospect.tenant_id == tenant_id, Prospect.status == "opted_out")

        async with session_scope() as session:
            await _persist_tick(session, tenant_id, stats, "ok", "")
        return {"status": "ok", "stats": dict(stats)}
    except SlideinError as exc:
        logger.warning("autopilot tick blocked for %s: %s", tenant_id, exc.code)
        async with session_scope() as session:
            await _persist_tick(session, tenant_id, stats, "blocked", f"{exc.code}: {exc.message}")
        return {"status": "blocked", "error": exc.code, "stats": dict(stats)}
    except Exception as exc:  # noqa: BLE001 — the loop must survive anything
        logger.exception("autopilot tick crashed for %s", tenant_id)
        async with session_scope() as session:
            await _persist_tick(session, tenant_id, stats, "failed", f"{type(exc).__name__}: {exc}")
        return {"status": "failed", "error": str(exc), "stats": dict(stats)}


async def _advance(session: AsyncSession, stats: Counter, success_key: str | None, coro, prospect_id: str) -> str:
    outcome = await _stage(session, stats, coro, prospect_id)
    if outcome and outcome["status"] in ("succeeded", "needs_review"):
        if success_key:
            stats[success_key] += 1
        return "ok"
    return ""


async def _stage(session: AsyncSession, stats: Counter, coro, prospect_id: str) -> dict | None:
    try:
        outcome = await coro
    except SlideinError as exc:
        stats["errors"] += 1
        logger.info("autopilot stage failed on %s: %s", prospect_id, exc.code)
        return None
    if outcome["status"] not in ("succeeded", "needs_review"):
        stats["errors"] += 1
    return outcome


async def _persist_tick(session: AsyncSession, tenant_id: str, stats: Counter, status: str, error: str) -> None:
    row = await get_state(session, tenant_id)
    row.last_tick_at = utcnow()
    row.last_status = status
    row.last_error = error
    row.last_stats = dict(stats)
    totals = dict(row.totals or {})
    for key, value in stats.items():
        totals[key] = int(totals.get(key, 0)) + int(value)
    row.totals = totals
    row.updated_by = ACTOR
    await session.flush()


async def _ids(session: AsyncSession, *conditions, limit: int) -> list[str]:
    rows = (
        await session.execute(
            select(Prospect.id).where(*conditions).order_by(Prospect.discovered_at).limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def _draft_ids(session: AsyncSession, tenant_id: str, status: str, limit: int) -> list[str]:
    rows = (
        await session.execute(
            select(MessageDraft.id)
            .where(MessageDraft.tenant_id == tenant_id, MessageDraft.status == status)
            .order_by(MessageDraft.created_at)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def _count(session: AsyncSession, *conditions) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(Prospect).where(*conditions))).scalar() or 0
    )


# ---------------------------------------------------------------------------
# Status + control plane (used by the routes and the dashboard)
# ---------------------------------------------------------------------------

async def status_payload(tenant_id: str) -> dict:
    cfg = AutopilotConfig.from_env()
    async with session_scope() as session:
        state = await get_state(session, tenant_id)
        pipeline = {
            status: await _count(session, Prospect.tenant_id == tenant_id, Prospect.status == status)
            for status in (
                "discovered", "researching", "researched", "qualified",
                "disqualified", "draft_ready", "in_campaign", "replied", "opted_out",
            )
        }
        drafts = {
            status: int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(MessageDraft)
                        .where(MessageDraft.tenant_id == tenant_id, MessageDraft.status == status)
                    )
                ).scalar()
                or 0
            )
            for status in (
                DraftStatus.PENDING_REVIEW.value, DraftStatus.APPROVED.value,
                DraftStatus.SENT.value, DraftStatus.REJECTED.value,
            )
        }
        open_conversations = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(Conversation)
                    .where(
                        Conversation.tenant_id == tenant_id,
                        Conversation.state == "open",
                    )
                )
            ).scalar()
            or 0
        )
        return {
            "enabled": state.enabled,
            "auto_approve": state.auto_approve,
            "send_enabled": state.send_enabled,
            "master_enabled": cfg.master_enabled,
            "interval_seconds": cfg.interval_seconds,
            "batch": cfg.batch,
            "max_sends": cfg.max_sends,
            "transport": transport_kind(),
            "ingest_sources": list(cfg.ingest_paths),
            "connector_chain": list(cfg.connector_chain),
            "last_tick_at": state.last_tick_at.isoformat() if state.last_tick_at else None,
            "last_status": state.last_status,
            "last_error": state.last_error,
            "last_stats": dict(state.last_stats or {}),
            "totals": dict(state.totals or {}),
            "pipeline": pipeline,
            "drafts": drafts,
            "open_conversations": open_conversations,
        }


async def set_switches(
    tenant_id: str, *, actor: str, enabled: bool | None = None,
    auto_approve: bool | None = None, send_enabled: bool | None = None,
) -> dict:
    async with session_scope() as session:
        await save_state(
            session,
            tenant_id,
            {
                key: value
                for key, value in (
                    ("enabled", enabled), ("auto_approve", auto_approve),
                    ("send_enabled", send_enabled),
                )
                if value is not None
            }
            | {"updated_by": actor},
        )
    return await status_payload(tenant_id)


async def run_all_tenants(cfg: AutopilotConfig | None = None) -> dict[str, dict]:
    """One tick across every workspace. Called by the lifespan loop."""
    cfg = cfg or AutopilotConfig.from_env()
    async with session_scope() as session:
        tenant_ids = list((await session.execute(select(Tenant.id))).scalars().all())
    results: dict[str, dict] = {}
    for tenant_id in tenant_ids:
        results[tenant_id] = await tick(tenant_id, cfg)
    return results
