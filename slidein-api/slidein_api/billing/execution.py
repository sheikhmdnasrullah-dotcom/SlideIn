"""Cost-aware operation execution.

Submit path: validate → capability check → estimate → spending-limit check
→ reserve credits → durable WorkJob (idempotent). Execution path: run the
real stage services unit by unit inside enforced budgets, meter every unit,
then capture the metered charge and release the remainder. Partial results
are reported honestly: processed vs accepted vs failed, with the shortfall
explained in the job result.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..db import session_scope
from ..errors import ConfigError, PermissionDenied, SlideinError, ValidationError
from ..ids import new_id
from ..services.discovery import DiscoveryService
from ..services.jobs import JobService
from ..services.modules import check_any_module_enabled
from ..services.personalization import PersonalizationService
from ..services.qualification import QualificationService
from ..services.research import ResearchService
from ..services.templates import TemplateService
from .ledger import LedgerService
from .models import JobUsage, ReservationState
from .pricebook import PROVIDER_COST_ESTIMATES, PriceBookService

logger = logging.getLogger("slidein.billing.execution")

JOB_KIND = "operation"

#: Products whose execution is implemented. Everything else in the catalog
#: is visible but refused with `capability_unavailable` — never faked.
SUPPORTED_PRODUCTS = frozenset({
    "prospect.discovered",
    "prospect.research",
    "prospect.qualified",
    "email.verified",
    "draft.generated",
    "message.sent",
    "campaign.package.350",
})

#: campaign.package.350 pipeline: stage product → metered product mapping.
CAMPAIGN_STAGES: tuple[tuple[str, str], ...] = (
    ("ingest", "prospect.discovered"),
    ("research", "prospect.research"),
    ("qualify", "prospect.qualified"),
    ("draft", "draft.generated"),
)


def job_result_dict(result: dict[str, Any]) -> dict[str, Any]:
    return result


class OperationService:
    """HTTP-facing submit/preflight for billable operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _check_capabilities(self, tenant_id: str, required: list[str]) -> None:
        if not required:
            return
        effective = await TemplateService(self.session).effective(tenant_id)
        stored = {"enabled": effective["modules"]["enabled"]}
        check_any_module_enabled(stored, required)

    async def _spend_limit(self, tenant_id: str) -> int | None:
        from ..models import Tenant

        row = await self.session.get(Tenant, tenant_id)
        if row is None:
            return None
        billing = (row.settings or {}).get("billing") or {}
        limit = billing.get("max_spend_credits")
        return int(limit) if limit else None

    async def estimate_operation(
        self, tenant_id: str, product_id: str, *, units: int
    ) -> dict[str, Any]:
        price = PriceBookService(self.session)
        entry = await price.active(product_id)
        estimate = await price.estimate(product_id, units=units)
        available = (await LedgerService(self.session).balance(tenant_id))["available_credits"]
        spend_limit = await self._spend_limit(tenant_id)
        estimate["available_credits"] = available
        estimate["spend_limit_credits"] = spend_limit
        estimate["affordable"] = available >= estimate["reservation_credits"] and (
            spend_limit is None or estimate["reservation_credits"] <= spend_limit
        )
        return estimate

    async def submit(
        self,
        *,
        tenant_id: str,
        product_id: str,
        units: int,
        params: dict[str, Any] | None = None,
        idempotency_key: str,
        allow_restricted: bool = False,
        actor: str = "",
    ) -> dict[str, Any]:
        """Reserve credits and enqueue a durable operation job. Idempotent:
        the same key returns the original job without a second reservation
        or charge."""
        if not idempotency_key.strip():
            raise ValidationError(
                "Idempotency-Key is required for billable operations",
                code="idempotency_required",
                recovery_action="supply_idempotency_key",
            )
        if product_id not in SUPPORTED_PRODUCTS:
            raise ValidationError(
                f"Operation {product_id!r} is catalogued but not executable yet",
                code="capability_unavailable",
                details={"product_id": product_id},
                recovery_action="list_capabilities",
            )
        price = PriceBookService(self.session)
        entry = await price.active(product_id)
        if entry.status == "restricted" and not allow_restricted:
            raise PermissionDenied(
                f"Product {product_id!r} is not publicly available yet",
                code="product_restricted",
                details={"product_id": product_id},
                recovery_action="contact_sales",
            )
        await self._check_capabilities(tenant_id, list(entry.required_capabilities or []))
        estimate = await price.estimate(product_id, units=units)
        spend_limit = await self._spend_limit(tenant_id)
        if spend_limit is not None and estimate["reservation_credits"] > spend_limit:
            raise PermissionDenied(
                "Operation exceeds the configured spending limit",
                code="spend_limit_exceeded",
                details={"spend_limit_credits": spend_limit},
                recovery_action="raise_spend_limit",
            )
        ledger = LedgerService(self.session)
        balance = await ledger.balance(tenant_id)
        if balance["available_credits"] < estimate["reservation_credits"]:
            from .ledger import InsufficientCreditsError

            raise InsufficientCreditsError(
                balance["available_credits"], estimate["reservation_credits"]
            )
        job = await JobService(self.session).enqueue(
            tenant_id=tenant_id,
            kind=JOB_KIND,
            idempotency_key=idempotency_key,
            payload={
                "product_id": product_id,
                "units": units,
                "params": params or {},
                "price_version": estimate["price_version"],
                "reservation_credits": estimate["reservation_credits"],
                "actor": actor,
            },
        )
        existing = await ledger.reservation_for_job(job["id"])
        if existing is None:
            await ledger.reserve(
                tenant_id=tenant_id,
                job_id=job["id"],
                product_id=product_id,
                price_version=estimate["price_version"],
                amount=estimate["reservation_credits"],
            )
        return {"job": job, "estimate": estimate}


