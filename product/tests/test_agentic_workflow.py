"""LangGraph agentic workflow: structured handoff, approval interrupt +
resume, failure terminal state, durable checkpoint, tenant isolation.

Synchronous wrappers (asyncio.run per test) keep aiosqlite on a single,
deterministic event loop per test — no pytest-asyncio loop scoping issues.
"""

import asyncio

import pytest

from product.core.errors import CrossTenantAccess
from product.core.scopes import Role
from product.services.agentic_workflow import AgenticWorkflowService


class _FailingAgent:
    async def execute(self, context):
        raise ConnectionError("llm provider unreachable")


PERSON = {"name": "Demo Person", "location": "Austin, TX"}


def _run(coro):
    return asyncio.run(coro)


def test_full_run_with_approval_interrupt(tmp_path):
    async def scenario():
        svc = await AgenticWorkflowService.create(str(tmp_path / "cp.sqlite"))
        view = await svc.start(tenant_id="t1", person=dict(PERSON))
        assert view["status"] == "WAITING_APPROVAL"
        assert view["research_keys"], "research output must exist before the gate"
        q = view["qualification"]
        assert q and 0 <= q["score"] <= 100
        assert [s["step"] for s in view["step_log"]] == [
            "planning", "research", "qualification", "evaluation"]

        exec_id = view["execution_id"]
        resumed = await svc.resume(tenant_id="t1", execution_id=exec_id,
                                   approved=True)
        assert resumed["status"] == "COMPLETED"
        assert [s["step"] for s in resumed["step_log"]] == [
            "planning", "research", "qualification", "evaluation", "await_approval"]

        # durable: re-read from the checkpointer after "restart"
        svc2 = await AgenticWorkflowService.create(str(tmp_path / "cp.sqlite"))
        reread = await svc2.get_execution(tenant_id="t1", execution_id=exec_id,
                                          caller_tenant_id="t1",
                                          role=Role.TENANT_ADMIN)
        assert reread["status"] == "COMPLETED"
        assert reread["qualification"]["score"] == q["score"]
    _run(scenario())


def test_rejection_path(tmp_path):
    async def scenario():
        svc = await AgenticWorkflowService.create(str(tmp_path / "cp.sqlite"))
        view = await svc.start(tenant_id="t1", person=dict(PERSON))
        out = await svc.resume(tenant_id="t1", execution_id=view["execution_id"],
                               approved=False)
        assert out["status"] == "REJECTED"
    _run(scenario())


def test_failure_terminal_state(tmp_path):
    async def scenario():
        svc = await AgenticWorkflowService.create(
            str(tmp_path / "cp.sqlite"), research_agent=_FailingAgent())
        view = await svc.start(tenant_id="t1", person=dict(PERSON))
        assert view["status"] == "FAILED"
        assert "llm provider unreachable" in view["error"]
        assert [s["step"] for s in view["step_log"]][-1] == "failed"
    _run(scenario())


def test_execution_tenant_isolation(tmp_path):
    async def scenario():
        svc = await AgenticWorkflowService.create(str(tmp_path / "cp.sqlite"))
        view = await svc.start(tenant_id="t1", person=dict(PERSON))
        with pytest.raises(CrossTenantAccess):
            await svc.get_execution(tenant_id="t1",
                                    execution_id=view["execution_id"],
                                    caller_tenant_id="t2", role=Role.TENANT_ADMIN)
        with pytest.raises(KeyError):
            await svc.get_execution(tenant_id="t1", execution_id="no-such-exec",
                                    caller_tenant_id="t1", role=Role.TENANT_ADMIN)
    _run(scenario())
