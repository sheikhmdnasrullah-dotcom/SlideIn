"""The workflow runtime.

`StageRunner` is the only way pipeline stages advance. It:

  1. validates the call against the stage contract (`requires`),
  2. checks the permission,
  3. writes a `stage_runs` row before executing,
  4. runs the stage function,
  5. applies the declared lifecycle transition,
  6. records the run as `succeeded` / `needs_review` / `failed`,
  7. attaches the failure code, retryability and recovery action,
  8. writes one activity row.

Retries are explicit: a caller re-invokes the stage and the runner
increments `attempt` on the same subject. A retryable failure keeps the
prospect where it is so the operator can retry; a non-retryable failure
also keeps the record in place but reports the recovery action that would
unblock it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .contracts import StageContract, StageName, contract_for
from .errors import RECOVERY_ACTION, RETRYABLE, SlideinError
from .ids import new_id, run_key
from .models import RunStatus, StageRun, utcnow
from .serialize import stage_run

logger = logging.getLogger("slidein.runtime")

StageFn = Callable[[dict, AsyncSession], Awaitable[dict]]

ROLE_RANK = {"viewer": 1, "service": 2, "operator": 3, "admin": 4}


@dataclass
class StageOutcome:
    """What a stage returned, normalised."""

    stage: str
    status: str
    outputs: dict = field(default_factory=dict)
    reason: str = ""
    needs_review: list[str] = field(default_factory=list)
    from_status: str = ""
    to_status: str = ""
    error_code: str = ""
    error_message: str = ""
    recovery_action: str = ""
    retryable: bool = False
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "status": self.status,
            "outputs": self.outputs,
            "reason": self.reason,
            "needs_review": self.needs_review,
            "from_status": getattr(self, "from_status", ""),
            "to_status": getattr(self, "to_status", ""),
            "run_id": self.details.get("run_id"),
            "attempt": self.details.get("attempt"),
            "error": {
                "code": self.error_code,
                "message": self.error_message,
                "recovery_action": self.recovery_action,
                "retryable": self.retryable,
            }
            if self.error_code
            else None,
            "details": self.details,
        }


class StageRunner:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- public API --------------------------------------------------------

    async def run(
        self,
        stage: StageName | str,
        *,
        tenant_id: str,
        payload: Mapping[str, Any],
        actor: str = "operator",
        role: str = "operator",
        subject_type: str = "prospect",
        subject_id: str | None = None,
        executor: StageFn,
    ) -> StageOutcome:
        contract = contract_for(stage)
        stage_name = contract.stage.value

        problems = contract.validate_input(dict(payload))
        if problems:
            return await self._contract_failure(contract, tenant_id, subject_id, actor, problems)

        if not self._has_permission(contract, role):
            return await self._permission_failure(contract, tenant_id, subject_id, actor, role)

        resolved_subject = (
            subject_id
            or str(payload.get("prospect_id") or payload.get("draft_id") or "")
        )
        key = run_key(tenant_id, stage_name, resolved_subject)

        prior = (
            await self.session.execute(
                select(StageRun).where(StageRun.run_key == key).order_by(StageRun.attempt.desc())
            )
        ).scalars().first()
        attempt = (prior.attempt + 1) if prior is not None else 1

        run = StageRun(
            id=new_id("stage_run"),
            tenant_id=tenant_id,
            run_key=key,
            stage=stage_name,
            subject_type=subject_type,
            subject_id=resolved_subject,
            status=RunStatus.RUNNING.value,
            attempt=attempt,
            max_attempts=contract.max_attempts,
            triggered_by=actor,
            input_snapshot=self._safe_snapshot(dict(payload)),
            started_at=utcnow(),
        )
        self.session.add(run)
        await self.session.flush()

        if attempt > contract.max_attempts:
            return await self._finish_failure(
                run,
                contract=contract,
                code="rate_limited" if attempt > contract.max_attempts else "unknown",
                message=(
                    f"{contract.title} has already been attempted "
                    f"{contract.max_attempts} times; the subject needs human review."
                ),
                recovery="review_prospect_status",
            )

        try:
            raw = await executor(dict(payload), self.session)
            if not isinstance(raw, Mapping):
                raise SlideinError(
                    f"{contract.title} returned {type(raw).__name__}, expected a mapping",
                    code="unknown",
                )
        except SlideinError as exc:
            return await self._finish_failure(
                run, contract=contract, code=exc.code, message=exc.message,
                recovery=exc.recovery_action, details=exc.details,
            )
        except Exception as exc:  # noqa: BLE001 - anything else is a failed run
            import traceback as _tb

            logger.error(
                "stage %s crashed on %s\n%s",
                stage_name, resolved_subject, _tb.format_exc(),
            )
            return await self._finish_failure(
                run, contract=contract, code="unknown",
                message=f"{type(exc).__name__}: {exc}",
                recovery="retry_stage",
            )

        outputs = self._normalise_outputs(raw)
        status = str(raw.get("status", "succeeded"))
        needs_review = [str(x) for x in (raw.get("needs_review") or [])]

        if status == "failed":
            error = raw.get("error") or {}
            return await self._finish_failure(
                run,
                contract=contract,
                code=str(error.get("code") or "unknown"),
                message=str(error.get("message") or "stage reported a failure"),
                recovery=str(error.get("recovery_action") or "retry_stage"),
                details=dict(outputs.get("details") or {}),
            )

        run.output_snapshot = self._safe_snapshot(outputs)
        run.needs_review = needs_review
        run.from_status = str(raw.get("from_status", ""))
        run.to_status = str(raw.get("to_status", ""))
        run.status = (
            RunStatus.NEEDS_REVIEW.value if needs_review else RunStatus.SUCCEEDED.value
        )
        run.finished_at = utcnow()
        await self.session.flush()

        await self._record_activity(
            run=run,
            contract=contract,
            action=f"stage.{run.stage}."
            + ("needs_review" if needs_review else "succeeded"),
            summary=self._summary(contract, outputs, needs_review),
            reason=", ".join(needs_review),
            subject_id=resolved_subject,
            details={"attempt": run.attempt, "outputs": self._safe_snapshot(outputs)},
        )

        return StageOutcome(
            stage=stage_name,
            status=run.status,
            outputs=outputs,
            reason=", ".join(needs_review),
            needs_review=needs_review,
            from_status=run.from_status,
            to_status=run.to_status,
            details={"run_id": run.id, "attempt": run.attempt},
        )

    # -- helpers -----------------------------------------------------------

    _ENVELOPE_KEYS = frozenset(
        {"status", "outputs", "needs_review", "from_status", "to_status", "error", "details"}
    )

    def _normalise_outputs(self, raw: Mapping[str, Any]) -> dict:
        """Accept either `{"outputs": {...}}` or a flat output mapping."""
        nested = raw.get("outputs")
        if isinstance(nested, Mapping):
            return dict(nested)
        return {k: v for k, v in raw.items() if k not in self._ENVELOPE_KEYS}

    def _has_permission(self, contract: StageContract, role: str) -> bool:
        if contract.permission == "service":
            # `service` is a machine credential: only service may run a
            # service-role stage, and a human may never assume it.
            return role == "service"
        if role == "service":
            return False
        required = ROLE_RANK.get(contract.permission, 3)
        granted = ROLE_RANK.get(role, 1)
        return granted >= required

    async def _contract_failure(
        self, contract: StageContract, tenant_id: str, subject_id: str | None,
        actor: str, problems: list[str],
    ) -> StageOutcome:
        message = "Stage contract violated: " + "; ".join(problems)
        await self._orphan_activity(
            tenant_id=tenant_id,
            stage=contract.stage.value,
            action="stage.contract_violated",
            summary=message,
            reason="invalid_input",
            actor=actor,
            subject_id=subject_id or "",
        )
        return StageOutcome(
            stage=contract.stage.value,
            status="failed",
            error_code="invalid_input",
            error_message=message,
            recovery_action="fix_prospect_record",
            retryable=False,
            details={"violations": problems},
        )

    async def _permission_failure(
        self, contract: StageContract, tenant_id: str, subject_id: str | None,
        actor: str, role: str,
    ) -> StageOutcome:
        message = (
            f"Role {role!r} cannot run {contract.title}; "
            f"requires {contract.permission!r}."
        )
        await self._orphan_activity(
            tenant_id=tenant_id,
            stage=contract.stage.value,
            action="stage.not_authorized",
            summary=message,
            reason="insufficient_role",
            actor=actor,
            subject_id=subject_id or "",
        )
        return StageOutcome(
            stage=contract.stage.value,
            status="failed",
            error_code="not_authorized",
            error_message=message,
            recovery_action="request_authorization",
            retryable=False,
            details={"role": role, "required": contract.permission},
        )

    async def _finish_failure(
        self,
        run: StageRun,
        *,
        contract: StageContract,
        code: str,
        message: str,
        recovery: str,
        details: dict | None = None,
    ) -> StageOutcome:
        run.status = RunStatus.FAILED.value
        run.error_code = code
        run.error_message = message
        run.recovery_action = recovery or RECOVERY_ACTION.get(code, "retry_stage")
        run.finished_at = utcnow()
        run.output_snapshot = self._safe_snapshot(details or {})
        await self.session.flush()

        retryable = code in RETRYABLE
        await self._record_activity(
            run=run,
            contract=contract,
            action="stage.failed",
            summary=f"{contract.title} failed: {message}",
            reason=code,
            subject_id=run.subject_id,
            details={
                "attempt": run.attempt,
                "max_attempts": run.max_attempts,
                "recovery_action": run.recovery_action,
                "retryable": retryable,
            },
        )
        return StageOutcome(
            stage=run.stage,
            status="failed",
            outputs=details or {},
            from_status=run.from_status,
            to_status=run.to_status,
            error_code=code,
            error_message=message,
            recovery_action=run.recovery_action,
            retryable=retryable,
            details={"run_id": run.id, "attempt": run.attempt, **(details or {})},
        )

    async def _record_activity(
        self,
        *,
        run: StageRun,
        contract: StageContract,
        action: str,
        summary: str,
        reason: str,
        subject_id: str,
        details: dict,
    ) -> None:
        from .services.activity import ActivityService

        await ActivityService(self.session).record(
            tenant_id=run.tenant_id,
            action=action,
            actor=run.triggered_by or "system",
            actor_role=self._role_for(run.triggered_by),
            summary=summary,
            reason=reason,
            entity_type=(
                "draft"
                if run.subject_type == "draft"
                else "prospect"
            ),
            entity_id=subject_id,
            prospect_id=subject_id if run.subject_type != "draft" else None,
            stage=run.stage,
            run_id=run.id,
            details=details,
        )

    async def _orphan_activity(
        self, *, tenant_id: str, stage: str, action: str, summary: str,
        reason: str, actor: str, subject_id: str,
    ) -> None:
        from .services.activity import ActivityService

        await ActivityService(self.session).record(
            tenant_id=tenant_id,
            action=action,
            actor=actor or "system",
            actor_role=self._role_for(actor),
            summary=summary,
            reason=reason,
            entity_type="prospect",
            entity_id=subject_id,
            prospect_id=subject_id or None,
            stage=stage,
        )

    @staticmethod
    def _role_for(actor: str) -> str:
        if actor in ("system", "inbound_webhook", "transport"):
            return "system"
        if actor.startswith("api:"):
            return "service"
        return "operator"

    @staticmethod
    def _summary(contract: StageContract, outputs: dict, needs_review: list[str]) -> str:
        if contract.stage is StageName.DISCOVER:
            return (
                f"Discovery created {outputs.get('created', 0)} prospect(s), "
                f"{outputs.get('duplicates', 0)} duplicate(s) skipped."
            )
        if contract.stage is StageName.RESEARCH:
            return (
                f"Research collected {outputs.get('evidence_count', 0)} evidence item(s), "
                f"{outputs.get('verified_count', 0)} verified."
            )
        if contract.stage is StageName.QUALIFY:
            return (
                f"Qualification scored {outputs.get('score', 0)}/100 "
                f"({'qualified' if outputs.get('is_qualified') else 'not qualified'})."
            )
        if contract.stage is StageName.PERSONALIZE:
            return (
                f"Personalization prepared draft v{outputs.get('draft_version', 1)} "
                f"with {len(outputs.get('attributed_evidence_ids') or [])} cited evidence item(s)."
            )
        if contract.stage is StageName.OUTREACH:
            return f"Outreach dispatched via {outputs.get('transport', 'transport')}."
        if contract.stage is StageName.CONVERSE:
            return f"Reply classified as {outputs.get('intent', 'unclassified')}."
        return f"{contract.title} completed."

    @staticmethod
    def _safe_snapshot(payload: Mapping[str, Any], limit: int = 4000) -> dict:
        try:
            text = json.dumps(dict(payload), default=str)
        except (TypeError, ValueError):
            text = str(dict(payload))
        if len(text) <= limit:
            return dict(payload)
        return {"truncated": True, "preview": text[:limit]}

    # -- reads -------------------------------------------------------------

    async def list_runs(
        self,
        tenant_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        stage: str | None = None,
        status: str | None = None,
        subject_id: str | None = None,
    ) -> tuple[list[dict], int]:
        query = select(StageRun).where(StageRun.tenant_id == tenant_id)
        if stage:
            query = query.where(StageRun.stage == stage)
        if status:
            query = query.where(StageRun.status == status)
        if subject_id:
            query = query.where(StageRun.subject_id == subject_id)
        rows = (
            await self.session.execute(
                query.order_by(StageRun.started_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        total = (
            await self.session.execute(
                select(func.count()).select_from(StageRun).where(
                    StageRun.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        return [stage_run(r) for r in rows], int(total)

    async def latest_run_for(self, tenant_id: str, subject_id: str) -> dict | None:
        row = (
            await self.session.execute(
                select(StageRun)
                .where(
                    StageRun.tenant_id == tenant_id,
                    StageRun.subject_id == subject_id,
                )
                .order_by(StageRun.started_at.desc())
            )
        ).scalars().first()
        return stage_run(row) if row else None

    async def runs_for_subject(self, tenant_id: str, subject_id: str) -> list[dict]:
        rows = (
            await self.session.execute(
                select(StageRun)
                .where(
                    StageRun.tenant_id == tenant_id,
                    StageRun.subject_id == subject_id,
                )
                .order_by(StageRun.started_at.asc())
            )
        ).scalars().all()
        return [stage_run(r) for r in rows]

    async def failed_runs(self, tenant_id: str, *, limit: int = 20) -> list[dict]:
        rows = (
            await self.session.execute(
                select(StageRun)
                .where(
                    StageRun.tenant_id == tenant_id,
                    StageRun.status == RunStatus.FAILED.value,
                )
                .order_by(StageRun.started_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [stage_run(r) for r in rows]

    async def needs_review_runs(self, tenant_id: str, *, limit: int = 20) -> list[dict]:
        rows = (
            await self.session.execute(
                select(StageRun)
                .where(
                    StageRun.tenant_id == tenant_id,
                    StageRun.status == RunStatus.NEEDS_REVIEW.value,
                )
                .order_by(StageRun.started_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [stage_run(r) for r in rows]


def transition_guard(
    table: Mapping[str, tuple[str, ...]], current: str, target: str
) -> tuple[bool, str]:
    result = check_transition(table, current, target)
    return result.ok, result.reason


__all__ = ["ROLE_RANK", "StageOutcome", "StageRunner", "transition_guard"]