# ---------------------------------------------------------------------------
# Execution (runs inside workers/runner.py under a claimed WorkJob)
# ---------------------------------------------------------------------------


class _Budget:
    def __init__(self, limits: dict[str, Any]) -> None:
        self.max_records = int(limits.get("max_records") or 0) or None
        self.max_seconds = float(limits.get("max_duration_seconds") or 0) or None
        self.started = time.monotonic()

    @property
    def exhausted_time(self) -> bool:
        return self.max_seconds is not None and (
            time.monotonic() - self.started >= self.max_seconds
        )

    def allow_more(self, processed: int) -> bool:
        if self.max_records is not None and processed >= self.max_records:
            return False
        return not self.exhausted_time


async def _unit_discover(session, tenant_id: str, record: dict, params: dict) -> dict[str, Any]:
    from ..services.config import ConfigService

    icp = await ConfigService(session).active_icp(tenant_id)
    if icp is None:
        raise ConfigError("No active ICP", code="icp_missing", recovery_action="define_icp")
    result = await DiscoveryService(session).create_records(
        tenant_id=tenant_id,
        icp_id=icp["id"],
        records=[record],
        source="api_operation",
        created_by="service:billing",
    )
    accepted = result.get("created", 0) > 0
    return {"accepted": accepted, "detail": result}


async def _unit_research(
    session, tenant_id: str, prospect_id: str, params: dict
) -> dict[str, Any]:
    discovery = DiscoveryService(session)
    prospect = await discovery.get_prospect(tenant_id, prospect_id)
    if prospect is None:
        raise ValidationError(
            f"Prospect {prospect_id!r} not found", code="prospect_not_found",
            recovery_action="return_to_discovery",
        )
    result = await ResearchService(session).collect_evidence(
        tenant_id=tenant_id,
        prospect=prospect,
        supplied_claims=params.get("claims") or [],
        connector=str(params.get("connector") or "orchestrated"),
        actor="service:billing",
    )
    return {"accepted": result.get("evidence_count", 0) > 0, "detail": result}


