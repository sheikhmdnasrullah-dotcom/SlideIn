"""Acceptance: one-shot client setup from raw context.

A transcript + notes produce a structured profile (confirmed vs inferred,
source refs), a validated persisted workspace, a universal-flow first
workflow, and an honest readiness state — surviving a process restart.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SLIDEIN_AUTH_MODE", "disabled")
    monkeypatch.setenv("SLIDEIN_DATABASE_URL",
                       f"sqlite+aiosqlite:///{tmp_path}/setup.db")
    os.environ["SLIDEIN_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/setup.db"
    from starlette.testclient import TestClient
    from slidein_api.api.app import app
    with TestClient(app) as c:
        c.headers.update({"X-Slidein-Tenant": "ten_setup"})
        yield c, tmp_path


TRANSCRIPT = """
We are BrightPath Mortgage, a mortgage company based in Austin.
We offer first-time homebuyer loans and refinancing.
Our ideal clients are first-time buyers with steady income in the Austin area.
Our goal is to book 20 loan consultations per month.
We use Salesforce as our CRM.
Nothing sends without my approval.
"""


def test_setup_happy_path(client):
    c, _ = client
    r = c.post("/v1/setup/client", json={
        "materials": [{"source_ref": "call-2026-10-26.txt", "text": TRANSCRIPT}],
    })
    assert r.status_code == 200, r.text
    d = r.json()

    # profile: confirmed facts with provenance
    assert d["profile"]["business_name"] == "BrightPath Mortgage"
    assert "first-time homebuyer loans" in " ".join(d["profile"]["offers"]).lower()
    assert d["profile"]["sources"] == ["call-2026-10-26.txt"]
    assert d["profile"]["missing"] == []  # name, offers, icp all confirmed

    # workspace: generated, validated, versioned; only real modules
    assert d["workspace"]["version"] >= 2
    order = d["workspace"]["module_order"]
    assert "overview" in order and "research" in order and "approvals" in order
    assert all(m in ("overview", "knowledge", "research", "contacts", "workflows",
                     "approvals", "analytics", "integrations", "agents",
                     "settings") for m in order)

    # first workflow: universal-flow stages only, approval-gated
    assert d["first_workflow"]["steps"] == [
        "discover", "research", "qualify", "personalize", "outreach"]
    assert d["first_workflow"]["approval_gate"] is True

    # readiness: integration named -> honest pending state + blocker, not fake
    assert d["readiness"]["state"] == "integrations_pending"
    assert any("Salesforce" in b for b in d["readiness"]["blockers"])
    assert d["readiness"]["questions"] == []

    # status endpoint reflects it
    r = c.get("/v1/setup/status")
    assert r.json()["state"] == "integrations_pending"


def test_setup_survives_restart(tmp_path):
    """True process restarts: phase 1 sets up, phase 2 (new process, same
    instance DB) must see the persisted workspace and recover it."""
    import subprocess
    import sys

    db = f"sqlite+aiosqlite:///{tmp_path}/setup.db"
    base = os.path.dirname(os.path.dirname(__file__))
    env = {**os.environ, "SLIDEIN_AUTH_MODE": "disabled",
           "SLIDEIN_DATABASE_URL": db}

    phase1 = (
        "import os;"
        f"os.environ['SLIDEIN_DATABASE_URL']='{db}';"
        "os.environ['SLIDEIN_AUTH_MODE']='disabled';"
        "from starlette.testclient import TestClient;"
        "from slidein_api.api.app import app;"
        "c = TestClient(app); c.__enter__();"
        "r = c.post('/v1/setup/client', json={'notes': 'We are Acme Consulting. "
        "We offer growth audits. Our ideal clients are B2B SaaS founders.'});"
        "assert r.status_code == 200, r.text;"
        "assert c.get('/v1/setup/status').json()['state'] == 'ready';"
        "print('PHASE1-OK')"
    )
    out1 = subprocess.run([sys.executable, "-c", phase1], capture_output=True,
                          text=True, cwd=base, env=env)
    assert "PHASE1-OK" in out1.stdout, out1.stderr[-600:]

    phase2 = (
        "import os;"
        f"os.environ['SLIDEIN_DATABASE_URL']='{db}';"
        "os.environ['SLIDEIN_AUTH_MODE']='disabled';"
        "from starlette.testclient import TestClient;"
        "from slidein_api.api.app import app;"
        "c = TestClient(app); c.__enter__();"
        "s = c.get('/v1/setup/status').json();"
        "assert s['state'] == 'ready', s;"
        "cfg = c.get('/v1/workspace/config').json();"
        "assert cfg['version'] == 2, cfg;"
        "rb = c.post('/v1/workspace/rollback', json={'to_version': 1}).json();"
        "assert rb['version'] == 3, rb;"
        "print('RESTART-OK')"
    )
    out2 = subprocess.run([sys.executable, "-c", phase2], capture_output=True,
                          text=True, cwd=base, env=env)
    assert "RESTART-OK" in out2.stdout, out2.stderr[-600:]


def test_setup_requires_material(client):
    c, _ = client
    r = c.post("/v1/setup/client", json={})
    assert r.status_code == 422


def test_setup_flags_contradictions(client):
    c, _ = client
    r = c.post("/v1/setup/client", json={"notes":
        "We are Alpha. We offer audits. Our ideal clients are startups. "
        "We offer plumbing services."})
    d = r.json()
    assert d["readiness"]["state"] == "blocked"
    assert d["profile"]["contradictions"]
    assert any("Contradictions" in q or "conflict" in q.lower()
               for q in d["readiness"]["questions"])
