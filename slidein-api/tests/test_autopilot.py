"""Autopilot: the autonomous background agent loop.

The loop is tested the way it runs in production — real services, real
StageRunner, real gates — with the OpenOSINT CLI replaced by the same
deterministic stub the OSINT tests use, and the transport left at its
env default (`dry_run`) so nothing touches a socket.

Covered: ingest → research → qualify → personalize → approve → send in
one tick; idempotence on the next tick; per-workspace switches; the
suppression gate; the control-plane endpoints; and the KumoMTA-aware
transport resolution.
"""

from __future__ import annotations

import csv
import stat
from pathlib import Path

import pytest

from tests.conftest import TENANT_A, prospect_records

pytestmark = pytest.mark.usefixtures("_restore_key_store")

FAKE_CLI = '''#!/usr/bin/env python3
import json, sys

if any(a in ("--help", "-h") for a in sys.argv[1:]):
    print("usage: openosint [options] command ...")
    sys.exit(0)

args = [a for a in sys.argv[1:] if not a.startswith("-")]
if len(args) < 2:
    print("usage: openosint --json <tool> <target>", file=sys.stderr)
    sys.exit(2)
tool, target = args[0], args[1]

if tool == "exposure":
    print(json.dumps({
        "domain": target, "grade": "B", "score": 82,
        "score_is_partial": False,
        "checks": {"tls": {"status": "ok", "reason": None}},
        "findings": [],
    }))
    sys.exit(0)

FIXTURES = {
    "dns": ["[DNS] Domain: {t}", "[DNS] SPF: v=spf1 -all"],
    # Bio carries the ICP's required signals so qualification can match.
    "github": ["[GitHub] Login: {t}",
               "[GitHub] Bio: Kubernetes and cloud cost platform lead",
               "[GitHub] Profile URL: https://github.com/{t}"],
}
lines = [line.format(t=target) for line in FIXTURES.get(tool, ["[unknown tool]"])]
print(json.dumps({
    "tool": tool, "target": target, "results": lines, "error": None,
}))
'''


def _cfg(**overrides) -> "AutopilotConfig":
    from slidein_api.services.autopilot import AutopilotConfig

    base = dict(
        master_enabled=True,
        interval_seconds=300,
        batch=10,
        max_sends=5,
        ingest_paths=(),
        connector_chain=("openosint",),
    )
    base.update(overrides)
    return AutopilotConfig(**base)


@pytest.fixture()
def fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = tmp_path / "fake-openosint"
    path.write_text(FAKE_CLI)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("OPENOSINT_CLI", str(path))
    monkeypatch.setenv("SLIDEIN_AUTOPILOT", "1")
    for var in (
        "SLIDEIN_TRANSPORT", "SLIDEIN_SMTP_HOST", "SLIDEIN_SMTP_PASS",
        "KUMO_HOST", "KUMO_AUTH_PASS", "SLIDEIN_AUTOPILOT_INGEST",
    ):
        monkeypatch.delenv(var, raising=False)
    return str(path)


