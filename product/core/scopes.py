"""Slidein universal core — learning scopes, roles, and access policy.

Every persistent learning item carries exactly one scope. Scope is the
primary isolation mechanism: it decides who may read an item and which
promotions are even expressible. See
docs/architecture/TENANT_MEMORY_POLICY.md.
"""

from __future__ import annotations

from enum import Enum


class LearningScope(str, Enum):
    """The five learning scopes. Ordered by breadth of visibility."""

    TENANT_PRIVATE = "tenant_private"
    PLATFORM_OPERATIONAL = "platform_operational"
    PLATFORM_CANDIDATE = "platform_candidate"
    PLATFORM_VALIDATED = "platform_validated"
    PLATFORM_RELEASED = "platform_released"


# Allowed scope transitions. Absence of an edge means the promotion is
# forbidden no matter who approves it — in particular, tenant_private can
# only ever leave its tenant via an explicit hop to platform_candidate,
# never directly to validated/released.
ALLOWED_TRANSITIONS: dict[LearningScope, frozenset[LearningScope]] = {
    LearningScope.TENANT_PRIVATE: frozenset({LearningScope.PLATFORM_CANDIDATE}),
    LearningScope.PLATFORM_OPERATIONAL: frozenset({LearningScope.PLATFORM_CANDIDATE}),
    LearningScope.PLATFORM_CANDIDATE: frozenset({LearningScope.PLATFORM_VALIDATED}),
    LearningScope.PLATFORM_VALIDATED: frozenset({LearningScope.PLATFORM_RELEASED}),
    LearningScope.PLATFORM_RELEASED: frozenset(),
}


class Role(str, Enum):
    """Caller roles recognized by the core. Agents execute workflows; they
    never approve promotions or releases."""

    AGENT = "agent"
    TENANT_MEMBER = "tenant_member"
    TENANT_ADMIN = "tenant_admin"
    PLATFORM_ADMIN = "platform_admin"
    SYSTEM = "system"  # migrations, seed scripts, CI fixtures


# Roles allowed to *approve* a promotion along each permitted edge.
# Note: Role.AGENT appears nowhere — agents may submit candidates but the
# scope change itself always requires a human (or human-delegated) approver.
PROMOTION_APPROVERS: dict[
    tuple[LearningScope, LearningScope], frozenset[Role]
] = {
    (LearningScope.TENANT_PRIVATE, LearningScope.PLATFORM_CANDIDATE): frozenset(
        {Role.TENANT_ADMIN, Role.PLATFORM_ADMIN}
    ),
    (LearningScope.PLATFORM_OPERATIONAL, LearningScope.PLATFORM_CANDIDATE): frozenset(
        {Role.PLATFORM_ADMIN}
    ),
    (LearningScope.PLATFORM_CANDIDATE, LearningScope.PLATFORM_VALIDATED): frozenset(
        {Role.PLATFORM_ADMIN}
    ),
    (LearningScope.PLATFORM_VALIDATED, LearningScope.PLATFORM_RELEASED): frozenset(
        {Role.PLATFORM_ADMIN}
    ),
}


def may_transition(
    from_scope: LearningScope, to_scope: LearningScope, approver: Role
) -> bool:
    """True only when the edge exists AND the approver role may approve it."""
    if to_scope not in ALLOWED_TRANSITIONS.get(from_scope, frozenset()):
        return False
    return approver in PROMOTION_APPROVERS.get((from_scope, to_scope), frozenset())


def may_read_scope(
    scope: LearningScope,
    role: Role,
    owner_tenant_id: str | None,
    caller_tenant_id: str | None,
) -> bool:
    """Scope read policy.

    - tenant_private: only callers acting for the owning tenant, plus
      platform admins (for support/ops tooling, never as agent context).
    - platform_*: readable by any authenticated role; agents included, since
      shared knowledge is exactly what agents are allowed to reuse.
    """
    if scope is LearningScope.TENANT_PRIVATE:
        if role is Role.PLATFORM_ADMIN:
            return True
        return (
            owner_tenant_id is not None
            and caller_tenant_id is not None
            and owner_tenant_id == caller_tenant_id
        )
    return True
