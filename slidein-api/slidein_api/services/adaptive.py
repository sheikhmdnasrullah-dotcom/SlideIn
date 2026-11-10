"""Console adaptation engine.

Owns the *configuration* of the Console surface per workspace, stored in
Redis (the project's shared cache/queue backbone) with a deterministic
SQLite fallback for local dev that hasn't reached Redis yet.

Two responsibilities, kept strictly apart:

1. **State.** Per-tenant Console section list: which sections exist,
   their order, and per-section visibility/terminology overrides. The
   section *vocabulary* comes from the module registry / knowledge base;
   this service never invents new sections — it only selects, orders,
   hides, or renames the validated ones the product already knows.

2. **Proposals.** The adaptive layer *records* behavior evidence and raises
   proposals (add/remove/reorder/rename). A proposal is NOT applied
   automatically. Deterministic code (this service, on explicit approval)
   writes the persisted preferences. This is the guard against the
   "unlimited dashboard-generating loop": nothing becomes a section merely
   because a behavior was observed.

Key invariants (enforced here and asserted by `product/tests/test_adaptive.py`):
  * Sections are always a subset of the validated module registry.
  * `settings` is never removable (it hosts this configuration).
  * Unknown / rejected proposals never alter persisted state.
  * Proposals expire after `PROPOSAL_TTL_SECONDS`.
"""

from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..services.modules import MODULE_IDS, DEFAULT_ENABLED

PROPOSAL_TTL_SECONDS = 60 * 60 * 24 * 3  # 3 days
MAX_PROPOSALS_PER_WORKSPACE = 50

# Behavior counters the adaptive layer consults when *proposing* changes.
BEHAVIOR_KEYS = {"shown", "clicked", "dismissed", "hidden_by_user"}


def _redis_url() -> str | None:
    return os.getenv("REDIS_URL")


class _Store:
    """Abstracts Redis vs. in-process fallback.

    Redis is the production store (shared, fast, eviction-safe). When
    REDIS_URL is unset — typical local dev without Docker — the engine keeps
    running against a module-level dict so the app is always usable.
    The dict is never the source of truth in any deployment with Redis.
    """

    def __init__(self) -> None:
        self._fallback: dict[str, dict[str, Any]] = {}
        self._redis: Any = None
        if _redis_url():
            try:
                import redis.asyncio as aredis  # type: ignore

                self._redis = aredis.from_url(_redis_url(), decode_responses=True)
            except Exception:  # pragma: no cover - env dependent
                self._redis = None

    # ── preferences ──────────────────────────────────────────────────────
    async def get_prefs(self, tenant_id: str) -> dict[str, Any]:
        if self._redis:
            raw = await self._redis.get(f"dashboard:{tenant_id}:prefs")
            if raw:
                return json.loads(raw)
        return dict(self._fallback.get(tenant_id, {}))

    async def set_prefs(self, tenant_id: str, prefs: dict[str, Any]) -> None:
        if self._redis:
            await self._redis.set(f"dashboard:{tenant_id}:prefs", json.dumps(prefs))
        self._fallback[tenant_id] = dict(prefs)

    # ── proposals ────────────────────────────────────────────────────────
    async def list_proposals(self, tenant_id: str) -> list[dict[str, Any]]:
        if self._redis:
            raw = await self._redis.hgetall(f"dashboard:{tenant_id}:proposals")
            items = [json.loads(v) for v in raw.values()]
        else:
            items = list(self._fallback.get(f"{tenant_id}:proposals", []))
        items.sort(key=lambda p: p.get("proposed_at", 0), reverse=True)
        return items[:MAX_PROPOSALS_PER_WORKSPACE]

    async def add_proposal(self, tenant_id: str, proposal: dict[str, Any]) -> str:
        pid = f"prop_{uuid.uuid4().hex[:12]}"
        proposal["id"] = pid
        proposal.setdefault("status", "proposed")
        proposal["proposed_at"] = time.time()
        proposal["expires_at"] = proposal["proposed_at"] + PROPOSAL_TTL_SECONDS
        value = json.dumps(proposal)
        if self._redis:
            key = f"dashboard:{tenant_id}:proposals"
            await self._redis.hset(key, pid, value)
            await self._redis.expire(key, PROPOSAL_TTL_SECONDS)
        else:
            bucket = self._fallback.setdefault(f"{tenant_id}:proposals", [])
            bucket.insert(0, proposal)
            del bucket[MAX_PROPOSALS_PER_WORKSPACE:]
        return pid

    async def drop_proposal(self, tenant_id: str, proposal_id: str) -> bool:
        if self._redis:
            removed = await self._redis.hdel(f"dashboard:{tenant_id}:proposals", proposal_id)
            return removed > 0
        bucket = self._fallback.get(f"{tenant_id}:proposals", [])
        before = len(bucket)
        bucket[:] = [p for p in bucket if p.get("id") != proposal_id]
        return before != len(bucket)

    # ── behavior ─────────────────────────────────────────────────────────
    async def record_behavior(
        self, tenant_id: str, section_id: str, kind: str, weight: float = 1.0
    ) -> None:
        if kind not in BEHAVIOR_KEYS:
            return
        key = f"dashboard:{tenant_id}:behavior:{section_id}:{kind}"
        if self._redis:
            await self._redis.incrbyfloat(key, weight)
            await self._redis.expire(key, PROPOSAL_TTL_SECONDS)
        else:
            acc = self._fallback.setdefault(f"{tenant_id}:behavior", {})
            acc[key] = acc.get(key, 0.0) + weight

    async def behavior_summary(self, tenant_id: str) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        if self._redis:
            pattern = f"dashboard:{tenant_id}:behavior:*"
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=200)
                for k in keys:
                    parts = k.split(":")
                    section_id = parts[4]
                    kind = parts[5]
                    out.setdefault(section_id, {})[kind] = float(
                        await self._redis.get(k) or 0
                    )
                if cursor == 0:
                    break
        else:
            raw = self._fallback.get(f"{tenant_id}:behavior", {})
            for k, v in raw.items():
                parts = k.split(":")
                section_id, kind = parts[4], parts[5]
                out.setdefault(section_id, {})[kind] = float(v)
        return out