def _write_csv(path: Path, records: list[dict]) -> Path:
    fields = [
        "first_name", "last_name", "email", "company_name",
        "company_domain", "job_title", "company_size", "location",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({k: row.get(k, "") for k in fields})
    return path


# ---------------------------------------------------------------------------
# Control plane
# ---------------------------------------------------------------------------


def test_status_reports_defaults_for_a_configured_workspace(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    response = client.get(f"/v1/tenants/{TENANT_A}/autopilot", headers=headers)
    assert response.status_code == 200, response.text
    status = response.json()
    assert status["enabled"] is True
    assert status["master_enabled"] is True
    assert status["transport"] == "dry_run"
    assert status["last_status"] == "never_run"
    assert status["pipeline"]["discovered"] == 0
    assert status["connector_chain"] == ["openosint", "website"]


def test_toggle_and_run_endpoints(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]

    off = client.post(
        f"/v1/tenants/{TENANT_A}/autopilot",
        json={"enabled": False},
        headers=headers,
    )
    assert off.status_code == 200, off.text
    assert off.json()["enabled"] is False

    run = client.post(f"/v1/tenants/{TENANT_A}/autopilot/run", headers=headers)
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["tick"]["status"] == "workspace_disabled"

    client.post(
        f"/v1/tenants/{TENANT_A}/autopilot",
        json={"enabled": True, "auto_approve": False},
        headers=headers,
    )
    status = client.get(f"/v1/tenants/{TENANT_A}/autopilot", headers=headers).json()
    assert status["enabled"] is True
    assert status["auto_approve"] is False


def test_viewer_cannot_configure_autopilot(configured_workspace):
    client = configured_workspace["client"]
    response = client.post(
        f"/v1/tenants/{TENANT_A}/autopilot",
        json={"enabled": False},
        headers={"X-API-Key": "sk_alpha_viewer_0001"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# The full autonomous journey
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_tick_runs_the_whole_loop(fake_cli, configured_workspace, tmp_path):
    from slidein_api.services.autopilot import status_payload, tick

    csv_path = _write_csv(tmp_path / "leads.csv", prospect_records(1))
    outcome = await tick(TENANT_A, _cfg(ingest_paths=(str(csv_path),)))
    assert outcome["status"] == "ok", outcome
    stats = outcome["stats"]
    assert stats["ingested"] == 1
    assert stats["researched"] == 1
    assert stats["qualified"] == 1
    assert stats["drafts"] == 1
    assert stats["approved"] == 1
    assert stats["sent"] == 1

    # Everything is visible through the dashboard's own endpoints.
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    prospects = client.get(
        f"/v1/tenants/{TENANT_A}/prospects", headers=headers
    ).json()["data"]
    assert [p["status"] for p in prospects] == ["in_campaign"]

    drafts = client.get(
        f"/v1/tenants/{TENANT_A}/drafts", headers=headers
    ).json()["data"]
    assert drafts[0]["status"] == "sent"
    assert drafts[0]["approved_by"] == "service:autopilot"

    sent = client.get(f"/v1/tenants/{TENANT_A}/sent", headers=headers).json()["data"]
    assert sent[0]["transport"] == "dry_run"
    assert sent[0]["delivery_status"] == "submitted"

    status = await status_payload(TENANT_A)
    assert status["totals"]["sent"] == 1
    assert status["last_status"] == "ok"
    assert status["pipeline"]["in_campaign"] == 1
    assert status["drafts"]["sent"] == 1

    # Activity trail (what the Activity page renders) carries the runs.
    activity = client.get(
        f"/v1/tenants/{TENANT_A}/activity", headers=headers
    ).json()["data"]
    actors = {row["actor"] for row in activity}
    assert "service:autopilot" in actors

    # A second tick must not re-ingest, re-send, or advance anything.
    second = await tick(TENANT_A, _cfg(ingest_paths=(str(csv_path),)))
    assert second["status"] == "ok"
    assert second["stats"].get("ingested", 0) == 0
    assert second["stats"].get("sent", 0) == 0
    assert second["stats"].get("ingest_duplicates", 0) == 1


@pytest.mark.asyncio
async def test_workspace_switches_gate_the_loop(fake_cli, configured_workspace, tmp_path):
    from slidein_api.services.autopilot import set_switches, tick

    csv_path = _write_csv(tmp_path / "leads.csv", prospect_records(1))

    # Sending off: the loop still researches/qualifies/drafts/approves.
    await set_switches(TENANT_A, actor="test", send_enabled=False)
    outcome = await tick(TENANT_A, _cfg(ingest_paths=(str(csv_path),)))
    assert outcome["stats"]["drafts"] == 1
    assert outcome["stats"]["approved"] == 1
    assert outcome["stats"].get("sent", 0) == 0

    # Auto-approve off (sending still off): the next draft parks for a human.
    await set_switches(TENANT_A, actor="test", auto_approve=False)
    parked_record = dict(
        prospect_records(1)[0],
        email="parked@cloudwave9.example",
        first_name="Parked",
        last_name="Prospect",
        company_name="ParkedCo",
        company_domain="parkedco.example",
    )
    second_csv = _write_csv(tmp_path / "leads2.csv", [parked_record])
    for _ in range(2):
        await tick(TENANT_A, _cfg(ingest_paths=(str(second_csv),)))
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    drafts = client.get(
        f"/v1/tenants/{TENANT_A}/drafts", headers=headers
    ).json()["data"]
    by_status = {d["id"]: d["status"] for d in drafts}
    assert "pending_review" in by_status.values()
    assert "approved" in by_status.values()  # the first, send-blocked one
    parked = next(d for d in drafts if d["status"] == "pending_review")
    assert parked["approved_by"] in (None, "")


@pytest.mark.asyncio
async def test_suppression_blocks_the_send_step(fake_cli, configured_workspace, tmp_path):
    from slidein_api.services.autopilot import tick
    from slidein_api.db import session_scope
    from slidein_api.services.suppression import SuppressionService

    records = prospect_records(1)
    async with session_scope() as session:
        await SuppressionService(session).add(
            tenant_id=TENANT_A, email=records[0]["email"],
            reason="opt_out", actor="test",
        )

    csv_path = _write_csv(tmp_path / "leads.csv", records)
    outcome = await tick(TENANT_A, _cfg(ingest_paths=(str(csv_path),)))
    assert outcome["status"] == "ok"
    assert outcome["stats"]["drafts"] == 1
    assert outcome["stats"].get("sent", 0) == 0
    assert outcome["stats"].get("send_failed", 0) == 1


@pytest.mark.asyncio
async def test_ingest_without_configuration_reports_blocked(tmp_path, monkeypatch):
    """A bare workspace (no ICP/profile) must not crash the loop."""
    from slidein_api.services.autopilot import tick
    from tests.conftest import TENANT_B

    csv_path = _write_csv(tmp_path / "leads.csv", prospect_records(1))
    outcome = await tick(TENANT_B, _cfg(ingest_paths=(str(csv_path),)))
    # Tenant B has no workspace config: either blocked ingest or an empty
    # advance — never an exception.
    assert outcome["status"] in ("ok", "blocked")
    if outcome["status"] == "ok":
        assert outcome["stats"].get("ingested", 0) == 0


def test_csv_reader_skips_rows_without_email(tmp_path):
    from slidein_api.services.autopilot import _read_csv_records

    path = _write_csv(tmp_path / "leads.csv", prospect_records(1))
    with path.open("a", encoding="utf-8") as fh:
        fh.write(",NoEmail,,,Bad Co,,,,\n")
    records, skipped = _read_csv_records(path)
    assert len(records) == 1
    assert skipped == 1


# ---------------------------------------------------------------------------
# Transport resolution (KumoMTA integration)
# ---------------------------------------------------------------------------


def test_transport_defaults_to_dry_run(monkeypatch):
    from slidein_api.services.transport import get_transport

    monkeypatch.delenv("SLIDEIN_TRANSPORT", raising=False)
    assert get_transport({}).name == "dry_run"


def test_transport_kumo_falls_back_to_kumomta_submission(monkeypatch):
    from slidein_api.services.transport import env_transport_config, get_transport

    monkeypatch.setenv("SLIDEIN_TRANSPORT", "kumo")
    monkeypatch.delenv("SLIDEIN_SMTP_HOST", raising=False)
    monkeypatch.delenv("KUMO_HOST", raising=False)
    cfg = env_transport_config()
    assert cfg["transport"] == "kumo"
    assert cfg["smtp_host"] == "127.0.0.1"
    assert cfg["smtp_port"] == 2587
    assert cfg["smtp_username"] == "outbound"
    transport = get_transport({})
    assert transport.name == "smtp"  # kumo rides the SMTP transport
    assert transport.host == "127.0.0.1"
    assert transport.port == 2587


def test_explicit_payload_config_beats_env(monkeypatch):
    from slidein_api.services.transport import get_transport

    monkeypatch.setenv("SLIDEIN_TRANSPORT", "kumo")
    transport = get_transport(
        {"transport": "dry_run", "smtp_host": "elsewhere", "smtp_port": 2525}
    )
    assert transport.name == "dry_run"
