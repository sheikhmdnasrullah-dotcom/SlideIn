"""Bounded, persistent execution of registered research tools."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime

from sqlalchemy import select

from ..errors import ProviderError, SlideinError
from ..ids import new_id
from ..integrations.firecrawl import FirecrawlAdapter
from ..integrations.openosint import DEFAULT_LOOKUPS, OpenOSINTAdapter
from ..integrations.tool_registry import ToolContext, build_coverage_plan
from ..models import ToolAttempt, ToolExecution, utcnow
from .osint import claims_from_results, targets_for
from .research import Claim, ResearchService, WebsiteConnector


class ResearchToolOrchestrator:
    def __init__(self, session) -> None:
        self.session = session

    async def collect(
        self,
        *,
        tenant_id: str,
        prospect,
        actor: str,
        execution_id: str = "",
        capabilities: list[str] | None = None,
        max_attempts: int = 12,
        budget_seconds: float = 120.0,
        offline_connector: bool = False,
        depth: str = "standard",
    ) -> dict:
        execution_key = execution_id.strip() or new_id("tool_execution")
        existing = await self._existing(tenant_id, execution_key)
        if existing is not None:
            if existing.status == "failed":
                raise ProviderError(
                    "This research execution previously failed without evidence",
                    code="source_unavailable",
                    details={"tool_execution_id": existing.id, "replayed": True},
                    recovery_action="retry_stage",
                )
            output = dict(existing.output_snapshot or {})
            summary = dict(output.get("tool_execution") or {})
            summary["replayed"] = True
            output["tool_execution"] = summary
            return output

        domain = (prospect.company_domain or prospect.email.split("@")[-1]).strip().strip(".")
        full_name = f"{prospect.first_name} {prospect.last_name}".strip()
        context = ToolContext(
            domain=domain,
            email=prospect.email,
            name=prospect.company_name or full_name,
            username=prospect.linkedin_url.rstrip("/").split("/")[-1] if prospect.linkedin_url else "",
        )
        plan = build_coverage_plan(context=context, stage="research", capabilities=capabilities)
        execution = ToolExecution(
            id=new_id("tool_exec"),
            tenant_id=tenant_id,
            execution_key=execution_key,
            stage="research",
            subject_id=prospect.id,
            requested_capabilities=plan["requested_capabilities"],
            triggered_by=actor,
        )
        self.session.add(execution)
        await self.session.flush()
        attempts = await self._create_attempts(execution, plan["ledger"])

        started = time.monotonic()
        executed_count = 0
        resolved: set[str] = set()
        claims: list[Claim] = []
        failed_tools: list[str] = []
        for attempt in attempts:
            if attempt.status != "ready":
                continue
            pending = [cap for cap in attempt.capabilities if cap not in resolved]
            if not pending:
                self._skip(attempt, "capability_already_satisfied")
                continue
            if executed_count >= max_attempts or time.monotonic() - started >= budget_seconds:
                self._skip(attempt, "budget_exhausted")
                continue

            attempt.capabilities = pending
            attempt.status = "running"
            attempt.started_at = utcnow()
            attempt.fallback_from = failed_tools[-1] if failed_tools else ""
            await self.session.flush()
            call_started = time.monotonic()
            try:
                remaining = max(0.001, budget_seconds - (time.monotonic() - started))
                produced, produced_capabilities = await asyncio.wait_for(
                    self._run_tool(
                        attempt.tool_id,
                        prospect=prospect,
                        depth=depth,
                        offline_connector=offline_connector,
                        requested=pending,
                    ),
                    timeout=remaining,
                )
                claims.extend(produced)
                resolved.update(produced_capabilities)
                attempt.status = "succeeded"
                attempt.reason = "evidence_collected" if produced else "no_evidence"
                failed_tools = [tool for tool in failed_tools if tool != attempt.tool_id]
            except Exception as exc:  # noqa: BLE001 - every adapter failure enters the ledger
                attempt.status = "failed"
                attempt.error_code = exc.code if isinstance(exc, SlideinError) else (
                    "provider_timeout" if isinstance(exc, asyncio.TimeoutError) else "provider_error"
                )
                attempt.error_message = self._safe_error(exc)
                attempt.reason = attempt.error_code
                if attempt.tool_id not in failed_tools:
                    failed_tools.append(attempt.tool_id)
            finally:
                executed_count += 1
                attempt.duration_ms = int((time.monotonic() - call_started) * 1000)
                attempt.finished_at = utcnow()
                await self.session.flush()

        execution.resolved_capabilities = sorted(resolved)
        unresolved = sorted(set(plan["requested_capabilities"]) - resolved)
        if not claims:
            execution.status = "failed"
            execution.finished_at = utcnow()
            execution.output_snapshot = {
                "tool_execution": self._summary(execution, attempts, unresolved),
                "mock_success": False,
            }
            await self.session.flush()
            raise ProviderError(
                "No research tool produced evidence",
                code="source_unavailable",
                details={"tool_execution_id": execution.id, "unresolved_capabilities": unresolved},
                recovery_action="retry_stage",
            )

        result = await ResearchService(self.session).persist_claims(
            tenant_id=tenant_id,
            prospect=prospect,
            claims=claims,
            actor=actor,
            collector="orchestrated",
        )
        evidence_ids = set(result["evidence_ids"])
        for attempt in attempts:
            if attempt.status == "succeeded":
                attempt.evidence_ids = sorted(
                    evidence_id for evidence_id in evidence_ids
                    if self._evidence_belongs_to_tool(evidence_id, result, attempt.tool_id)
                )
        result.pop("evidence_records", None)
        execution.status = "succeeded"
        execution.finished_at = utcnow()
        result["tool_execution"] = self._summary(execution, attempts, unresolved)
        result["tool_execution"]["replayed"] = False
        result["tool_execution"]["mock_success"] = False
        execution.output_snapshot = result
        await self.session.flush()
        return result

    async def _existing(self, tenant_id: str, execution_key: str) -> ToolExecution | None:
        return (
            await self.session.execute(
                select(ToolExecution).where(
                    ToolExecution.tenant_id == tenant_id,
                    ToolExecution.execution_key == execution_key,
                )
            )
        ).scalars().first()

    async def _create_attempts(self, execution: ToolExecution, ledger: list[dict]) -> list[ToolAttempt]:
        attempts = []
        for position, row in enumerate(ledger):
            attempt = ToolAttempt(
                id=new_id("tool_attempt"),
                execution_id=execution.id,
                tenant_id=execution.tenant_id,
                tool_id=row["tool_id"],
                capabilities=list(row["capabilities"]),
                status=row["status"],
                reason=row["reason"],
                missing=list(row["missing"]),
                position=position,
            )
            self.session.add(attempt)
            attempts.append(attempt)
        await self.session.flush()
        return attempts

    async def _run_tool(
        self,
        tool_id: str,
        *,
        prospect,
        depth: str,
        offline_connector: bool,
        requested: list[str],
    ) -> tuple[list[Claim], set[str]]:
        if tool_id == "openosint":
            results = await OpenOSINTAdapter().run_lookups(
                targets_for(prospect, list(DEFAULT_LOOKUPS)), list(DEFAULT_LOOKUPS)
            )
            raw = claims_from_results(results, prospect)
            if not raw:
                raise ProviderError(
                    "OpenOSINT produced no evidence",
                    code="source_unavailable",
                    recovery_action="retry_stage",
                )
            resolved = set()
            for item in raw:
                collector = item["collector"]
                if collector.endswith(":dns"):
                    resolved.add("dns_research")
                elif collector.endswith(":exposure"):
                    resolved.add("exposure_research")
                elif collector.endswith(":github"):
                    resolved.add("code_footprint")
            return [Claim(**item) for item in raw], resolved & set(requested)
        if tool_id == "website_connector":
            website = WebsiteConnector(offline=offline_connector)
            claims = await asyncio.to_thread(website.collect, prospect, depth=depth)
            return claims, {"website_fetch", "company_enrichment"} & set(requested)
        if tool_id == "firecrawl":
            raw = await FirecrawlAdapter().scrape(
                (prospect.company_domain or prospect.email.split("@")[-1]).strip().strip(".")
            )
            return [Claim(**item) for item in raw], {"website_fetch", "company_enrichment"} & set(requested)
        raise ProviderError(
            f"Tool {tool_id!r} has no execution adapter",
            code="adapter_not_wired",
            recovery_action="configure_provider",
        )

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if isinstance(exc, SlideinError):
            return exc.message[:500]
        if isinstance(exc, asyncio.TimeoutError):
            return "Research tool exceeded the execution budget"
        return f"Research adapter failed with {type(exc).__name__}"

    @staticmethod
    def _skip(attempt: ToolAttempt, reason: str) -> None:
        attempt.status = "skipped"
        attempt.reason = reason
        attempt.finished_at = utcnow()

    @staticmethod
    def _evidence_belongs_to_tool(evidence_id: str, result: dict, tool_id: str) -> bool:
        evidence = result.get("evidence_records") or []
        row = next((item for item in evidence if item["id"] == evidence_id), None)
        return bool(row and (row["collector"] == tool_id or row["collector"].startswith(f"{tool_id}:")))

    @staticmethod
    def _summary(execution: ToolExecution, attempts: list[ToolAttempt], unresolved: list[str]) -> dict:
        return {
            "id": execution.id,
            "execution_key": execution.execution_key,
            "status": execution.status,
            "complete_coverage": True,
            "executed": True,
            "requested_capabilities": list(execution.requested_capabilities),
            "resolved_capabilities": sorted(set(execution.resolved_capabilities)),
            "unresolved_capabilities": unresolved,
            "attempts": [
                {
                    "tool_id": attempt.tool_id,
                    "capabilities": list(attempt.capabilities),
                    "status": attempt.status,
                    "reason": attempt.reason,
                    "error_code": attempt.error_code,
                    "missing": list(attempt.missing),
                    "fallback_from": attempt.fallback_from,
                    "evidence_ids": list(attempt.evidence_ids),
                    "position": attempt.position,
                    "duration_ms": attempt.duration_ms,
                }
                for attempt in sorted(attempts, key=lambda item: item.position)
            ],
        }


__all__ = ["ResearchToolOrchestrator"]
