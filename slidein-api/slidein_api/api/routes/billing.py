"""Customer billing routes: balance, ledger, purchases, payments, resources.

Every route is tenant-bound through `resolve_workspace`; a caller can only
ever see or move its own workspace's credits.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Request

from ...db import session_scope
from ...security import AuthContext, require_role, resolve_workspace
from ...services.jobs import execution_mode
from ...billing.ledger import LedgerService
from ...billing.models import ManagedResource
from ...billing.payments import PaymentService
from ...billing.pricebook import PriceBookService

router = APIRouter()


@router.get("/tenants/{tenant_id}/billing/balance", tags=["billing"])
async def billing_balance(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "viewer")
    async with session_scope() as session:
        balance = await LedgerService(session).balance(auth.tenant_id)
        price = PriceBookService(session)
        balance["catalog"] = await price.catalog(include_restricted=False)
    return balance


@router.get("/tenants/{tenant_id}/billing/ledger", tags=["billing"])
async def billing_ledger(
    tenant_id: str,
    limit: int = 100,
    offset: int = 0,
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "viewer")
    async with session_scope() as session:
        entries = await LedgerService(session).ledger(
            auth.tenant_id, limit=min(500, max(1, limit)), offset=max(0, offset)
        )
    return {"entries": entries, "limit": limit, "offset": offset}


@router.get("/tenants/{tenant_id}/billing/reconcile", tags=["billing"])
async def billing_reconcile(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "admin")
    async with session_scope() as session:
        return await LedgerService(session).reconcile(auth.tenant_id)


@router.post("/tenants/{tenant_id}/billing/purchases", tags=["billing"])
async def create_purchase(
    tenant_id: str,
    background: BackgroundTasks,
    body: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Create a credit purchase intent (manual provider: pending until an
    admin confirms; Stripe provider: completes via webhook)."""
    require_role(auth, "operator")
    amount_cents = int(body.get("amount_cents") or 0)
    idempotency_key = str(body.get("idempotency_key") or "").strip()
    if not idempotency_key:
        from ...errors import ValidationError

        raise ValidationError(
            "idempotency_key is required for purchases",
            code="idempotency_required",
            recovery_action="supply_idempotency_key",
        )
    async with session_scope() as session:
        payment = await PaymentService(session).create_purchase(
            tenant_id=auth.tenant_id,
            amount_cents=amount_cents,
            idempotency_key=idempotency_key,
            created_by=f"user:{auth.role}",
        )
    return {"payment": payment}


@router.post("/tenants/{tenant_id}/billing/purchases/{payment_id}/confirm", tags=["billing"])
async def confirm_purchase(
    tenant_id: str,
    payment_id: str,
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Admin confirmation for the manual payment provider."""
    require_role(auth, "admin")
    async with session_scope() as session:
        payment = await PaymentService(session).confirm_purchase(
            tenant_id=auth.tenant_id,
            payment_id=payment_id,
            admin_actor=auth.email or auth.key_fingerprint or f"key:{auth.role}",
        )
        balance = await LedgerService(session).balance(auth.tenant_id)
    return {"payment": payment, "balance": balance}


@router.get("/tenants/{tenant_id}/billing/purchases", tags=["billing"])
async def list_purchases(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "viewer")
    async with session_scope() as session:
        return {"payments": await PaymentService(session).list_payments(auth.tenant_id)}


@router.get("/tenants/{tenant_id}/billing/resources", tags=["billing"])
async def list_resources(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "viewer")
    async with session_scope() as session:
        from sqlalchemy import select

        rows = (
            await session.execute(
                select(ManagedResource)
                .where(ManagedResource.tenant_id == auth.tenant_id)
                .order_by(ManagedResource.provisioned_at.desc())
            )
        ).scalars().all()
    return {
        "resources": [
            {
                "id": row.id,
                "resource_type": row.resource_type,
                "provider": row.provider,
                "state": row.state,
                "allocation_period_days": row.allocation_period_days,
                "included_allowance": dict(row.included_allowance or {}),
                "product_id": row.product_id,
                "campaign_id": row.campaign_id,
                "provisioned_at": row.provisioned_at.isoformat() if row.provisioned_at else None,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            }
            for row in rows
        ]
    }


# ---------------------------------------------------------------------------
# Stripe webhook (unauthenticated by design; signature-verified inside)
# ---------------------------------------------------------------------------


@router.post("/billing/webhooks/stripe", tags=["billing"])
async def stripe_webhook(request: Request) -> dict:
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    tenant_hint = request.headers.get("x-slidein-tenant", "")
    async with session_scope() as session:
        service = PaymentService(session)
        event = service.verify_stripe_signature(
            payload=payload, signature_header=signature
        )
        outcome = await service.process_stripe_event(
            tenant_hint=tenant_hint or None, event=event
        )
    return outcome


__all__ = ["router"]
