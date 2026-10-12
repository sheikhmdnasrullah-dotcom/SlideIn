"""Slidein universal core — tenant-owned business context.

A TenantContext is the complete, isolated configuration surface for one
tenant's business: identity, offers, ICP, exclusions, approved claims,
terminology, messaging preferences, and operating policies. It travels
*through* the shared workflow as data; it can never rewrite shared code,
shared prompts, or another tenant's settings.

Storage here is in-memory and dependency-free so the boundary rules are
unit-testable everywhere. The production SQLAlchemy mapping (reusing the
existing TenantMixin pattern) is specified in
docs/architecture/CORE_VS_TENANT_BOUNDARIES.md.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from product.core.errors import CrossTenantAccess
from product.core.scopes import Role


@dataclass(frozen=True)
class BusinessIdentity:
    """Public facts about the tenant's business. No PII beyond what the
    tenant publishes about itself."""

    name: str
    domain: str
    industry: str = ""
    description: str = ""


@dataclass(frozen=True)
class Offer:
    """One thing the tenant sells. Claims listed here are the only ones
    personalization may assert on this tenant's behalf."""

    name: str
    summary: str
    approved_claims: tuple[str, ...] = ()
    proof_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class IdealCustomerProfile:
    """Typed targeting criteria. Never a global default."""

    name: str
    titles: tuple[str, ...] = ()
    industries: tuple[str, ...] = ()
    company_size: tuple[str, ...] = ()
    geographies: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()


@dataclass(frozen=True)
class MessagingPreferences:
    """How this tenant wants to sound. A tone preference here must never
    leak into universal writing defaults."""

    tone: str = "professional"
    max_sentences: int = 4
    greeting: str = ""
    signoff: str = ""
    banned_phrases: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperatingPolicy:
    """Tenant-approved operating limits (subset of the full policy model)."""

    max_emails_per_day: int = 50
    require_human_approval: bool = True
    allowed_channels: tuple[str, ...] = ("email",)


@dataclass(frozen=True)
class TenantContext:
    """Immutable snapshot of one tenant's business context.

    Frozen so workflow stages cannot mutate it mid-run; tenants change their
    context only through TenantConfigStore.update_* with their own role.
    """

    tenant_id: str
    identity: BusinessIdentity
    offers: tuple[Offer, ...] = ()
    icps: tuple[IdealCustomerProfile, ...] = ()
    exclusions: tuple[str, ...] = ()
    terminology: dict[str, str] = field(default_factory=dict)
    messaging: MessagingPreferences = field(default_factory=MessagingPreferences)
    policy: OperatingPolicy = field(default_factory=OperatingPolicy)

    def offer_names(self) -> tuple[str, ...]:
        return tuple(o.name for o in self.offers)


class TenantConfigStore:
    """Per-tenant configuration storage with hard isolation.

    - Every read/write names a tenant_id; callers acting for tenant A can
      never observe or mutate tenant B (CrossTenantAccess otherwise).
    - The store holds *copies*: mutating a returned context is impossible
      (frozen dataclass) and internal state cannot be aliased.
    - There is deliberately no method here that touches shared defaults —
      tenant configuration and shared configuration are different objects
      with different writers (see product.core.shared).
    """

    def __init__(self) -> None:
        self._contexts: dict[str, TenantContext] = {}

    def register(self, context: TenantContext, *, role: Role) -> TenantContext:
        if role not in (Role.TENANT_ADMIN, Role.PLATFORM_ADMIN, Role.SYSTEM):
            raise CrossTenantAccess(
                f"role {role.value} may not register tenant contexts"
            )
        self._contexts[context.tenant_id] = copy.deepcopy(context)
        return self.get(context.tenant_id, caller_tenant_id=context.tenant_id, role=role)

    def get(
        self, tenant_id: str, *, caller_tenant_id: str | None, role: Role
    ) -> TenantContext:
        self._check(tenant_id, caller_tenant_id, role)
        try:
            return copy.deepcopy(self._contexts[tenant_id])
        except KeyError:
            raise CrossTenantAccess(f"unknown tenant {tenant_id!r}") from None

    def update_messaging(
        self,
        tenant_id: str,
        messaging: MessagingPreferences,
        *,
        caller_tenant_id: str | None,
        role: Role,
    ) -> TenantContext:
        """Tenant-scoped preference change. Returns the new snapshot; shared
        writing defaults are untouched by construction (separate object)."""
        self._check(tenant_id, caller_tenant_id, role)
        if role not in (Role.TENANT_ADMIN, Role.TENANT_MEMBER, Role.PLATFORM_ADMIN):
            raise CrossTenantAccess(
                f"role {role.value} may not update tenant configuration"
            )
        current = self._contexts[tenant_id]
        updated = TenantContext(
            tenant_id=current.tenant_id,
            identity=current.identity,
            offers=current.offers,
            icps=current.icps,
            exclusions=current.exclusions,
            terminology=copy.deepcopy(current.terminology),
            messaging=messaging,
            policy=current.policy,
        )
        self._contexts[tenant_id] = updated
        return copy.deepcopy(updated)

    def tenant_ids(self, *, role: Role) -> tuple[str, ...]:
        if role not in (Role.PLATFORM_ADMIN, Role.SYSTEM):
            raise CrossTenantAccess("tenant enumeration requires platform admin")
        return tuple(sorted(self._contexts))

    @staticmethod
    def _check(
        tenant_id: str, caller_tenant_id: str | None, role: Role
    ) -> None:
        if role in (Role.PLATFORM_ADMIN, Role.SYSTEM):
            return
        if caller_tenant_id is None or caller_tenant_id != tenant_id:
            raise CrossTenantAccess(
                f"caller for tenant {caller_tenant_id!r} cannot access tenant {tenant_id!r}"
            )
