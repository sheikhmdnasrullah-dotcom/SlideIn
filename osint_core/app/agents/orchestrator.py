"""Agent orchestrator — event-driven sequencing.

Flow:  Investigator ∥ Researcher  ->  Copywriter  (Copywriter needs both).

Each agent runs under its own timeout boundary; a failed agent yields an
empty dict + a log line in the stream rather than failing the lead. Every
completed agent is one unit of AI_AGENT_REASONING progress.
"""
from __future__ import annotations

import asyncio

from ..core.progress import ProgressTracker
from ..events.models import ModuleName, ModuleStatus
from .base import AgentContext, LLMClient
from .copywriter import Copywriter
from .investigator import Investigator
from .researcher import Researcher


class AgentOrchestrator:
    AGENT_UNITS = 3  # investigator, researcher, copywriter

    def __init__(self, tracker: ProgressTracker, llm: LLMClient | None = None):
        self._tracker = tracker
        self._llm = llm or LLMClient()
        self._agents = {
            "investigator": Investigator(self._llm),
            "researcher": Researcher(self._llm),
            "copywriter": Copywriter(self._llm),
        }

    async def run(self, ctx: AgentContext) -> dict:
        out: dict = {}

        async def _phase_one():
            inv, res = await asyncio.gather(
                self._run_agent("investigator", ctx),
                self._run_agent("researcher", ctx),
            )
            out["investigator"], out["researcher"] = inv, res
            ctx.prior.update({"investigator": inv, "researcher": res})

        await asyncio.wait_for(_phase_one(), timeout=120)
        out["copywriter"] = await asyncio.wait_for(
            self._run_agent("copywriter", ctx), timeout=90
        )
        return out

    async def _run_agent(self, name: str, ctx: AgentContext) -> dict:
        try:
            result = await asyncio.wait_for(self._agents[name].run(ctx), timeout=90)
        except (asyncio.TimeoutError, Exception) as exc:
            await self._tracker.set_state(
                ModuleName.AI_AGENT_REASONING, ModuleStatus.EXTRACTING_DOM,
                logs=[f"agent {name} failed/isolated: {exc}"],
            )
            result = {}
        if hasattr(result, "model_dump"):
            result = result.model_dump()
        await self._tracker.unit_done(
            ModuleName.AI_AGENT_REASONING,
            live={"agent": name, "done": True},
        )
        return result
