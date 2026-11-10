"""Versioned price book and per-operation cost estimation.

Prices are rows in the database; this module only seeds initial versions and
resolves the active version at charge time. Provider costs in estimates are
clearly marked `"estimate"` — the codebase has no provider cost telemetry
yet, so nothing here pretends to be a measured charge.

The 350-prospect campaign package is seeded with status `restricted`: it is
visible in the catalog but cannot be purchased until its cost model is
validated (see `cost_model` on the entry and USAGE_PLATFORM_AUDIT.md).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import NotFoundError, ValidationError
from ..ids import new_id
from ..models import utcnow
from .models import CREDITS_PER_USD, PriceBookEntry

#: Product catalog. `capability` maps the price to the verified module that
#: fronts it; operations are refused when the tenant lacks the capability.
PRODUCTS: tuple[dict[str, Any], ...] = (
    {
        "product_id": "credits.pack",
        "description": "Prepaid Slidein credits. 1 credit = $0.01.",
        "billing_unit": "credit",
        "unit_price": 1,
        "required_capabilities": [],
        "usage_limits": {},
        "refund_policy": "Unused purchased credits are refundable within 30 days of purchase.",
    },
    {
        "product_id": "prospect.discovered",
        "description": "One accepted prospect record ingested with source attribution and duplicate handling.",
        "billing_unit": "prospect",
        "unit_price": 5,
        "required_capabilities": ["discovery"],
        "usage_limits": {"max_records_per_job": 5000},
        "refund_policy": "Duplicate or invalid rows are not billed.",
    },
    {
        "product_id": "prospect.research",
        "description": "One researched prospect: evidence collected with provenance.",
        "billing_unit": "prospect",
        "unit_price": 40,
        "required_capabilities": ["research"],
        "usage_limits": {"max_records_per_job": 1000},
        "refund_policy": "Failed research attempts are not billed.",
    },
    {
        "product_id": "prospect.qualified",
        "description": "One prospect scored against the active ICP with an explainable result.",
        "billing_unit": "prospect",
        "unit_price": 10,
        "required_capabilities": ["qualification"],
        "usage_limits": {"max_records_per_job": 1000},
        "refund_policy": "Failed qualification runs are not billed.",
    },
    {
        "product_id": "email.verified",
        "description": "One email address verified (syntax, MX, SMTP where reachable).",
        "billing_unit": "email",
        "unit_price": 3,
        "required_capabilities": ["outreach"],
        "usage_limits": {"max_records_per_job": 5000},
        "refund_policy": "Verification of an undeliverable address is billed; transport failures are refunded.",
    },
    {
        "product_id": "draft.generated",
        "description": "One completed, evidence-attributed personalized draft ready for approval.",
        "billing_unit": "draft",
        "unit_price": 30,
        "required_capabilities": ["personalization"],
        "usage_limits": {"max_records_per_job": 1000},
        "refund_policy": "Drafts rejected before send are not refunded; generation failures are not billed.",
    },
    {
        "product_id": "message.sent",
        "description": "One approved message dispatched (dry-run or live transport).",
        "billing_unit": "message",
        "unit_price": 5,
        "required_capabilities": ["outreach"],
        "usage_limits": {"max_records_per_job": 5000},
        "refund_policy": "Transport rejections before provider acceptance are not billed.",
    },
    {
        "product_id": "campaign.package.350",
        "description": (
            "350-prospect campaign package (proposed): prospect email addresses, "
            "research-backed qualification against the client ICP, prospect-specific "
            "research, personalized outreach drafts, a defined mailbox allocation "
            "and warm-up period, a defined sending allowance, CRM synchronization, "
            "and results reporting."
        ),
        "billing_unit": "package",
        "unit_price": 0,
        "package_price": 100_000,  # $1,000 proposed price — commercial hypothesis, not validated
        "included_allowances": {
            "prospects": 350,
            "mailboxes": 2,
            "mailbox_allocation_days": 90,
            "warmup_days": 21,
            "sending_allowance": 350,
            "campaign_duration_days": 60,
        },
        "required_capabilities": [
            "discovery", "research", "qualification", "personalization", "outreach",
        ],
        "usage_limits": {"max_prospects": 350},
        "eligibility": {"requires_admin_approval": True},
        "refund_policy": (
            "Billing is per accepted, qualified prospect with ICP-match evidence. "
            "Invalid or duplicate prospects are not billed. If fewer than the "
            "committed quantity can be delivered, undelivered units are refunded. "
            "Guaranteed replies or booked meetings are NOT included."
        ),
        "status": "restricted",
        "cost_model": {
            "validated": False,
            "currency": "USD",
            "scenarios": {
                "low": {
                    "llm": 45.0, "search_scrape_enrichment": 60.0, "verification": 17.5,
                    "mailboxes_warmup": 20.0, "sending_infra": 5.0, "vps_compute": 15.0,
                    "storage_monitoring": 5.0, "retries_failed": 10.0,
                    "payment_processing": 32.0, "support_overhead": 50.0, "total": 259.5,
                },
                "expected": {
                    "llm": 90.0, "search_scrape_enrichment": 120.0, "verification": 35.0,
                    "mailboxes_warmup": 40.0, "sending_infra": 10.0, "vps_compute": 30.0,
                    "storage_monitoring": 10.0, "retries_failed": 25.0,
                    "payment_processing": 32.0, "support_overhead": 100.0, "total": 492.0,
                },
                "high": {
                    "llm": 180.0, "search_scrape_enrichment": 240.0, "verification": 70.0,
                    "mailboxes_warmup": 80.0, "sending_infra": 20.0, "vps_compute": 60.0,
                    "storage_monitoring": 20.0, "retries_failed": 60.0,
                    "payment_processing": 32.0, "support_overhead": 175.0, "total": 937.0,
                },
            },
            "note": (
                "Assumption-based, not measured: no LLM token telemetry, no "
                "mailbox provider contract, no Firecrawl account pricing in the "
                "repository. Keep restricted until measured."
            ),
        },
    },
)

#: Per-unit internal provider cost estimates (cents), all basis="estimate".
#: Used for preflight previews and margin reporting only.
PROVIDER_COST_ESTIMATES: dict[str, dict[str, Any]] = {
    "prospect.discovered": {"provider": "builtin", "cost_cents_per_unit": 1},
    "prospect.research": {"provider": "openosint+llm", "cost_cents_per_unit": 18},
    "prospect.qualified": {"provider": "builtin", "cost_cents_per_unit": 1},
    "email.verified": {"provider": "reacher", "cost_cents_per_unit": 2},
    "draft.generated": {"provider": "llm", "cost_cents_per_unit": 12},
    "message.sent": {"provider": "kumomta", "cost_cents_per_unit": 1},
    "campaign.package.350": {"provider": "mixed", "cost_cents_per_unit": 0},  # see cost_model
}

DEFAULT_JOB_BUDGETS: dict[str, dict[str, int]] = {
    "prospect.discovered": {"max_records": 5000, "max_duration_seconds": 900, "max_retries": 3},
    "prospect.research": {"max_records": 1000, "max_duration_seconds": 3600, "max_retries": 3},
    "prospect.qualified": {"max_records": 1000, "max_duration_seconds": 1800, "max_retries": 3},
    "email.verified": {"max_records": 5000, "max_duration_seconds": 1800, "max_retries": 3},
    "draft.generated": {"max_records": 1000, "max_duration_seconds": 3600, "max_retries": 3},
    "message.sent": {"max_records": 5000, "max_duration_seconds": 3600, "max_retries": 3},
    "campaign.package.350": {"max_records": 350, "max_duration_seconds": 14_400, "max_retries": 3},
}


def price_dict(row: PriceBookEntry) -> dict[str, Any]:
    return {
        "product_id": row.product_id,
        "version": row.version,
        "description": row.description,
        "billing_unit": row.billing_unit,
        "unit_price_credits": row.unit_price,
        "package_price_credits": row.package_price,
        "included_allowances": dict(row.included_allowances or {}),
        "required_capabilities": list(row.required_capabilities or []),
        "usage_limits": dict(row.usage_limits or {}),
        "eligibility": dict(row.eligibility or {}),
        "refund_policy": row.refund_policy,
        "status": row.status,
        "effective_from": row.effective_from.isoformat() if row.effective_from else None,
        "cost_model_validated": bool((row.cost_model or {}).get("validated")),
    }


class PriceBookService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def seed(self) -> int:
        """Install version 1 of every product once; never overwrites edits."""
        seeded = 0
        for spec in PRODUCTS:
            exists = (
                await self.session.execute(
                    select(PriceBookEntry.id).where(
                        PriceBookEntry.product_id == spec["product_id"]
                    )
                )
            ).first()
            if exists:
                continue
            self.session.add(
                PriceBookEntry(
                    id=new_id("price"),
                    product_id=spec["product_id"],
                    version=1,
                    description=spec["description"],
                    billing_unit=spec["billing_unit"],
                    unit_price=spec["unit_price"],
                    package_price=spec.get("package_price"),
                    included_allowances=spec.get("included_allowances", {}),
                    required_capabilities=spec.get("required_capabilities", []),
                    usage_limits={
                        **DEFAULT_JOB_BUDGETS.get(spec["product_id"], {}),
                        **spec.get("usage_limits", {}),
                    },
                    eligibility=spec.get("eligibility", {}),
                    refund_policy=spec.get("refund_policy", ""),
                    status=spec.get("status", "active"),
                    cost_model=spec.get("cost_model", {}),
                    created_by="system:seed",
                )
            )
            seeded += 1
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
        return seeded

    async def active(self, product_id: str) -> PriceBookEntry:
        row = (
            await self.session.execute(
                select(PriceBookEntry)
                .where(PriceBookEntry.product_id == product_id)
                .order_by(PriceBookEntry.version.desc())
                .limit(1)
            )
        ).scalars().first()
        if row is None:
            raise NotFoundError(
                f"Unknown product {product_id!r}",
                code="unknown_product",
                recovery_action="list_capabilities",
            )
        return row

    async def catalog(self, *, include_restricted: bool = True) -> list[dict[str, Any]]:
        query = select(PriceBookEntry).order_by(PriceBookEntry.product_id, PriceBookEntry.version.desc())
        rows = (await self.session.execute(query)).scalars().all()
        seen: set[str] = set()
        out = []
        for row in rows:
            if row.product_id in seen:
                continue
            seen.add(row.product_id)
            if not include_restricted and row.status == "restricted":
                continue
            out.append(price_dict(row))
        return out

    async def estimate(
        self, product_id: str, *, units: int, price_version: int | None = None
    ) -> dict[str, Any]:
        """Customer-facing preflight estimate from the active price version.
        Variable-cost operations reserve a conservative cap; the final charge
        is metered at completion."""
        if units <= 0:
            raise ValidationError(
                "units must be positive", code="validation_error", recovery_action="fix_request"
            )
        if price_version is None:
            row = await self.active(product_id)
        else:
            row = (
                await self.session.execute(
                    select(PriceBookEntry).where(
                        PriceBookEntry.product_id == product_id,
                        PriceBookEntry.version == price_version,
                    )
                )
            ).scalars().first()
            if row is None:
                raise NotFoundError(
                    f"Unknown product/version {product_id!r} v{price_version}",
                    code="unknown_product",
                    recovery_action="list_capabilities",
                )
        limits = dict(row.usage_limits or {})
        max_records = int(limits.get("max_records") or limits.get("max_prospects") or 0)
        if max_records and units > max_records:
            raise ValidationError(
                f"{units} units exceeds the per-job limit of {max_records} for {product_id!r}",
                code="usage_limit_exceeded",
                details={"max_records": max_records},
                recovery_action="split_into_smaller_jobs",
            )
        if row.package_price is not None:
            # Packages reserve the full price regardless of units; partial
            # delivery refunds the undelivered share at the per-unit rate.
            per_unit = row.package_price // max(1, int(row.included_allowances.get("prospects") or 1))
            reservation = row.package_price
            charge_cap = row.package_price
        else:
            per_unit = row.unit_price
            reservation = row.unit_price * units
            charge_cap = reservation
        cost = PROVIDER_COST_ESTIMATES.get(product_id, {})
        estimated_provider_cost = int(cost.get("cost_cents_per_unit", 0)) * units
        return {
            "product_id": product_id,
            "price_version": row.version,
            "units": units,
            "billing_unit": row.billing_unit,
            "unit_price_credits": row.unit_price,
            "package_price_credits": row.package_price,
            "estimated_charge_credits": reservation,
            "maximum_charge_credits": charge_cap,
            "reservation_credits": reservation,
            "per_unit_package_credits": per_unit if row.package_price is not None else None,
            "estimated_provider_cost_cents": estimated_provider_cost,
            "provider_cost_basis": "estimate",
            "status": row.status,
            "budgets": {
                "max_duration_seconds": int(limits.get("max_duration_seconds") or 3600),
                "max_retries": int(limits.get("max_retries") or 3),
                "max_records": max_records or None,
            },
            "refund_policy": row.refund_policy,
        }


def credits_to_usd(credits: int) -> str:
    return f"${credits / CREDITS_PER_USD:.2f}"


__all__ = [
    "PRODUCTS",
    "PROVIDER_COST_ESTIMATES",
    "PriceBookService",
    "credits_to_usd",
    "price_dict",
]