async def _unit_qualify(
    session, tenant_id: str, prospect_id: str, params: dict
) -> dict[str, Any]:
    from ..services.config import ConfigService

    discovery = DiscoveryService(session)
    prospect = await discovery.get_prospect(tenant_id, prospect_id)
    if prospect is None:
        raise ValidationError(
            f"Prospect {prospect_id!r} not found", code="prospect_not_found",
            recovery_action="return_to_discovery",
        )
    icp = await ConfigService(session).active_icp(tenant_id)
    if icp is None:
        raise ConfigError(
            "No active ICP", code="icp_missing", recovery_action="define_icp"
        )
    evidence_rows = await ResearchService(session).list_evidence(tenant_id, prospect_id)
    result = await QualificationService(session).record(
        tenant_id=tenant_id,
        prospect=prospect,
        icp=icp,
        evidence_rows=evidence_rows,
        actor="service:billing",
    )
    return {"accepted": True, "detail": result}


async def _unit_verify(
    session, tenant_id: str, email: str, params: dict
) -> dict[str, Any]:
    from ..services.preflight import reacher_verification

    verdict = await reacher_verification(email)
    if verdict.get("status") in ("not_configured", "unavailable"):
        raise SlideinError(
            "Email verification provider is not available",
            code="provider_unavailable",
            recovery_action="retry_stage",
            retryable=True,
        )
    return {"accepted": bool(verdict.get("verified")), "detail": verdict}


async def _unit_draft(
    session, tenant_id: str, prospect_id: str, params: dict
) -> dict[str, Any]:
    discovery = DiscoveryService(session)
    prospect = await discovery.get_prospect(tenant_id, prospect_id)
    if prospect is None:
        raise ValidationError(
            f"Prospect {prospect_id!r} not found", code="prospect_not_found",
            recovery_action="return_to_discovery",
        )
    result = await PersonalizationService(session).generate_draft(
        tenant_id=tenant_id, prospect=prospect, actor="service:billing"
    )
    return {"accepted": result.get("status") == "pending_review", "detail": result}


async def _unit_send(
    session, tenant_id: str, draft_id: str, params: dict
) -> dict[str, Any]:
    from ..services.outreach import OutreachService

    result = await OutreachService(session).send_draft(
        tenant_id=tenant_id, draft_id=draft_id, actor="service:billing"
    )
    accepted = result.get("status") not in ("failed", "transport_rejected")
    return {"accepted": bool(accepted), "detail": result}


UNIT_EXECUTORS = {
    "prospect.discovered": ("records", _unit_discover),
    "prospect.research": ("prospect_ids", _unit_research),
    "prospect.qualified": ("prospect_ids", _unit_qualify),
    "email.verified": ("emails", _unit_verify),
    "draft.generated": ("prospect_ids", _unit_draft),
    "message.sent": ("draft_ids", _unit_send),
}


def _meter(
    session: AsyncSession,
    *,
    tenant_id: str,
    job_id: str,
    product_id: str,
    units: int,
) -> None:
    cost = PROVIDER_COST_ESTIMATES.get(product_id, {})
    session.add(
        JobUsage(
            id=new_id("usage"),
            tenant_id=tenant_id,
            job_id=job_id,
            product_id=product_id,
            provider=str(cost.get("provider", "")),
            units=units,
            unit_type="unit",
            provider_cost_cents=int(cost.get("cost_cents_per_unit", 0)) * units,
            cost_basis="estimate",
        )
    )


