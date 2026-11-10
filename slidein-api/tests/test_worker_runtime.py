"""Hermetic regressions for PostgreSQL and Celery runtime boundaries."""

from __future__ import annotations

import asyncio

import pytest

from slidein_api import db
from slidein_api.workers import tasks


@pytest.mark.asyncio
async def test_legacy_column_upgrade_cannot_rollback_schema_creation(monkeypatch):
    calls = []

    class FakeConnection:
        async def run_sync(self, _operation):
            calls.append("create_schema")

        async def execute(self, _statement):
            calls.append("legacy_upgrade")
            raise RuntimeError("duplicate column")

    class FakeTransaction:
        async def __aenter__(self):
            calls.append("begin")
            return FakeConnection()

        async def __aexit__(self, *_args):
            calls.append("end")
            return False

    class FakeEngine:
        def begin(self):
            return FakeTransaction()

    monkeypatch.setattr(db, "engine", FakeEngine())
    await db.init_db()
    assert calls == [
        "begin", "create_schema", "end",
        "begin", "legacy_upgrade", "end",
    ]


def test_celery_adapter_reuses_and_closes_its_worker_loop(monkeypatch):
    loops = []

    async def fake_execute(job_id):
        loops.append(asyncio.get_running_loop())
        return {"id": job_id}

    monkeypatch.setattr(tasks, "execute_job", fake_execute)
    try:
        assert tasks.execute_job_task("one") == {"id": "one"}
        assert tasks.execute_job_task("two") == {"id": "two"}
        assert len(loops) == 2
        assert loops[0] is loops[1]
    finally:
        tasks._close_worker_loop()
    assert loops[0].is_closed()


@pytest.mark.asyncio
async def test_scheduler_tick_dispatches_due_jobs(configured_workspace, monkeypatch):
    from slidein_api.services.autopilot import set_switches
    from slidein_api.workers.runner import scheduler_tick
    from tests.conftest import TENANT_A

    await set_switches(TENANT_A, actor="test", enabled=True)
    monkeypatch.setenv("SLIDEIN_AUTOPILOT", "1")
    dispatched = []

    async def fake_dispatch(job_id):
        dispatched.append(job_id)
        return True

    monkeypatch.setattr("slidein_api.workers.dispatch.dispatch_job", fake_dispatch)
    outcome = await scheduler_tick()
    assert outcome["ready_tenants"] == 1
    assert outcome["dispatched"] == 1
    assert len(dispatched) == 1
