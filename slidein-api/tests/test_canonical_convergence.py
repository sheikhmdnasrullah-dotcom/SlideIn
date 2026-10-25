"""Canonical convergence invariants: seven stable sections, total capability
projection, synthesize reconciliation, and approval-required adaptations."""

from __future__ import annotations

import os

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SLIDEIN_AUTH_MODE", "disabled")
    os.environ["SLIDEIN_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/c.db"
    from starlette.testclient import TestClient
    from slidein_api.api.app import app
    with TestClient(app) as c:
        yield c


def test_seven_stable_sections():
    from slidein_api.canonical import SEVEN_SECTIONS, SECTION_CAPABILITIES
    assert SEVEN_SECTIONS == ("overview", "business_setup", "prospects_research",
                              "outreach", "conversations", "activity", "settings")
    # every catalog module maps to exactly one section (projection is total)
    from product.core.capabilities import CAPABILITY_CATALOG
    catalog = {m.module_id for m in CAPABILITY_CATALOG}
    mapped = {m for mods in SECTION_CAPABILITIES.values() for m in mods}
    assert mapped <= catalog, f"unknown module in mapping: {mapped - catalog}"
    assert catalog - mapped == set(), f"unmapped modules: {catalog - mapped}"


def test_navigation_projection_hides_disabled():
    from slidein_api.canonical import project_navigation
    nav = project_navigation(["overview", "research", "settings"])
    by_id = {s["section"]: s for s in nav}
    assert by_id["overview"]["visible"] and by_id["settings"]["visible"]
    assert by_id["outreach"]["modules"] == [] and not by_id["outreach"]["visible"]
    assert by_id["prospects_research"]["modules"] == ["research"]
    assert len(nav) == 7


def test_synthesize_reconciled_not_deleted():
    from slidein_api.canonical import assert_canonical_flow
    # legacy eighth stage validates by mapping onto converse (§9.1)
    assert assert_canonical_flow(("research", "synthesize")) == ("research", "converse")
    from product.core.flow import FlowViolation
    with pytest.raises(FlowViolation):
        assert_canonical_flow(("research", "quantum_stage"))


def test_adaptations_require_approval(client):
    for _ in range(3):
        client.post("/v1/workspace/evidence", json={
            "kind": "behavior", "fact": "user opened research module daily",
            "verified": True, "confidence": 0.9})
    r = client.post("/v1/workspace/adapt", json={"rationale": "research use"})
    assert r.status_code == 200
    pid = r.json()["proposal_id"]
    # §3.4: no auto-apply bypass — apply before approval must fail closed
    r = client.post(f"/v1/workspace/proposals/{pid}/apply", json={"auto_apply": True})
    assert r.status_code == 403, r.text
    # approve, then apply succeeds
    from slidein_api.api.routes.workspace import _proposal_ledger
    from product.core.workspace import ProposalStatus
    ledger = next(l for l in _proposal_ledger.values() if pid in l)
    entry = ledger[pid]
    ledger[pid] = {**entry, "status": ProposalStatus.APPROVED.value}
    r = client.post(f"/v1/workspace/proposals/{pid}/apply", json={})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2


def test_config_endpoint_projects_sections(client):
    d = client.get("/v1/workspace/config").json()
    assert "sections" in d and len(d["sections"]) == 7
    assert [s["section"] for s in d["sections"]][0] == "overview"