async def execute_operation_job(job: dict[str, Any]) -> dict[str, Any]:
    """Metered execution of one operation job. Always finalizes billing:
    capture the accepted-unit charge, release everything else."""
    tenant_id = job["tenant_id"]
    job_id = job["id"]
    payload = job.get("payload") or {}
    product_id = str(payload.get("product_id") or "")
    params = payload.get("params") or {}

    async with session_scope() as session:
        ledger = LedgerService(session)
        reservation = await ledger.reservation_for_job(job_id)
        price = PriceBookService(session)
        entry = await price.active(product_id)

    result: dict[str, Any] = {
        "product_id": product_id,
        "requested_units": int(payload.get("units") or 0),
        "processed": 0,
        "accepted_units": 0,
        "failed_units": 0,
        "outputs": [],
        "failures": [],
        "charge_credits": 0,
        "released_credits": 0,
        "refund_policy": entry.refund_policy,
    }

    try:
        if product_id == "campaign.package.350":
            await _run_campaign(job, entry, result)
        else:
            await _run_units(job, entry, result)
        result["status"] = "complete" if result["accepted_units"] > 0 else "failed"
        if result["failed_units"]:
            result["status"] = "partial" if result["accepted_units"] else "failed"
    except Exception as exc:  # noqa: BLE001 — billing must still finalize
        logger.exception("Operation job %s crashed", job_id)
        result["status"] = "failed"
        result["crash"] = f"{type(exc).__name__}: {exc}"
        result.setdefault("failures", []).append({
            "unit": None, "error_code": "worker_exception",
            "retryable": True,
        })

    # -- finalize billing (never raises into the runner) -----------------------
    async with session_scope() as session:
        ledger = LedgerService(session)
        reservation = await ledger.reservation_for_job(job_id)
        if reservation is None or reservation.state != ReservationState.HELD.value:
            result["billing_finalized"] = False
            return result
        if entry.package_price is not None:
            allowance = max(1, int((entry.included_allowances or {}).get("prospects") or 1))
            per_unit = entry.package_price // allowance
            charge = min(result["accepted_units"], allowance) * per_unit
        else:
            charge = result["accepted_units"] * entry.unit_price
        result["charge_credits"] = charge
        result["released_credits"] = reservation.amount - charge
        await ledger.capture(
            reservation_id=reservation.id,
            actual_amount=charge,
            reason=f"{product_id} job {job_id}: {result['accepted_units']} accepted unit(s)",
        )
        result["billing_finalized"] = True
    return result


async def _run_units(job: dict, entry, result: dict) -> None:
    tenant_id = job["tenant_id"]
    job_id = job["id"]
    payload = job.get("payload") or {}
    product_id = str(payload.get("product_id") or "")
    params = payload.get("params") or {}
    param_key, unit_fn = UNIT_EXECUTORS[product_id]
    units: list[Any] = list(params.get(param_key) or [])
    budget = _Budget(entry.usage_limits or {})

    async with session_scope() as session:
        for unit in units:
            if not budget.allow_more(result["processed"]):
                result["failures"].append({
                    "unit": None, "error_code": "budget_exceeded",
                    "message": "Job stopped at its enforced budget",
                    "retryable": False,
                })
                break
            try:
                outcome = await unit_fn(session, tenant_id, unit, params)
            except SlideinError as exc:
                result["failed_units"] += 1
                result["failures"].append({
                    "unit": unit, "error_code": exc.code,
                    "message": exc.message, "retryable": exc.retryable,
                })
                continue
            except Exception as exc:  # noqa: BLE001 — one bad unit never kills the batch
                result["failed_units"] += 1
                result["failures"].append({
                    "unit": unit, "error_code": "unknown",
                    "message": f"{type(exc).__name__}: {exc}", "retryable": True,
                })
                continue
            result["processed"] += 1
            if outcome.get("accepted"):
                result["accepted_units"] += 1
                _meter(session, tenant_id=tenant_id, job_id=job_id,
                       product_id=product_id, units=1)
            else:
                result["failed_units"] += 1
                detail = outcome.get("detail") or {}
                reason = (
                    detail.get("skipped_records")
                    or detail.get("duplicate_emails")
                    or "unit rejected by acceptance criteria"
                )
                result["failures"].append({
                    "unit": unit if isinstance(unit, str) else None,
                    "error_code": "unit_rejected",
                    "message": str(reason),
                    "retryable": False,
                })
            detail = outcome.get("detail") or {}
            reference_id = (
                detail.get("id")
                or detail.get("draft_id")
                or (detail.get("prospect_ids") or [""])[0]
                or ""
            )
            result["outputs"].append({
                "unit": unit if isinstance(unit, str) else str(unit.get("email") or ""),
                "accepted": bool(outcome.get("accepted")),
                "reference_id": reference_id,
            })


