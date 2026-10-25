"""Progress tracking + module isolation.

Every recon module reports unit completion here; the tracker blends module
chunk progress into a lead-level percentage using fixed weights and broadcasts
wire-schema envelopes on every transition. `guard()` wraps a module coroutine
with:
  * an asyncio timeout boundary,
  * full exception capture (traceback -> error_logs + FAILED status),
  * graceful degradation to a caller-supplied empty result.
"""
from __future__ import annotations

import asyncio
import traceback
from typing import Any, Awaitable, Callable

from ..events.bus import EventPublisher
from ..events.models import (
    EventEnvelope,
    LifecycleStatus,
    ModuleName,
    ModuleStatus,
)

# Weight-blend across modules -> lead-level progress_percentage (sums to 100).
MODULE_WEIGHTS: dict[ModuleName, float] = {
    ModuleName.WEBSCRAPER: 5.0,
    ModuleName.FIREENRICH: 10.0,
    ModuleName.SPIDERFOOT: 6.0,
    ModuleName.SUBFINDER: 7.0,
    ModuleName.DNSRECON: 5.0,
    ModuleName.MAIGRET: 16.0,
    ModuleName.BLACKBIRD: 12.0,
    ModuleName.HOLEHE: 5.0,
    ModuleName.BOMKESH: 4.0,
    ModuleName.MAILACCESS: 5.0,
    ModuleName.NOIMOSINY: 4.0,
    ModuleName.BRIGHTDATA: 3.0,
    ModuleName.GRAPH: 4.0,
    ModuleName.AI_AGENT_REASONING: 12.0,
}


class ProgressTracker:
    def __init__(
        self,
        *,
        task_id: str,
        lead_email: str,
        job_id: str | None = None,
        plans: dict[ModuleName, int] | None = None,
        publisher: type[EventPublisher] = EventPublisher,
    ):
        self.task_id = task_id
        self.job_id = job_id
        self.lead_email = lead_email
        self._publisher = publisher
        self._plans: dict[ModuleName, int] = plans or {}
        self._completed: dict[ModuleName, int] = {m: 0 for m in self._plans}
        self._module_status: dict[ModuleName, ModuleStatus] = {
            m: ModuleStatus.QUEUED for m in self._plans
        }

    # ------------------------------------------------------------------ #
    @classmethod
    def noop(cls) -> "ProgressTracker":
        """Silent tracker for inline/dev runs without Redis or task context."""
        t = cls(task_id="inline", lead_email="unknown")
        t._emit = lambda env: None  # type: ignore[method-assign]
        return t

    def set_plans(self, plans: dict[ModuleName, int]) -> None:
        """Install unit plans after construction (pipeline computes counts)."""
        self._plans = plans
        self._completed = {m: 0 for m in plans}
        self._module_status = {m: ModuleStatus.QUEUED for m in plans}

    def add_plan_units(self, module: ModuleName, extra: int) -> None:
        if extra > 0:
            self._plans[module] = self._plans.get(module, 0) + extra

    def status_of(self, module: ModuleName) -> ModuleStatus:
        return self._module_status.get(module, ModuleStatus.QUEUED)

    def _emit(self, env: EventEnvelope) -> None:
        self._publisher.publish(env)

    # ------------------------------------------------------------------ #
    def overall(self) -> float:
        """(completed_chunks / total_chunks) * 100, weight-blended per module."""
        total_w = sum(MODULE_WEIGHTS.get(m, 0.0) for m in self._plans) or 1.0
        acc = 0.0
        for m, total in self._plans.items():
            w = MODULE_WEIGHTS.get(m, 0.0)
            frac = min(self._completed.get(m, 0) / total, 1.0) if total else 0.0
            acc += w * frac
        return round(acc / total_w * 100, 1)

    def _publish(
        self,
        module: ModuleName,
        status: ModuleStatus,
        *,
        live: dict | None = None,
        logs: list[str] | None = None,
    ) -> None:
        self._module_status[module] = status
        self._emit(EventEnvelope(
            task_id=self.task_id,
            job_id=self.job_id,
            lead_email=self.lead_email,
            active_framework=module,
            lifecycle_status=LifecycleStatus.from_module_status(status),
            progress_percentage=self.overall(),
            chunk_progress={"completed_chunks": self._completed.get(module, 0),
                            "total_chunks": self._plans.get(module, 0)},
            extracted_delta=live or {},
            error_logs=" | ".join(logs) if logs else None,
        ))

    # ------------------------------------------------------------------ #
    async def unit_done(
        self, module: ModuleName, delta: int = 1, live: dict | None = None,
        logs: list[str] | None = None,
    ) -> None:
        self._completed[module] = self._completed.get(module, 0) + delta
        self._publish(module, ModuleStatus.EXTRACTING_DOM, live=live, logs=logs)

    async def set_state(
        self, module: ModuleName, status: ModuleStatus,
        live: dict | None = None, logs: list[str] | None = None,
    ) -> None:
        self._publish(module, status, live=live, logs=logs)

    async def guard(
        self,
        module: ModuleName,
        coro: Callable[[], Awaitable[Any]],
        empty: Any = None,
        timeout_s: float = 120.0,
    ) -> Any:
        """Run a module under timeout + exception isolation. Never raises."""
        await self.set_state(module, ModuleStatus.INITIALIZED)
        await self.set_state(module, ModuleStatus.RESOLVING_PROXIES)
        try:
            result = await asyncio.wait_for(coro(), timeout=timeout_s)
        except asyncio.TimeoutError:
            await self.set_state(
                module, ModuleStatus.FAILED,
                logs=[f"{module.value}: timeout after {timeout_s}s — module skipped"],
            )
            return empty
        except Exception:
            tb = traceback.format_exc(limit=6)
            await self.set_state(
                module, ModuleStatus.FAILED,
                logs=[f"{module.value}: exception — {tb}"],
            )
            return empty
        await self.set_state(module, ModuleStatus.COMPLETED)
        return result

    async def finalize(self, live: dict | None = None, failed: bool = False) -> None:
        for m in self._plans:
            if self._module_status.get(m) not in (
                ModuleStatus.COMPLETED, ModuleStatus.FAILED
            ):
                await self.set_state(m, ModuleStatus.FAILED,
                                     logs=[f"{m.value}: terminated before completion"])
        if not failed:
            for m in self._plans:
                self._completed[m] = self._plans.get(m, 0)
        last = ModuleName.AI_AGENT_REASONING if not failed else ModuleName.GRAPH
        self._emit(EventEnvelope(
            task_id=self.task_id, job_id=self.job_id, lead_email=self.lead_email,
            active_framework=last,
            lifecycle_status=LifecycleStatus.FAILED if failed else LifecycleStatus.COMPLETED,
            progress_percentage=self.overall(),
            chunk_progress={"completed_chunks":
                                sum(self._completed.values()),
                            "total_chunks": sum(self._plans.values())},
            extracted_delta=live or {},
            error_logs="lead marked FAILED — see framework events" if failed else None,
        ))
