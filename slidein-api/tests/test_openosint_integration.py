"""OpenOSINT integration: adapter, service, routes and research connector.

The CLI is never actually run against the network — `fake_cli` points
`OPENOSINT_CLI` at a stub that speaks the real `openosint --json` schema
(`{tool, target, timestamp, results, error}`), so every path (parsing,
gating, persistence, API contract) is deterministic.
"""

from __future__ import annotations

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
    # The exposure tool prints a report document, not the standard envelope.
    print(json.dumps({
        "domain": target,
        "registrable_domain": target,
        "checked_at": "2026-01-01T00:00:00+00:00",
        "duration_ms": 500,
        "grade": "B",
        "score": 82,
        "score_is_partial": False,
        "checks": {
            "email": {"status": "ok", "reason": None},
            "tls": {"status": "warn", "reason": "cert expires in 12 days"},
        },
        "findings": [
            {"id": "dmarc_no_rua", "severity": "low", "title": "DMARC has no aggregate report address"},
        ],
    }))
    sys.exit(0)

FIXTURES = {
    "dns": ["[DNS] Domain: {t}", "\\u001b[H\\u001b[J[DNS] A: 203.0.113.10", "[DNS] SPF: v=spf1 -all"],
    "github": ["[GitHub] Login: {t}", "[GitHub] Name: CloudWave"],
    "email": ["[+] registered-site.example"],
    "username": ["[+] twitter.com", "[+] github.com"],
}
lines = [line.format(t=target) for line in FIXTURES.get(tool, ["[unknown tool]"])]
print(json.dumps({
    "tool": "search_" + tool,
    "target": target,
    "timestamp": "2026-01-01T00:00:00+00:00",
    "results": lines,
    "error": None,
}))
'''


@pytest.fixture()
def fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point OPENOSINT_CLI at a deterministic stub of the real CLI."""
    path = tmp_path / "fake-openosint"
    path.write_text(FAKE_CLI)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("OPENOSINT_CLI", str(path))
    monkeypatch.delenv("OPENOSINT_ALLOW_ACTIVE", raising=False)
    return str(path)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_runs_lookups_and_parses_json(fake_cli):
    from slidein_api.integrations.openosint import OpenOSINTAdapter

    results = await OpenOSINTAdapter().run_lookups(
        {"dns": "cloudwave0.example", "github": "CloudWave 0"},
        ["dns", "github"],
    )
    by_name = {r.lookup: r for r in results}
    assert by_name["dns"].ok
    assert by_name["dns"].lines[0] == "[DNS] Domain: cloudwave0.example"
    # ANSI escape sequences (holehe-style terminal repaints) are stripped.
    assert by_name["dns"].lines[1] == "[DNS] A: 203.0.113.10"
    assert not any("\x1b" in line for line in by_name["dns"].lines)
    assert by_name["dns"].duration_ms >= 0
    assert by_name["github"].ok
    assert by_name["github"].summary()["lines"] == 2


@pytest.mark.asyncio
async def test_adapter_parses_exposure_report_schema(fake_cli):
    """`exposure` prints a report document, not the {results: [...]} envelope."""
    from slidein_api.integrations.openosint import OpenOSINTAdapter

    (result,) = await OpenOSINTAdapter().run_lookups(
        {"exposure": "cloudwave0.example"}, ["exposure"]
    )
    assert result.ok
    assert result.lines[0] == "[exposure] cloudwave0.example grade B score 82"
    assert "[exposure] check email: ok" in result.lines
    assert "[exposure] check tls: warn (cert expires in 12 days)" in result.lines
    assert (
        "[exposure] low: DMARC has no aggregate report address" in result.lines
    )


def test_adapter_enrich_reports_missing_cli():
    from slidein_api.errors import ValidationError
    from slidein_api.integrations.openosint import OpenOSINTAdapter

    outcome = OpenOSINTAdapter(cli="/nonexistent/openosint").enrich(domain="example.com")
    assert outcome["succeeded"] == []
    assert set(outcome["failed"]) == {"dns", "exposure"}
    assert all("OPENOSINT_CLI" in item["error"] for item in outcome["lookups"])

    with pytest.raises(ValidationError):
        OpenOSINTAdapter(cli="/nonexistent/openosint").enrich()


@pytest.mark.asyncio
async def test_active_lookups_gated_without_opt_in(fake_cli):
    from slidein_api.integrations.openosint import OpenOSINTAdapter

    adapter = OpenOSINTAdapter()
    (blocked,) = await adapter.run_lookups(
        {"email": "vp@cloudwave0.example"}, ["email"], allow_active=False
    )
    assert not blocked.ok
    assert "allow_active" in blocked.error

    (allowed,) = await adapter.run_lookups(
        {"email": "vp@cloudwave0.example"}, ["email"], allow_active=True
    )
    assert allowed.ok
    assert allowed.lines == ["[+] registered-site.example"]


@pytest.mark.asyncio
async def test_adapter_rejects_unknown_lookup(fake_cli):
    from slidein_api.errors import ValidationError
    from slidein_api.integrations.openosint import OpenOSINTAdapter

    with pytest.raises(ValidationError):
        await OpenOSINTAdapter().run_lookups({}, ["telepathy"])


def test_adapter_health_reports_connected_and_missing_cli(fake_cli):
    from slidein_api.integrations.openosint import OpenOSINTAdapter

    assert OpenOSINTAdapter().health().status.value == "connected"
    missing = OpenOSINTAdapter(cli="/nope/openosint").health()
    assert missing.status.value == "disconnected"
    assert "OPENOSINT_CLI" in missing.detail


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def test_targets_map_lookup_to_prospect_fields():
    from slidein_api.models import Prospect
    from slidein_api.services.osint import targets_for

    prospect = Prospect(
        id="prosp_test",
        tenant_id=TENANT_A,
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.org",
        company_name="Analytical Engines",
        company_domain="example.org",
        linkedin_url="https://linkedin.com/in/ada-lovelace",
        source="test",
    )
    targets = targets_for(prospect, ["dns", "exposure", "github", "email", "username"])
    assert targets == {
        "dns": "example.org",
        "exposure": "example.org",
        "github": "Ada Lovelace",
        "email": "ada@example.org",
        "username": "ada-lovelace",
    }

    # Email-derived domain when the record has no company domain.
    bare = Prospect(
        id="prosp_bare",
        tenant_id=TENANT_A,
        email="ops@acme.example",
        source="test",
    )
    assert targets_for(bare, ["dns", "github"]) == {"dns": "acme.example"}


@pytest.mark.asyncio
async def test_service_persists_osint_evidence(fake_cli):
    from slidein_api.db import session_scope
    from slidein_api.ids import new_id
    from slidein_api.models import Prospect
    from slidein_api.services.config import ConfigService
    from slidein_api.services.osint import OSINTService

    async with session_scope() as session:
        await ConfigService(session).ensure_tenant(TENANT_A)
        prospect = Prospect(
            id=new_id("prospect"),
            tenant_id=TENANT_A,
            first_name="Prospect0",
            last_name="Tester0",
            email="prospect0@cloudwave0.example",
            company_name="CloudWave 0",
            company_domain="cloudwave0.example",
            source="test",
        )
        session.add(prospect)
        await session.flush()

        result = await OSINTService(session).enrich_prospect(
            tenant_id=TENANT_A,
            prospect=prospect,
            lookups=["dns", "github"],
            actor="tester",
        )
        rows = await OSINTService(session).list_evidence(TENANT_A, prospect.id)

    assert result["evidence_count"] == 2
    assert result["verified_count"] == 2
    assert {row["collector"] for row in rows} == {"openosint:dns", "openosint:github"}
    dns_row = next(row for row in rows if row["collector"] == "openosint:dns")
    assert dns_row["source_url"] == "https://cloudwave0.example"
    assert dns_row["claim_text"].startswith("[openosint dns] cloudwave0.example")
    assert dns_row["verification_status"] == "verified"
    assert dns_row["retrieved_by"] == "tester"


@pytest.mark.asyncio
async def test_service_rejects_unknown_lookup(fake_cli):
    from slidein_api.errors import ValidationError
    from slidein_api.db import session_scope
    from slidein_api.ids import new_id
    from slidein_api.models import Prospect
    from slidein_api.services.config import ConfigService
    from slidein_api.services.osint import OSINTService

    async with session_scope() as session:
        await ConfigService(session).ensure_tenant(TENANT_A)
        prospect = Prospect(
            id=new_id("prospect"),
            tenant_id=TENANT_A,
            email="x@cloudwave0.example",
            company_domain="cloudwave0.example",
            source="test",
        )
        session.add(prospect)
        await session.flush()
        with pytest.raises(ValidationError):
            await OSINTService(session).enrich_prospect(
                tenant_id=TENANT_A, prospect=prospect, lookups=["telepathy"]
            )


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


def test_api_osint_enrichment_and_readback(configured_workspace, fake_cli):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1)},
        headers=headers,
    ).json()
    prospect_id = discover["outputs"]["prospect_ids"][0]

    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/osint",
        json={"lookups": ["dns", "github"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    outcome = response.json()
    assert outcome["collector"] == "openosint"
    assert outcome["evidence_count"] == 2
    assert all(item["ok"] for item in outcome["lookups"])

    readback = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/osint",
        headers=headers,
    ).json()
    assert readback["count"] == 2
    assert {row["collector"] for row in readback["evidence"]} == {
        "openosint:dns",
        "openosint:github",
    }

    shared = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/evidence",
        headers=headers,
    ).json()["evidence"]
    assert len(shared) == 2


def test_api_osint_active_lookup_stays_gated(configured_workspace, fake_cli):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1)},
        headers=headers,
    ).json()
    prospect_id = discover["outputs"]["prospect_ids"][0]

    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/osint",
        json={"lookups": ["dns", "email"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    outcome = response.json()
    by_name = {item["lookup"]: item for item in outcome["lookups"]}
    assert by_name["dns"]["ok"] is True
    assert by_name["email"]["ok"] is False
    assert "allow_active" in by_name["email"]["error"]
    assert outcome["evidence_count"] == 1  # only the dns claim was filed

    opted_in = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/osint",
        json={"lookups": ["email"], "allow_active": True},
        headers=headers,
    )
    assert opted_in.status_code == 200, opted_in.text
    assert opted_in.json()["evidence_count"] == 1
    assert opted_in.json()["lookups"][0]["ok"] is True


def test_api_osint_rejects_unknown_lookup(configured_workspace, fake_cli):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1)},
        headers=headers,
    ).json()
    prospect_id = discover["outputs"]["prospect_ids"][0]

    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/osint",
        json={"lookups": ["telepathy"]},
        headers=headers,
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "prospect_invalid"
    assert "dns" in error["details"]["allowed"]


def test_api_osint_requires_operator_role(configured_workspace, viewer_headers, fake_cli):
    client = configured_workspace["client"]
    admin = configured_workspace["headers"]
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1)},
        headers=admin,
    ).json()
    prospect_id = discover["outputs"]["prospect_ids"][0]

    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/osint",
        json={"lookups": ["dns"]},
        headers=viewer_headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authorized"


def test_api_osint_unknown_prospect_is_404(configured_workspace, fake_cli):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/prosp_missing/osint",
        json={"lookups": ["dns"]},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "prospect_not_found"


def test_osint_health_endpoint(client, admin_headers, fake_cli):
    response = client.get("/v1/osint/health", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "connected"
    assert body["adapter"] == "openosint"
    assert {"dns", "exposure", "github", "email", "username"} <= {
        entry["name"] for entry in body["lookups"]
    }


# ---------------------------------------------------------------------------
# Research stage integration (connector = "openosint")
# ---------------------------------------------------------------------------


def test_research_stage_runs_openosint_connector(configured_workspace, fake_cli):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1)},
        headers=headers,
    ).json()
    prospect_id = discover["outputs"]["prospect_ids"][0]

    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/research",
        json={"connector": "openosint"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    outcome = response.json()
    assert outcome["status"] == "succeeded"
    # Passive default set: dns + exposure + github.
    assert outcome["outputs"]["evidence_count"] == 3
    assert outcome["outputs"]["verified_count"] == 3
    assert outcome["outputs"]["collector"] == "openosint"
    assert outcome["to_status"] == "researched"

    evidence = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/evidence",
        headers=headers,
    ).json()["evidence"]
    assert len(evidence) == 3
    assert all(row["collector"].startswith("openosint:") for row in evidence)


# ---------------------------------------------------------------------------
# Ad-hoc research (no prospect record)
# ---------------------------------------------------------------------------


def test_detect_target_type_and_dorks():
    from urllib.parse import unquote

    from slidein_api.services.osint import (
        default_lookups_for,
        detect_target_type,
        dorks_for,
        query_targets,
    )

    assert detect_target_type("jane@acme.example") == "email"
    assert detect_target_type("acme.example") == "domain"
    assert detect_target_type("jdoe42") == "handle"
    assert detect_target_type("Sanjida Nasrin Efa") == "name"
    assert detect_target_type("") == "name"

    assert default_lookups_for("email") == ("email", "username")
    assert default_lookups_for("domain") == ("dns", "exposure")
    assert default_lookups_for("handle") == ("github", "username")
    assert default_lookups_for("name") == ("github",)

    email_targets = query_targets("ops@acme.example", "email")
    assert email_targets["email"] == "ops@acme.example"
    assert email_targets["username"] == "ops"
    assert email_targets["dns"] == "acme.example"
    assert query_targets("jdoe42", "handle") == {"github": "jdoe42", "username": "jdoe42"}

    dorks = dorks_for("Jane Doe")
    assert len(dorks) == 12
    assert dorks[1]["label"] == "LinkedIn"
    assert dorks[0]["url"].startswith("https://www.google.com/search?q=")
    assert "site%3Alinkedin.com" in unquote(dorks[1]["url"]).replace(" ", "%20") or (
        "site:linkedin.com" in unquote(dorks[1]["url"])
    )


def test_api_ad_hoc_research_by_name(configured_workspace, fake_cli):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    response = client.post(
        f"/v1/tenants/{TENANT_A}/osint/research",
        json={"query": "Sanjida Nasrin Efa"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["query"] == "Sanjida Nasrin Efa"
    assert body["target_type"] == "name"
    assert body["targets"] == {"github": "Sanjida Nasrin Efa"}
    assert body["lookups"][0]["ok"] is True
    assert body["succeeded"] == ["github"]
    assert len(body["dorks"]) == 12


def test_api_ad_hoc_research_email_gate_and_optin(configured_workspace, fake_cli):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    path = f"/v1/tenants/{TENANT_A}/osint/research"

    gated = client.post(path, json={"query": "vp@cloudwave0.example"}, headers=headers)
    assert gated.status_code == 200, gated.text
    body = gated.json()
    assert body["target_type"] == "email"
    assert body["failed"] == ["email", "username"]
    assert all("allow_active" in row["error"] for row in body["lookups"])
    assert body["dorks"], "dorks are returned even when lookups are gated"

    opted = client.post(
        path,
        json={"query": "vp@cloudwave0.example", "allow_active": True},
        headers=headers,
    )
    assert opted.status_code == 200, opted.text
    assert opted.json()["succeeded"] == ["email", "username"]


def test_api_ad_hoc_research_validation_and_roles(
    configured_workspace, viewer_headers, fake_cli
):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    path = f"/v1/tenants/{TENANT_A}/osint/research"

    missing = client.post(path, json={}, headers=headers)
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "prospect_invalid"

    unknown = client.post(
        path, json={"query": "acme.example", "lookups": ["telepathy"]}, headers=headers
    )
    assert unknown.status_code == 400

    no_target = client.post(
        path, json={"query": "Jane Doe", "lookups": ["dns"]}, headers=headers
    )
    assert no_target.status_code == 200
    assert no_target.json()["lookups"][0]["ok"] is False
    assert "no target" in no_target.json()["lookups"][0]["error"]

    forbidden = client.post(path, json={"query": "Jane Doe"}, headers=viewer_headers)
    assert forbidden.status_code == 403