async def _run_campaign(job: dict, entry, result: dict) -> None:
    """350-package pipeline: ingest → research → qualify → draft, billed per
    accepted qualified prospect at the package per-unit rate."""
    tenant_id = job["tenant_id"]
    job_id = job["id"]
    payload = job.get("payload") or {}
    params = payload.get("params") or {}
    records: list[dict] = list(params.get("records") or [])
    allowance = int((entry.included_allowances or {}).get("prospects") or 350)
    records = records[:allowance]
    budget = _Budget(entry.usage_limits or {})

    async with session_scope() as session:
        from ..services.config import ConfigService

        discovery = DiscoveryService(session)
        research = ResearchService(session)
        qualification = QualificationService(session)
        personalization = PersonalizationService(session)
        icp = await ConfigService(session).active_icp(tenant_id)
        if icp is None:
            raise ConfigError("No active ICP", code="icp_missing", recovery_action="define_icp")

        for record in records:
            if not budget.allow_more(result["processed"]):
                result["failures"].append({
                    "unit": None, "error_code": "budget_exceeded",
                    "message": "Campaign stopped at its enforced budget",
                    "retryable": False,
                })
                break
            accepted = False
            try:
                ingest = await _unit_discover(session, tenant_id, record, params)
                if not ingest["accepted"]:
                    raise SlideinError(
                        "Prospect record rejected as duplicate or invalid",
                        code="prospect_duplicate", recovery_action="merge_duplicate",
                    )
                prospect_id = (ingest["detail"].get("prospect_ids") or [""])[0]
                researched = await _unit_research(session, tenant_id, prospect_id, params)
                if not researched["accepted"]:
                    raise SlideinError(
                        "Research produced no evidence", code="source_unavailable",
                        recovery_action="retry_stage", retryable=True,
                    )
                qualified = await qualification.record(
                    tenant_id=tenant_id,
                    prospect=await discovery.get_prospect(tenant_id, prospect_id),
                    icp=icp,
                    evidence_rows=await research.list_evidence(tenant_id, prospect_id),
                    actor="service:billing",
                )
                if not qualified.get("is_qualified"):
                    raise SlideinError(
                        "Prospect did not meet the ICP acceptance criteria",
                        code="icp_mismatch", recovery_action="review_icp",
                    )
                draft = await personalization.generate_draft(
                    tenant_id=tenant_id,
                    prospect=await discovery.get_prospect(tenant_id, prospect_id),
                    actor="service:billing",
                )
                accepted = draft.get("status") == "pending_review"
                result["outputs"].append({
                    "unit": prospect_id, "accepted": accepted,
                    "reference_id": draft.get("id") or "",
                    "qualification_score": qualified.get("score"),
                })
            except SlideinError as exc:
                result["failed_units"] += 1
                result["failures"].append({
                    "unit": record.get("email") or "",
                    "error_code": exc.code, "message": exc.message,
                    "retryable": exc.retryable,
                })
                continue
            result["processed"] += 1
            if accepted:
                result["accepted_units"] += 1
                for stage, stage_product in CAMPAIGN_STAGES:
                    _meter(session, tenant_id=tenant_id, job_id=job_id,
                           product_id=stage_product, units=1)


__all__ = ["JOB_KIND", "OperationService", "execute_operation_job"]
