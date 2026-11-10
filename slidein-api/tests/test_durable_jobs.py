"""Hermetic durable execution tests; no Redis, provider, DNS, or mail IO."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from slidein_api.db import session_scope
from slidein_api.ids import new_id
from slidein_api.models import WorkJob, utcnow
from slidein_api.services.jobs import JobService
from slidein_api.workers.runner import execute_job
from tests.conftest import TENANT_A, TENANT_B
from tests.test_autopilot import fake_cli  # noqa: F401 — re-export the hermetic CLI fixture
from tests.test_setup_llm_intake import BUSINESS_CONTEXT

pytestmark = pytest.mark.usefixtures("_restore_key_store")


async def _enqueue(*, kind: str = "autopilot", max_attempts: int = 3) -> dict:
    async with session_scope() as session:
        return await JobService(session).enqueue(
            tenant_id=TENANT_A,
            kind=kind,
            idempotency_key=f"test:{new_id('work_job')}",
            payload={},
            max_attempts=max_attempts,
        )


@pytest.mark.asyncio
async def test_setup_job_automatically_enqueues_and_runs_research(
    client, operator_headers, monkeypatch
):
    monkeypatch.setenv("SLIDEIN_EXECUTION_MODE", "celery")
    dispatched = []

    async def fake_dispatch(job_id: str) -> bool:
        dispatched.append(job_id)
        return True

    monkeypatch.setattr("slidein_api.workers.dispatch.dispatch_job", fake_dispatch)
    response = client.post(
        f"/v1/tenants/{TENANT_A}/setup/intake",
        headers=operator_headers,
        json={"sources": [{"type": "notes", "text": BUSINESS_CONTEXT}]},
    )
    assert response.status_code == 200, response.text
    setup_job_id = response.json()["job"]["id"]
    assert client.get(
        f"/v1/tenants/{TENANT_A}/profile", headers=operator_headers
    ).json()["profile"] is None

    completed = await execute_job(setup_job_id, worker_id="setup-test")
    assert completed["status"] == "complete", completed
    from slidein_api.models import AutopilotState

    async with session_scope() as session:
        switches = await session.get(AutopilotState, TENANT_A)
        assert switches.enabled is True
        assert switches.auto_approve is False
        assert switches.send_enabled is False
        followup = (
            await session.execute(
                select(WorkJob).where(
                    WorkJob.tenant_id == TENANT_A,
                    WorkJob.kind == "autopilot",
                )
            )
        ).scalars().one()
        followup_id = followup.id
    assert followup_id in dispatched

    researched = []

    async def fake_tick(tenant_id, _cfg):
        researched.append(tenant_id)
        return {"status": "ok", "stats": {"researched": 0}}

    monkeypatch.setattr("slidein_api.workers.runner.autopilot_tick", fake_tick)
    outcome = await execute_job(followup_id, worker_id="research-test")
    assert outcome["status"] == "complete"
    assert researched == [TENANT_A]


@pytest.mark.asyncio
async def test_duplicate_worker_delivery_never_executes_twice(monkeypatch):
    job = await _enqueue()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def slow_tick(_tenant_id, _cfg):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"status": "ok", "stats": {}}

    monkeypatch.setattr("slidein_api.workers.runner.autopilot_tick", slow_tick)
    first = asyncio.create_task(execute_job(job["id"], worker_id="worker-a"))
    await asyncio.wait_for(started.wait(), timeout=2)
    duplicate = await execute_job(job["id"], worker_id="worker-b")
    assert duplicate["status"] == "running"
    release.set()
    assert (await first)["status"] == "complete"
    replay = await execute_job(job["id"], worker_id="worker-c")
    assert replay["status"] == "complete"
    assert calls == 1


@pytest.mark.asyncio
async def test_retry_backoff_and_dead_letter(monkeypatch):
    monkeypatch.setenv("SLIDEIN_JOB_BACKOFF_SECONDS", "1")
    job = await _enqueue(max_attempts=2)
    calls = 0

    async def failed_tick(_tenant_id, _cfg):
        nonlocal calls
        calls += 1
        return {"status": "failed", "error": "temporary_failure", "stats": {}}

    monkeypatch.setattr("slidein_api.workers.runner.autopilot_tick", failed_tick)
    first = await execute_job(job["id"], worker_id="worker-a")
    assert first["status"] == "retrying"
    assert first["job"]["attempts"] == 1

    early = await execute_job(job["id"], worker_id="worker-b")
    assert early["status"] == "retrying"
    assert calls == 1

    async with session_scope() as session:
        await session.execute(
            update(WorkJob)
            .where(WorkJob.id == job["id"])
            .values(run_at=utcnow() - timedelta(seconds=1))
        )
    second = await execute_job(job["id"], worker_id="worker-b")
    assert second["status"] == "dead_letter"
    assert second["job"]["attempts"] == 2
    assert calls == 2


@pytest.mark.asyncio
async def test_expired_worker_lease_recovers_after_restart(monkeypatch):
    job = await _enqueue()
    async with session_scope() as session:
        claimed = await JobService(session).claim(job["id"], worker_id="crashed-worker")
        assert claimed["status"] == "claimed"
        await session.execute(
            update(WorkJob)
            .where(WorkJob.id == job["id"])
            .values(lease_expires_at=utcnow() - timedelta(seconds=1))
        )
    async with session_scope() as session:
        recovered = await JobService(session).recover_expired()
        assert recovered == {"requeued": 1, "dead_letter": 0}

    calls = 0

    async def healthy_tick(_tenant_id, _cfg):
        nonlocal calls
        calls += 1
        return {"status": "ok", "stats": {}}

    monkeypatch.setattr("slidein_api.workers.runner.autopilot_tick", healthy_tick)
    outcome = await execute_job(job["id"], worker_id="replacement-worker")
    assert outcome["status"] == "complete"
    assert outcome["job"]["attempts"] == 2
    assert calls == 1


@pytest.mark.asyncio
async def test_only_the_live_worker_can_renew_its_lease():
    job = await _enqueue()
    previous_expiry = utcnow() + timedelta(seconds=5)
    async with session_scope() as session:
        service = JobService(session)
        claimed = await service.claim(job["id"], worker_id="live-worker")
        assert claimed["status"] == "claimed"
        await session.execute(
            update(WorkJob)
            .where(WorkJob.id == job["id"])
            .values(lease_expires_at=previous_expiry)
        )

    async with session_scope() as session:
        service = JobService(session)
        assert await service.heartbeat(job["id"], worker_id="stale-worker") is False
        assert await service.heartbeat(job["id"], worker_id="live-worker") is True
        renewed = await service.get(TENANT_A, job["id"])
        assert renewed["lease_expires_at"] > previous_expiry.isoformat()


@pytest.mark.asyncio
async def test_pause_cancels_pending_work_and_preserves_tenant_boundary(monkeypatch):
    job = await _enqueue()
    calls = 0

    async def forbidden_tick(_tenant_id, _cfg):
        nonlocal calls
        calls += 1
        return {"status": "ok", "stats": {}}

    monkeypatch.setattr("slidein_api.workers.runner.autopilot_tick", forbidden_tick)
    from slidein_api.services.autopilot import set_switches

    await set_switches(TENANT_A, actor="test", enabled=False)
    async with session_scope() as session:
        service = JobService(session)
        cancelled = await service.get(TENANT_A, job["id"])
        assert cancelled["state"] == "cancelled"
        with pytest.raises(Exception) as missing:
            await service.get(TENANT_B, job["id"])
        assert getattr(missing.value, "code", "") == "not_found"
    outcome = await execute_job(job["id"], worker_id="late-worker")
    assert outcome["status"] == "cancelled"
    assert calls == 0


@pytest.mark.asyncio
async def test_scheduler_is_idempotent_and_skips_unready_tenants(configured_workspace):
    from slidein_api.services.autopilot import set_switches

    await set_switches(TENANT_A, actor="test", enabled=True)
    moment = utcnow()
    async with session_scope() as session:
        service = JobService(session)
        first = await service.schedule_due_tenants(interval_seconds=300, now=moment)
        second = await service.schedule_due_tenants(interval_seconds=300, now=moment)
        assert len(first) == 1
        assert first[0]["tenant_id"] == TENANT_A
        assert [job["id"] for job in second] == [first[0]["id"]]
        due = await service.due_ids()
        assert first[0]["id"] in due
        assert all(job["tenant_id"] != TENANT_B for job in first + second)


def test_durable_control_routes_cancel_retry_and_isolate(
    configured_workspace, other_tenant_headers, monkeypatch
):
    monkeypatch.setenv("SLIDEIN_EXECUTION_MODE", "celery")

    async def fake_dispatch(_job_id: str) -> bool:
        return True

    monkeypatch.setattr("slidein_api.workers.dispatch.dispatch_job", fake_dispatch)
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    queued = client.post(f"/v1/tenants/{TENANT_A}/autopilot/run", headers=headers)
    assert queued.status_code == 200, queued.text
    job_id = queued.json()["job"]["id"]
    assert "payload" not in queued.json()["job"]
    forbidden = client.get(
        f"/v1/tenants/{TENANT_A}/autopilot/jobs/{job_id}", headers=other_tenant_headers
    )
    assert forbidden.status_code == 404

    cancelled = client.delete(
        f"/v1/tenants/{TENANT_A}/autopilot/jobs/{job_id}", headers=headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["state"] == "cancelled"
    retried = client.post(
        f"/v1/tenants/{TENANT_A}/autopilot/jobs/{job_id}/retry", headers=headers
    )
    assert retried.status_code == 200
    assert retried.json()["job"]["state"] == "queued"

    paused = client.post(
        f"/v1/tenants/{TENANT_A}/autopilot", json={"enabled": False}, headers=headers
    )
    assert paused.status_code == 200
    final = client.get(
        f"/v1/tenants/{TENANT_A}/autopilot/jobs/{job_id}", headers=headers
    )
    assert final.json()["job"]["state"] == "cancelled"


@pytest.mark.asyncio
async def test_replayed_worker_job_cannot_double_send(
    fake_cli, configured_workspace, tmp_path, monkeypatch
):
    """A real dry-run pipeline executes once even if Celery replays the job."""
    from slidein_api.models import SentMessage
    from tests.conftest import prospect_records
    from tests.test_autopilot import _write_csv

    csv_path = _write_csv(tmp_path / "durable-leads.csv", prospect_records(1))
    monkeypatch.setenv("SLIDEIN_AUTOPILOT_INGEST", str(csv_path))
    monkeypatch.setenv("SLIDEIN_AUTOPILOT_CONNECTOR", "openosint")
    monkeypatch.delenv("SLIDEIN_TRANSPORT", raising=False)
    from slidein_api.services.autopilot import set_switches

    await set_switches(
        TENANT_A, actor="test", enabled=True, auto_approve=True, send_enabled=True
    )
    job = await _enqueue()
    first = await execute_job(job["id"], worker_id="worker-a")
    replay = await execute_job(job["id"], worker_id="worker-b")
    assert first["status"] == "complete"
    assert replay["status"] == "complete"
    tick = first["job"]["result"]["tick"]
    assert tick["status"] == "ok", tick
    assert tick["stats"].get("sent", 0) == 1, tick
    async with session_scope() as session:
        sent_count = len(
            (
                await session.execute(
                    select(SentMessage).where(SentMessage.tenant_id == TENANT_A)
                )
            ).scalars().all()
        )
    assert sent_count == 1
