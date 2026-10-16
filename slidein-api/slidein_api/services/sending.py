"""Tenant-level sending configuration and circuit-breaker state.

This service is the single place that answers:

* which sending mode a tenant uses (`shared`, `dedicated` or
  `provider_managed`),
* which egress pool / provider account the tenant is assigned to,
* whether that route has been verified,
* whether the tenant's circuit breaker is open.

Every decision is derived server-side from trusted application data.
Client-supplied values are never consulted here.

Honest isolation language — nothing in this module claims that a tenant
is reputation-isolated unless a dedicated egress has actually been
verified:
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ConfigError, SlideinError
from ..ids import new_id
from ..models import (
    CircuitBreakerState,
    DeliveryEvent,
    TenantSendingConfig,
    utcnow,
)
from .deliverability_guard import (
    BREAKER_EVENT_TYPES,
    DeliverabilityGuard as _DeliverabilityGuard,
    QUARANTINE_WINDOW,
)

logger = logging.getLogger("slidein.sending")

SHARED_MODE = "shared"
DEDICATED_MODE = "dedicated"
PROVIDER_MANAGED_MODE = "provider_managed"

#: Plain-language isolation copy used by the admin view. These strings are
#: part of the product's honesty contract: the shared and
#: provider-managed modes explicitly describe what is *not* isolated.
SHARED_IP_COPY = (
    "Shared IP — reputation is shared with other tenants using this IP."
)
DEDICATED_VERIFIED_COPY = "Dedicated IP — routing verified."
DEDICATED_UNVERIFIED_COPY = (
    "Dedicated IP configured, but outbound route not yet verified."
)
PROVIDER_ROUTE_COPY = (
    "Provider route — IP isolation depends on provider account/IP "
    "configuration."
)


class SendingRouteError(SlideinError):
    """The tenant's sending configuration cannot be resolved.

    Routing fails closed: the message is not dispatched and the operator
    is pointed at the misconfiguration.
    """

    code = "sending_route_unresolved"


class CircuitBreakerError(SlideinError):
    """The circuit-breaker request is invalid for the current state."""

    code = "circuit_breaker_invalid"


def _parse_mode(value: str) -> str:
    return str(value or "").strip().lower()


class SendingService:
    """Resolves the effective sending route for one tenant.

    Also reports the tenant's circuit-breaker state: the evaluation
    methods and the operator controls live on the same service so the
    routing decision and the pause state can never disagree.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- configuration ---------------------------------------------------

    async def ensure_tenant_config(self, tenant_id: str) -> TenantSendingConfig:
        row = (
            await self.session.execute(
                select(TenantSendingConfig).where(TenantSendingConfig.tenant_id == tenant_id)
            )
        ).scalars().first()
        if row is not None:
            return row
        config = TenantSendingConfig(
            id=new_id("sending_config"),
            tenant_id=tenant_id,
            sending_mode=SHARED_MODE,
        )
        self.session.add(config)
        await self.session.flush()
        return config

    async def save_config(
        self,
        tenant_id: str,
        payload: dict,
        *,
        actor: str = "operator",
    ) -> dict:
        """Create or update the tenant's sending configuration.

        Only an operator may change it. Shared mode always clears any
        dedicated assignment: a shared tenant must never keep a private
        pool. A dedicated or provider-managed configuration must name
        its route, or the save fails closed.
        """
        config = await self.ensure_tenant_config(tenant_id)
        mode = str(payload.get("sending_mode") or SHARED_MODE).strip().lower()
        if mode not in (SHARED_MODE, DEDICATED_MODE, PROVIDER_MANAGED_MODE):
            raise ConfigError(
                f"Unknown sending mode {mode!r}",
                code="sending_route_unresolved",
                recovery_action="review_sending_mode",
            )
        config.sending_mode = mode

        if mode == SHARED_MODE:
            config.egress_pool = ""
            config.provider = ""
            config.provider_account = ""
            config.dedicated_ips = []
        elif mode == DEDICATED_MODE:
            egress_pool = str(payload.get("egress_pool") or "").strip()
            dedicated_ips = [
                str(ip).strip()
                for ip in (payload.get("dedicated_ips") or [])
                if str(ip).strip()
            ]
            if not egress_pool and not dedicated_ips:
                raise SendingRouteError(
                    "A dedicated tenant must be assigned an egress pool or "
                    "dedicated IPs."
                )
            config.egress_pool = egress_pool
            config.dedicated_ips = dedicated_ips
            config.provider = ""
            config.provider_account = ""
        else:
            provider = str(payload.get("provider") or "").strip()
            provider_account = str(payload.get("provider_account") or "").strip()
            if not provider or not provider_account:
                raise SendingRouteError(
                    "A provider-managed tenant must be assigned a provider "
                    "account."
                )
            config.provider = provider
            config.provider_account = provider_account
            config.egress_pool = ""
            config.dedicated_ips = []

        verified = bool(payload.get("verified", False))
        config.verified = verified
        config.verified_by = actor
        config.verified_at = utcnow() if verified else None
        config.verification_note = str(payload.get("verification_note") or "")

        await self.session.flush()
        return self._serialize(config)

    async def get_config(self, tenant_id: str) -> dict:
        """Effective sending configuration for the admin and operator views.

        Existing tenants have no row yet and stay on the shared route so
        current working delivery is never disrupted by a missing record.
        """
        config = await self.ensure_tenant_config(tenant_id)
        return self._serialize(config)

    @staticmethod
    def _serialize(config: TenantSendingConfig) -> dict:
        mode = _parse_mode(config.sending_mode)
        verified_by = config.verified_by or ""
        verified_at = config.verified_at.isoformat() if config.verified_at else ""
        return {
            "sending_mode": mode,
            "egress_pool": config.egress_pool,
            "provider": config.provider,
            "provider_account": config.provider_account,
            "dedicated_ips": list(config.dedicated_ips),
            "verified": bool(config.verified),
            "verified_by": verified_by,
            "verified_at": verified_at,
            "verification_note": config.verification_note,
            "isolation_copy": SendingService.isolation_copy(
                mode, verified=bool(config.verified)
            ),
        }

    @staticmethod
    def isolation_copy(mode: str, *, verified: bool = False) -> str:
        if mode == "dedicated":
            return DEDICATED_VERIFIED_COPY if verified else DEDICATED_UNVERIFIED_COPY
        if mode == "provider_managed":
            return PROVIDER_ROUTE_COPY
        return SHARED_IP_COPY

    async def resolve_route(self, tenant_id: str) -> dict:
        """Resolve the route this tenant's next message must use.

        The decision is deterministic and server-side. It fails closed
        (raises SendingRouteError) when the tenant is configured for a
        dedicated or provider-managed route but has no assignment.
        Shared-mode tenants always resolve to the shared route, even when
        no dedicated assignment exists — that is their explicit choice.
        """
        config = await self.ensure_tenant_config(tenant_id)
        mode = _parse_mode(config.sending_mode)

        if mode == "dedicated" and not (config.egress_pool or config.dedicated_ips):
            raise SendingRouteError(
                "Dedicated sending is configured for this tenant but no "
                "egress pool or dedicated IP is assigned. Ask an operator "
                "to assign the tenant's dedicated route."
            )
        if mode == "provider_managed" and not (
            config.provider and config.provider_account
        ):
            raise SendingRouteError(
                "Provider-managed sending is configured for this tenant "
                "but no provider account is assigned."
            )

        # `verified` is a reporting state, not a gate: a dedicated route
        # may be verified later. It must never be papered over by falling
        # back to the shared route.
        return self._serialize(config)

    # -- circuit breaker ------------------------------------------------

    async def get_circuit_state(self, tenant_id: str) -> dict:
        row = (
            await self.session.execute(
                select(CircuitBreakerState)
                .where(CircuitBreakerState.tenant_id == tenant_id)
                .order_by(CircuitBreakerState.updated_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if row is None:
            return {
                "status": "closed",
                "reason": "",
                "metrics": {},
                "opened_by": "",
                "opened_at": "",
                "resolved_by": "",
                "resolved_at": "",
                "resolve_note": "",
            }
        return {
            "status": row.status,
            "reason": row.reason,
            "metrics": row.metrics_json if isinstance(row.metrics_json, dict) else json.loads(row.metrics_json or "{}"),
            "opened_by": row.opened_by,
            "opened_at": row.opened_at.isoformat() if row.opened_at else "",
            "resolved_by": row.resolved_by,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else "",
            "resolve_note": row.resolve_note,
        }

    async def evaluate(self, tenant_id: str) -> tuple[bool, str]:
        """Evaluate the rolling reputation window for this tenant only.

        Returns (tripped, reason). Only this tenant's delivery events are
        considered, so a tenant with a poor reputation never pauses its
        neighbours.
        """
        guard = _DeliverabilityGuard(tenant_id)
        rows = (
            await self.session.execute(
                select(DeliveryEvent)
                .where(
                    DeliveryEvent.tenant_id == tenant_id,
                    DeliveryEvent.event_type.in_(BREAKER_EVENT_TYPES),
                )
                .order_by(DeliveryEvent.occurred_at.desc(), DeliveryEvent.id.desc())
                .limit(QUARANTINE_WINDOW)
            )
        ).scalars().all()
        events = [row.event_type for row in rows]
        tripped, reason = _DeliverabilityGuard.evaluate_circuit_breaker(events)
        return tripped, reason

    async def open(
        self,
        tenant_id: str,
        *,
        reason: str,
        opened_by: str,
        metrics: dict | None = None,
    ) -> dict:
        state = CircuitBreakerState(
            id=new_id("circuit_breaker"),
            tenant_id=tenant_id,
            status="open",
            reason=reason,
            metrics_json=metrics or {},
            opened_by=opened_by,
            opened_at=utcnow(),
        )
        self.session.add(state)
        await self.session.flush()
        return {
            "status": "open",
            "reason": reason,
            "opened_by": opened_by,
            "opened_at": state.opened_at.isoformat() if state.opened_at else "",
        }

    async def start_recovery_probe(self, tenant_id: str, *, started_by: str) -> dict:
        """Half-open: an operator accepts a limited probe batch."""
        state = CircuitBreakerState(
            id=new_id("circuit_breaker"),
            tenant_id=tenant_id,
            status="half-open",
            reason="operator started recovery probe",
            opened_by=started_by,
            opened_at=utcnow(),
        )
        self.session.add(state)
        await self.session.flush()
        return {
            "status": "half-open",
            "reason": state.reason,
            "started_by": started_by,
        }

    async def resolve(
        self,
        tenant_id: str,
        *,
        resolved_by: str,
        note: str = "",
    ) -> dict:
        """Operator review: the tenant may send again."""
        state = CircuitBreakerState(
            id=new_id("circuit_breaker"),
            tenant_id=tenant_id,
            status="closed",
            reason="",
            resolved_by=resolved_by,
            resolved_at=utcnow(),
            resolve_note=note,
        )
        self.session.add(state)
        await self.session.flush()
        return {
            "status": "closed",
            "resolved_by": resolved_by,
            "resolved_at": state.resolved_at.isoformat() if state.resolved_at else "",
        }


class CircuitBreakerService(SendingService):
    """Circuit-breaker state for one tenant.

    Inherit the sending-route resolution; the evaluation methods and the
    operator controls add the pause/probe/resume workflow on top.
    """
