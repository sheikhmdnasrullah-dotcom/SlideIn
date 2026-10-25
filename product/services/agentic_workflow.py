"""LangGraph-backed agentic workflow execution service.

A real stateful graph coordinates existing product agents:

    planning (deterministic fn, not an LLM)
      -> research      (ResearchAgent, typed output + provenance)
      -> qualification (QualificationAgent, consumes research output)
      -> evaluation    (deterministic schema/policy checks)
      -> [interrupt] await_approval (human gate; resume to continue)
      -> finalize

Durability: AsyncSqliteSaver checkpointer — executions survive process
restart; approval-paused runs resume by thread id. Tenant isolation is
enforced by thread-id scoping (`{tenant}:{execution}`) plus caller checks on
every read. Deterministic fallbacks keep the graph runnable without LLM keys;
agent exceptions route to a FAILED terminal state, never a hang.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, TypedDict

from product.core.errors import CrossTenantAccess
from product.core.scopes import Role


class AgentWorkflowState(TypedDict, total=False):
    tenant_id: str
    opportunity_id: str
    person: dict[str, Any]
    plan: list[str]
    research: dict[str, Any] | None
    qualification: dict[str, Any] | None
    evaluation: dict[str, Any] | None
    approved: bool
    status: str                      # RUNNING | WAITING_APPROVAL | COMPLETED | REJECTED | FAILED
    step_log: list[dict[str, Any]]
    error: str | None


def _log(state: AgentWorkflowState, step: str, detail: dict) -> None:
    state.setdefault("step_log", []).append(
        {"step": step, "ts": time.time(), **detail}
    )


def _deterministic_research(person: dict) -> dict:
    return {
        "who_are_they": f"{person.get('name', 'Unknown')} "
                      f"({person.get('location', 'location unknown')})",
        "fit_indicators": [],
        "recent_signals": [],
        "what_they_might_care_about": [],
        "source": "deterministic-fallback",
        "evidence_refs": [],
    }


def _deterministic_qualification(research: dict, person: dict) -> dict:
    known = sum(1 for v in research.values() if v not in (None, "", [], {}))
    score = min(30 + known * 10, 100)
    missing = [k for k in ("email", "location") if not person.get(k)]
    return {"score": score, "reasons": [f"{known} populated research fields"],
            "missing_data": missing, "source": "deterministic-fallback"}


class AgenticWorkflowService:
    """Executes and inspects agent workflows with durable checkpoints."""

    def __init__(self, db_path: str, *, research_agent=None,
                 qualification_agent=None):
        self._db_path = db_path
        self._research_agent = research_agent
        self._qualification_agent = qualification_agent
        self._saver = None
        self._graph = None

    # ------------------------------------------------------------------ #
    async def _build(self):
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from langgraph.graph import END, START, StateGraph
        import aiosqlite

        self._saver = AsyncSqliteSaver(await aiosqlite.connect(self._db_path))

        g = StateGraph(AgentWorkflowState)

        async def planning(state: AgentWorkflowState) -> AgentWorkflowState:
            state["plan"] = ["research", "qualify", "evaluate", "approve"]
            state["status"] = "RUNNING"
            _log(state, "planning", {"plan": state["plan"]})
            return state

        async def research(state: AgentWorkflowState) -> AgentWorkflowState:
            try:
                if self._research_agent is not None:
                    out = await self._research_agent.execute({
                        "org_id": state["tenant_id"],
                        "opportunity_id": state["opportunity_id"],
                        "person": state["person"],
                        "depth": "standard",
                    })
                    dossier = out.get("dossier") or out.get("research") or out
                else:
                    dossier = _deterministic_research(state["person"])
                if not isinstance(dossier, dict) or not dossier:
                    raise ValueError("research agent returned empty output")
                state["research"] = dossier
                _log(state, "research", {"keys": sorted(dossier)[:8]})
            except Exception as exc:
                state["error"] = f"research: {exc}"
            return state

        async def qualification(state: AgentWorkflowState) -> AgentWorkflowState:
            if state.get("error"):
                return state
            try:
                if self._qualification_agent is not None:
                    out = await self._qualification_agent.execute({
                        "org_id": state["tenant_id"],
                        "opportunity_id": state["opportunity_id"],
                        "research": state["research"],
                        "person": state["person"],
                    })
                    result = out.get("qualification") or out
                else:
                    result = _deterministic_qualification(
                        state["research"] or {}, state["person"])
                score = result.get("score")
                if not isinstance(score, (int, float)) or not (0 <= score <= 100):
                    raise ValueError("qualification score must be 0..100")
                state["qualification"] = result
                _log(state, "qualification", {"score": score})
            except Exception as exc:
                state["error"] = f"qualification: {exc}"
            return state

        async def evaluation(state: AgentWorkflowState) -> AgentWorkflowState:
            if state.get("error"):
                return state
            missing = (state["qualification"] or {}).get("missing_data", [])
            state["evaluation"] = {
                "complete": not missing,
                "missing_data": missing,
                "policy": "tenant_approval_required",
            }
            state["status"] = "WAITING_APPROVAL"
            _log(state, "evaluation", state["evaluation"])
            return state

        async def await_approval(state: AgentWorkflowState) -> AgentWorkflowState:
            """Runtime interrupt: the graph pauses here until a human
            decision arrives via Command(resume=...). No double-interrupt."""
            from langgraph.types import interrupt

            decision = interrupt({"gate": "await_approval",
                                  "evaluation": state.get("evaluation")})
            state["approved"] = bool(decision.get("approved"))
            state["status"] = "COMPLETED" if state["approved"] else "REJECTED"
            _log(state, "await_approval", {"approved": state["approved"]})
            return state

        def route(state: AgentWorkflowState) -> str:
            return "failed" if state.get("error") else "ok"

        async def failed(state: AgentWorkflowState) -> AgentWorkflowState:
            state["status"] = "FAILED"
            _log(state, "failed", {"error": state.get("error")})
            return state

        g.add_node("planning", planning)
        g.add_node("research", research)
        g.add_node("qualification", qualification)
        g.add_node("evaluation", evaluation)
        g.add_node("await_approval", await_approval)
        g.add_node("failed", failed)
        g.add_edge(START, "planning")
        g.add_edge("planning", "research")
        g.add_conditional_edges("research", route, {"ok": "qualification", "failed": "failed"})
        g.add_conditional_edges("qualification", route, {"ok": "evaluation", "failed": "failed"})
        g.add_conditional_edges("evaluation", route, {"ok": "await_approval", "failed": "failed"})
        g.add_edge("await_approval", END)
        g.add_edge("failed", END)
        self._graph = g.compile(checkpointer=self._saver)
        return self

    @classmethod
    async def create(cls, db_path: str, **kwargs) -> "AgenticWorkflowService":
        svc = cls(db_path, **kwargs)
        await svc._build()
        return svc

    # ------------------------------------------------------------------ #
    async def start(self, *, tenant_id: str, person: dict,
                    opportunity_id: str | None = None) -> dict:
        execution_id = uuid.uuid4().hex[:16]
        state: AgentWorkflowState = {
            "tenant_id": tenant_id,
            "opportunity_id": opportunity_id or execution_id,
            "person": dict(person),
            "approved": False,
            "status": "RUNNING",
            "step_log": [],
            "error": None,
        }
        config = {"configurable": {"thread_id": f"{tenant_id}:{execution_id}"}}
        final_state = None
        async for chunk in self._graph.astream(state, config, stream_mode="values"):
            final_state = chunk
        return self._view(final_state, execution_id)

    async def resume(self, *, tenant_id: str, execution_id: str,
                     approved: bool) -> dict:
        """Resume an approval-paused execution. Only the owning tenant can."""
        from langgraph.types import Command

        config = {"configurable": {"thread_id": f"{tenant_id}:{execution_id}"}}
        current = await self.get_execution(tenant_id=tenant_id,
                                           execution_id=execution_id,
                                           caller_tenant_id=tenant_id,
                                           role=Role.TENANT_ADMIN)
        if current["status"] != "WAITING_APPROVAL":
            raise ValueError(f"execution is {current['status']}, not awaiting approval")
        final_state = None
        async for chunk in self._graph.astream(
            Command(resume={"approved": approved}), config, stream_mode="values"
        ):
            final_state = chunk
        return self._view(final_state, execution_id)

    async def get_execution(self, *, tenant_id: str, execution_id: str,
                            caller_tenant_id: str | None, role: Role) -> dict:
        if role not in (Role.PLATFORM_ADMIN, Role.SYSTEM) \
                and caller_tenant_id != tenant_id:
            raise CrossTenantAccess("cannot inspect another tenant's execution")
        config = {"configurable": {"thread_id": f"{tenant_id}:{execution_id}"}}
        snap = await self._graph.aget_state(config)
        if snap is None or not snap.values:
            raise KeyError(execution_id)
        return self._view(dict(snap.values), execution_id)

    @staticmethod
    def _view(state: dict, execution_id: str) -> dict:
        return {
            "execution_id": execution_id,
            "tenant_id": state.get("tenant_id"),
            "status": state.get("status"),
            "plan": state.get("plan", []),
            "research_keys": sorted((state.get("research") or {}).keys()),
            "qualification": state.get("qualification"),
            "evaluation": state.get("evaluation"),
            "step_log": state.get("step_log", []),
            "error": state.get("error"),
        }
