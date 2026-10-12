"""Slidein universal core — scoped memory store.

Memory is partitioned by LearningScope. The enforcement points:

- put/get require an explicit tenant for tenant_private records, and the
  caller's tenant must match (CrossTenantAccess otherwise).
- search() never returns tenant_private records — there is no global
  search over tenant memory, by default or otherwise. Tenant-scoped
  search requires the caller's tenant to match.
- promote() moves a record along ALLOWED_TRANSITIONS only, and only with
  an approver whose role is authorized for that edge. Agents can never
  approve their own promotions.
- Every promotion appends an audit entry naming approver + reason.

See docs/architecture/TENANT_MEMORY_POLICY.md.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from product.core.errors import CrossTenantAccess, UnauthorizedPromotion
from product.core.scopes import (
    LearningScope,
    Role,
    may_read_scope,
    may_transition,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class MemoryRecord:
    """One memory item. Content is opaque to the store; the store enforces
    *where* it may live and *who* may read it, never what it means."""

    id: str
    scope: LearningScope
    tenant_id: str | None  # required when scope is tenant_private
    category: str  # e.g. "icp", "preference", "outcome", "defect", "metric"
    content: dict[str, object]
    created_by_role: Role
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True)
class PromotionRecord:
    record_id: str
    from_scope: LearningScope
    to_scope: LearningScope
    approver: str
    approver_role: Role
    reason: str
    at: datetime = field(default_factory=_utcnow)


class MemoryStore:
    """Scope-enforcing memory storage (in-memory; SQLAlchemy mapping for
    production is specified in CORE_VS_TENANT_BOUNDARIES.md)."""

    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}
        self._promotions: list[PromotionRecord] = []

    def put(
        self,
        *,
        scope: LearningScope,
        tenant_id: str | None,
        category: str,
        content: dict[str, object],
        role: Role,
        caller_tenant_id: str | None = None,
    ) -> MemoryRecord:
        if scope is LearningScope.TENANT_PRIVATE:
            if tenant_id is None:
                raise CrossTenantAccess("tenant_private memory requires a tenant_id")
            if role not in (Role.PLATFORM_ADMIN, Role.SYSTEM) and (
                caller_tenant_id is None or caller_tenant_id != tenant_id
            ):
                raise CrossTenantAccess(
                    f"caller for tenant {caller_tenant_id!r} cannot write "
                    f"tenant {tenant_id!r} memory"
                )
        record = MemoryRecord(
            id=str(uuid.uuid4()),
            scope=scope,
            tenant_id=tenant_id,
            category=category,
            content=copy.deepcopy(content),
            created_by_role=role,
        )
        self._records[record.id] = record
        return copy.deepcopy(record)

    def get(
        self, record_id: str, *, caller_tenant_id: str | None, role: Role
    ) -> MemoryRecord:
        try:
            record = self._records[record_id]
        except KeyError:
            raise CrossTenantAccess(f"unknown memory record {record_id!r}") from None
        if not may_read_scope(
            record.scope, role, record.tenant_id, caller_tenant_id
        ):
            raise CrossTenantAccess(
                f"role {role.value} may not read {record.scope.value} record "
                f"owned by tenant {record.tenant_id!r}"
            )
        return copy.deepcopy(record)

    def search(
        self,
        query: str,
        *,
        caller_tenant_id: str | None,
        role: Role,
        include_tenant_private: bool = False,
    ) -> tuple[MemoryRecord, ...]:
        """Substring search over categories and content.

        Tenant-private records are excluded unconditionally unless the
        caller explicitly requests their *own* tenant's records and the
        tenant matches. There is no flag combination that returns another
        tenant's private memory.
        """
        needle = query.lower()
        out: list[MemoryRecord] = []
        for record in self._records.values():
            if record.scope is LearningScope.TENANT_PRIVATE and not include_tenant_private:
                continue
            # may_read_scope is the single arbiter: tenant_private is
            # readable only by the owning tenant (or platform admin for
            # ops tooling). No flag combination exposes another tenant's
            # private memory to agents or tenant roles.
            if not may_read_scope(
                record.scope, role, record.tenant_id, caller_tenant_id
            ):
                continue
            haystack = f"{record.category} {record.content}".lower()
            if needle in haystack:
                out.append(copy.deepcopy(record))
        return tuple(out)

    def promote(
        self,
        record_id: str,
        to_scope: LearningScope,
        *,
        approver: str,
        approver_role: Role,
        reason: str,
    ) -> MemoryRecord:
        """Move a record to a broader scope. Requires an authorized
        approver for the exact edge; agents can never self-approve."""
        try:
            record = self._records[record_id]
        except KeyError:
            raise UnauthorizedPromotion(f"unknown memory record {record_id!r}") from None
        if not reason:
            raise UnauthorizedPromotion("promotion requires a recorded reason")
        if not may_transition(record.scope, to_scope, approver_role):
            raise UnauthorizedPromotion(
                f"{approver_role.value} may not promote {record.scope.value} "
                f"-> {to_scope.value}"
            )
        updated = MemoryRecord(
            id=record.id,
            scope=to_scope,
            tenant_id=record.tenant_id,
            category=record.category,
            content=copy.deepcopy(record.content),
            created_by_role=record.created_by_role,
            created_at=record.created_at,
        )
        self._records[record_id] = updated
        self._promotions.append(
            PromotionRecord(
                record_id=record_id,
                from_scope=record.scope,
                to_scope=to_scope,
                approver=approver,
                approver_role=approver_role,
                reason=reason,
            )
        )
        return copy.deepcopy(updated)

    def promotions(self) -> tuple[PromotionRecord, ...]:
        return tuple(self._promotions)