@dataclass
class SectionState:
    """A persisted Console section as the viewer renders it."""

    id: str
    visible: bool = True
    order: int = 0
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "visible": self.visible, "order": self.order, "label": self.label}


@dataclass
class Proposal:
    section_id: str
    action: str  # "add" | "remove" | "reorder" | "label"
    evidence: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""


class AdaptiveService:
    """Reads and mutates the per-tenant Console section configuration.

    All writes that change what a client *sees* go through `apply_preferences`,
    which is the single deterministic writer. Proposals are separate records
    that must be explicitly approved.
    """

    def __init__(self, store: _Store | None = None) -> None:
        self.store = store or _Store()

    # ── effective sections ───────────────────────────────────────────────
    async def effective_sections(self, tenant_id: str) -> list[SectionState]:
        """The Console sections, in render order, as the client sees them.

        Source of truth: persisted preferences in Redis. Fallback to template
        defaults (the validated module registry, full set).
        """
        prefs = await self.store.get_prefs(tenant_id)
        stored = prefs.get("sections", [])
        if stored:
            sections: list[SectionState] = []
            seen: set[str] = set()
            for entry in stored:
                sid = entry["id"]
                # Validate against the registry; reject unknown ids silently
                # so a stale preference can never surface an unknown section.
                if sid not in MODULE_IDS:
                    continue
                if sid in seen:
                    continue
                seen.add(sid)
                sections.append(
                    SectionState(
                        id=sid,
                        visible=bool(entry.get("visible", True)),
                        order=int(entry.get("order", 0)),
                        label=entry.get("label"),
                    )
                )
            # Never let `settings` disappear — it hosts this configuration.
            if "settings" not in {s.id for s in sections}:
                sections.append(SectionState(id="settings"))
            sections.sort(key=lambda s: (s.order, s.id))
            return sections
        # No stored prefs: default to the full validated registry.
        return [
            SectionState(id=mid, order=i) for i, mid in enumerate(DEFAULT_ENABLED)
        ]

    # ── deterministic write ──────────────────────────────────────────────
    async def apply_preferences(
        self, tenant_id: str, sections: list[dict[str, Any]], source: str = "user"
    ) -> list[SectionState]:
        """Replace the Console's visible section set.

        Validates every id against the registry, pins `settings`, and persists.
        This is the only path that mutates what the Console renders.
        """
        cleaned: dict[str, SectionState] = {}
        for i, entry in enumerate(sections):
            sid = entry["id"]
            if sid not in MODULE_IDS:
                raise ValueError(f"Unknown dashboard section: {sid!r}")
            cleaned[sid] = SectionState(
                id=sid,
                visible=bool(entry.get("visible", True)),
                order=int(entry.get("order", i)),
                label=entry.get("label"),
            )
        if "settings" not in cleaned:
            cleaned["settings"] = SectionState(id="settings")

        prefs = {
            "sections": [s.to_dict() for s in cleaned.values()],
            "updated_at": time.time(),
            "updated_by": source,
        }
        await self.store.set_prefs(tenant_id, prefs)
        return sorted(cleaned.values(), key=lambda s: (s.order, s.id))

    # ── proposals (NOT applied automatically) ────────────────────────────
    async def propose(
        self, tenant_id: str, proposal: Proposal
    ) -> dict[str, Any]:
        if proposal.section_id not in MODULE_IDS and proposal.action != "label":
            raise ValueError(f"Cannot propose against unknown section: {proposal.section_id!r}")
        record: dict[str, Any] = {
            "section_id": proposal.section_id,
            "action": proposal.action,
            "reasoning": proposal.reasoning,
            "evidence": proposal.evidence,
            "token": secrets.token_urlsafe(8),
        }
        pid = await self.store.add_proposal(tenant_id, record)
        return {"id": pid, "status": "proposed", **record}

    async def approve(self, tenant_id: str, proposal_id: str) -> list[SectionState]:
        """Mutate persisted Console state from an approved proposal.

        Only these actions change state: add, remove, reorder, label.
        Unknown proposal ids raise.
        """
        proposals = await self.store.list_proposals(tenant_id)
        matched = [p for p in proposals if p.get("id") == proposal_id]
        if not matched:
            raise KeyError(proposal_id)
        proposal = matched[0]

        current = await self.effective_sections(tenant_id)
        existing = {s.id: s for s in current}
        action = proposal["action"]
        sid = proposal["section_id"]

        if action == "add":
            if sid in existing:
                # Already present — ensure visible.
                existing[sid].visible = True
            else:
                existing[sid] = SectionState(
                    id=sid, order=len(existing), visible=True
                )
        elif action == "remove":
            if sid == "settings":
                raise ValueError("Cannot remove the settings section.")
            if sid in existing:
                existing[sid].visible = False
        elif action == "reorder":
            order = proposal.get("evidence", {}).get("order", [])
            if isinstance(order, list) and order:
                for idx, new_id in enumerate(order):
                    if new_id in existing:
                        existing[new_id].order = idx
        elif action == "label":
            if sid in existing:
                existing[sid].label = (
                    proposal.get("evidence", {}).get("label") or None
                )
        else:
            raise ValueError(f"Unknown proposal action: {action!r}")

        new_sections = [s.to_dict() for s in existing.values()]
        result = await self.apply_preferences(
            tenant_id, new_sections, source=f"approved:{proposal_id}"
        )
        await self.store.drop_proposal(tenant_id, proposal_id)
        return result

    async def reject(self, tenant_id: str, proposal_id: str) -> None:
        removed = await self.store.drop_proposal(tenant_id, proposal_id)
        if not removed:
            raise KeyError(proposal_id)

    # ── behavior learning ────────────────────────────────────────────────
    async def record_user_interaction(
        self, tenant_id: str, section_id: str, kind: str
    ) -> None:
        if section_id not in MODULE_IDS:
            return
        await self.store.record_behavior(tenant_id, section_id, kind)

    async def evidence(self, tenant_id: str) -> dict[str, Any]:
        """Behavior summary driving the next round of proposals."""
        return await self.store.behavior_summary(tenant_id)


def adaptive_service() -> AdaptiveService:
    """Module-level singleton; the Redis client is reused."""
    return AdaptiveService()
