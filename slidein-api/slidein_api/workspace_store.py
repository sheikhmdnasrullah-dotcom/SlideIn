"""Instance-durable persistence for the adaptive workspace.

Each client instance has its OWN database (deployment independence, §3 of
the product north star) — these tables store that instance's workspace
config versions, evidence, and adaptation proposals. Write-through on every
mutation; hydrate-on-first-touch per tenant after a process restart, so an
instance never loses its adaptations or config history.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, String, select

from .db import session_scope
from .models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceConfigRow(Base):
    __tablename__ = "workspace_config_versions"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(64), index=True)
    version = Column(Float)
    payload = Column(JSON)          # full serialised WorkspaceConfig
    created_at = Column(DateTime, default=_utcnow)


class WorkspaceEvidenceRow(Base):
    __tablename__ = "workspace_evidence"

    evidence_id = Column(String(16), primary_key=True)
    tenant_id = Column(String(64), index=True)
    kind = Column(String(32))
    fact = Column(String(1024))
    source_ref = Column(String(256))
    confidence = Column(Float)
    verified = Column(Boolean, default=False)
    ts = Column(DateTime, default=_utcnow)


class WorkspaceProposalRow(Base):
    __tablename__ = "workspace_proposals"

    proposal_id = Column(String(16), primary_key=True)
    tenant_id = Column(String(64), index=True)
    risk = Column(String(16))
    changes = Column(JSON)
    rationale = Column(String(1024))
    status = Column(String(24), default="pending_approval")
    created_at = Column(DateTime, default=_utcnow)


class SetupStatusRow(Base):
    __tablename__ = "setup_status"

    tenant_id = Column(String(64), primary_key=True)
    state = Column(String(32))
    payload = Column(JSON)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


async def persist_setup_status(status) -> None:
    async with session_scope() as s:
        row = await s.get(SetupStatusRow, status.tenant_id)
        if row is None:
            row = SetupStatusRow(tenant_id=status.tenant_id)
            s.add(row)
        row.state = status.state
        row.payload = {
            "profile_id": status.profile_id,
            "config_version": status.config_version,
            "workflow_proposal_id": status.workflow_proposal_id,
            "blockers": list(status.blockers),
            "questions": list(status.questions),
            "next_action": status.next_action,
        }


async def load_setup_status(tenant_id: str):
    async with session_scope() as s:
        row = await s.get(SetupStatusRow, tenant_id)
        if row is None:
            return None
        return {"tenant_id": row.tenant_id, "state": row.state, **(row.payload or {})}


async def persist_config(cfg) -> None:
    import uuid as _uuid
    from product.core.workspace import WidgetConfig
    payload = {
        "tenant_id": cfg.tenant_id,
        "version": cfg.version,
        "enabled_modules": list(cfg.enabled_modules),
        "module_order": list(cfg.module_order),
        "nav_groups": {k: list(v) for k, v in cfg.nav_groups.items()},
        "widgets": [{"module_id": w.module_id, "widget_type": w.widget_type,
                     "settings": w.settings} for w in cfg.widgets],
        "metrics": list(cfg.metrics),
        "workflow_refs": list(cfg.workflow_refs),
        "agent_refs": list(cfg.agent_refs),
        "integration_refs": list(cfg.integration_refs),
        "display": dict(cfg.display),
        "role_visibility": {k: list(v) for k, v in cfg.role_visibility.items()},
    }
    async with session_scope() as s:
        s.add(WorkspaceConfigRow(id=_uuid.uuid4().hex, tenant_id=cfg.tenant_id,
                                 version=cfg.version, payload=payload))


async def persist_evidence(item) -> None:
    async with session_scope() as s:
        s.add(WorkspaceEvidenceRow(
            evidence_id=item.evidence_id, tenant_id=item.tenant_id,
            kind=item.kind, fact=item.fact, source_ref=item.source_ref,
            confidence=item.confidence, verified=item.verified, ts=item.ts))


async def persist_proposal(entry: dict, tenant_id: str) -> None:
    async with session_scope() as s:
        row = await s.get(WorkspaceProposalRow, entry["proposal_id"])
        if row is None:
            row = WorkspaceProposalRow(proposal_id=entry["proposal_id"],
                                       tenant_id=tenant_id)
            s.add(row)
        row.risk = entry["risk"]
        row.changes = json.loads(json.dumps(entry["changes"], default=str))
        row.rationale = entry["rationale"]
        row.status = entry["status"]


async def load_tenant(tenant_id: str, *, workspaces, evidence_store,
                      proposal_ledger) -> bool:
    """Hydrate in-process stores from the instance DB. Returns True when the
    tenant had persisted state (i.e. this is a restart, not first boot)."""
    from dataclasses import replace
    from product.core.workspace import WidgetConfig, WorkspaceConfig
    async with session_scope() as s:
        cfg_rows = (await s.execute(select(WorkspaceConfigRow)
                  .where(WorkspaceConfigRow.tenant_id == tenant_id)
                  .order_by(WorkspaceConfigRow.version))).scalars().all()
        ev_rows = (await s.execute(select(WorkspaceEvidenceRow)
                 .where(WorkspaceEvidenceRow.tenant_id == tenant_id))).scalars().all()
        pr_rows = (await s.execute(select(WorkspaceProposalRow)
                 .where(WorkspaceProposalRow.tenant_id == tenant_id))).scalars().all()
    if not cfg_rows:
        return False
    workspaces._history[tenant_id] = []
    for row in cfg_rows:
        p = row.payload
        cfg = WorkspaceConfig(
            tenant_id=p["tenant_id"], version=int(p["version"]),
            enabled_modules=tuple(p["enabled_modules"]),
            module_order=tuple(p["module_order"]),
            nav_groups={k: tuple(v) for k, v in p["nav_groups"].items()},
            widgets=tuple(WidgetConfig(**w) for w in p["widgets"]),
            metrics=tuple(p.get("metrics", ())),
            workflow_refs=tuple(p.get("workflow_refs", ())),
            agent_refs=tuple(p.get("agent_refs", ())),
            integration_refs=tuple(p.get("integration_refs", ())),
            display=dict(p.get("display", {})),
            role_visibility={k: tuple(v) for k, v in p.get("role_visibility", {}).items()},
        )
        workspaces._history[tenant_id].append(cfg)
        workspaces._current[tenant_id] = cfg
    ev_items = []
    for row in ev_rows:
        from product.core.adaptation import Evidence
        ev_items.append(Evidence(tenant_id=row.tenant_id, kind=row.kind,
                                 fact=row.fact, source_ref=row.source_ref,
                                 confidence=row.confidence or 0.5,
                                 verified=bool(row.verified),
                                 evidence_id=row.evidence_id, ts=row.ts))
    evidence_store._items[tenant_id] = ev_items
    ledger = proposal_ledger.setdefault(tenant_id, {})
    for row in pr_rows:
        ledger[row.proposal_id] = {
            "proposal_id": row.proposal_id, "risk": row.risk,
            "changes": row.changes or {}, "rationale": row.rationale or "",
            "status": row.status,
        }
    return True
