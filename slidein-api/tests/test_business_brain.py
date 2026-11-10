"""Business Brain: file-backed workspace, integrity, onboarding writes, tasks."""

from __future__ import annotations

import json
import os

import pytest

from tests.conftest import TENANT_A, TENANT_B

PROFILE_FACT = {
    "legal_name": "Acme Inbound",
    "website_url": "https://acme.example.com",
    "industry": "SaaS",
    "company_description": "Cold email tooling for agencies.",
    "core_value_prop": "Send personal outreach at scale.",
}


def _ws_root(monkeypatch, tmp_path) -> str:
    monkeypatch.setenv("SLIDEIN_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    return str(tmp_path / "workspaces")


def _init(client, headers, tenant_id=TENANT_A):
    response = client.post("/v1/brain/init", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _write_fact(client, headers, kind, fact, actor="operator"):
    response = client.post(
        "/v1/brain/facts",
        json={"kind": kind, "fact": fact, "actor": actor, "reason": "onboarding"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_task(client, headers, **payload):
    body = {
        "requested_outcome": payload.get("requested_outcome") or "Research prospect",
        "workflow_step": payload.get("workflow_step") or "research",
        "success_criteria": payload.get("success_criteria") if payload.get("success_criteria") is not None else ["research evidence collected"],
        "constraints": payload.get("constraints") or [],
        "permitted_tools": payload.get("permitted_tools") or ["research"],
        "context_refs": payload.get("context_refs") or [],
    }
    response = client.post("/v1/brain/tasks", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _transition(client, headers, task_id, to, **payload):
    response = client.post(
        f"/v1/brain/tasks/{task_id}/transition",
        json={"to": to, "reason": payload.get("reason") or ""},
        headers=headers,
    )
    return response


def test_init_creates_isolated_workspace_with_brain_index(client, admin_headers, monkeypatch, tmp_path):
    root = _ws_root(monkeypatch, tmp_path)
    status = _init(client, admin_headers)

    assert status["initialized"] is True
    assert status["valid"] is True
    assert status["errors"] == []
    assert status["schema_version"] == 1
    for relpath in (
        "brain.md", "CHANGELOG.md", "tasks/index.md", "workflows/index.md", "knowledge/index.md",
        "business/profile.md", "business/offers.md", "business/icp.md", "business/policies.md",
        "business/integrations.md", "tasks", "evidence", "artifacts", "schemas",
    ):
        expected = True
        if relpath.endswith(("/",)):
            expected = True
        if relpath in ("tasks", "evidence", "artifacts", "schemas"):
            assert (tmp_path / "workspaces" / "ten_alpha" / relpath).is_dir()
            continue
        assert (tmp_path / "workspaces" / "ten_alpha" / relpath).exists(), relpath

    assert (tmp_path / "workspaces" / "ten_alpha" / "brain.md").exists()
    assert (tmp_path / "workspaces" / "ten_alpha" / "business" / "profile.md").exists()

    status2 = client.get("/v1/brain", headers=admin_headers).json()
    assert status2["initialized"] is True
    assert status2["valid"] is True


def test_brain_status_reports_missing_required_file(client, admin_headers, monkeypatch, tmp_path):
    _ws_root(monkeypatch, tmp_path)
    _init(client, admin_headers)
    (tmp_path / "workspaces" / "ten_alpha" / "business" / "offers.md").unlink()

    status = client.get("/v1/brain", headers=admin_headers).json()
    assert status["initialized"] is True
    assert status["valid"] is False
    assert any("offers.md" in e for e in status["errors"])


def test_onboarding_fact_write_persists_and_reads_back(client, admin_headers, monkeypatch, tmp_path):
    _ws_root(monkeypatch, tmp_path)
    _init(client, admin_headers)

    result = _write_fact(client, admin_headers, "profile", PROFILE_FACT)
    assert result["ok"] is True
    assert result["version"] == 1
    assert result["previous_version"] == 0
    assert result["validation"]["ok"] is True

    facts = client.get("/v1/brain/facts", headers=admin_headers).json()
    assert facts["initialized"] is True
    assert facts["valid"] is True
    assert facts["facts"]["profile"]["legal_name"] == "Acme Inbound"
    assert facts["facts"]["profile"]["industry"] == "SaaS"


def test_structured_fact_edit_preserves_unrelated_business_knowledge(client, admin_headers, monkeypatch, tmp_path):
    _ws_root(monkeypatch, tmp_path)
    _init(client, admin_headers)
    _write_fact(client, admin_headers, "profile", PROFILE_FACT)

    _write_fact(client, admin_headers, "profile", {
        "legal_name": "Acme Inbound Ltd",
        "website_url": "https://acme.example.com",
        "industry": "SaaS",
        "company_description": "Cold email tooling for agencies.",
        "core_value_prop": "Send personal outreach at scale.",
    })

    facts = client.get("/v1/brain/facts", headers=admin_headers).json()
    assert facts["facts"]["profile"]["legal_name"] == "Acme Inbound Ltd"
    assert facts["facts"]["profile"]["company_description"] == "Cold email tooling for agencies."


def test_brain_write_fact_rejects_incomplete_profile(client, admin_headers, monkeypatch, tmp_path):
    _ws_root(monkeypatch, tmp_path)
    _init(client, admin_headers)

    response = client.post(
        "/v1/brain/facts",
        json={"kind": "profile", "fact": {"legal_name": "Only Name"}, "actor": "operator", "reason": "bad"},
        headers=admin_headers,
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "brain_invalid"
    assert body["error"]["retryable"] is False


def test_task_lifecycle_full_flow(client, admin_headers, monkeypatch, tmp_path):
    _ws_root(monkeypatch, tmp_path)
    _init(client, admin_headers)

    task = _create_task(client, admin_headers, requested_outcome="Research prospect", workflow_step="research")
    task_id = task["task_id"]
    assert task["status"] == "queued"

    response = _transition(client, admin_headers, task_id, "planning")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "planning"

    response = _transition(client, admin_headers, task_id, "running")
    assert response.status_code == 200
    assert response.json()["attempts"] == 1

    response = _transition(client, admin_headers, task_id, "verifying")
    assert response.status_code == 200

    response = _transition(client, admin_headers, task_id, "completed")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    fetched = client.get(f"/v1/brain/tasks/{task_id}", headers=admin_headers).json()
    assert fetched["status"] == "completed"
    assert fetched["task_id"] == task_id


def test_task_completion_requires_success_criteria(client, admin_headers, monkeypatch, tmp_path):
    _ws_root(monkeypatch, tmp_path)
    _init(client, admin_headers)

    task = _create_task(client, admin_headers, success_criteria=[])
    task_id = task["task_id"]

    assert _transition(client, admin_headers, task_id, "planning").status_code == 200
    assert _transition(client, admin_headers, task_id, "running").status_code == 200
    assert _transition(client, admin_headers, task_id, "verifying").status_code == 200
    response = _transition(client, admin_headers, task_id, "completed")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "brain_invalid"


def test_task_invalid_transition_rejected(client, admin_headers, monkeypatch, tmp_path):
    _ws_root(monkeypatch, tmp_path)
    _init(client, admin_headers)

    task = _create_task(client, admin_headers)
    task_id = task["task_id"]

    response = _transition(client, admin_headers, task_id, "completed")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "brain_invalid"


def test_task_not_found_returns_404(client, admin_headers, monkeypatch, tmp_path):
    _ws_root(monkeypatch, tmp_path)
    _init(client, admin_headers)

    response = client.get("/v1/brain/tasks/task_missing000000000000", headers=admin_headers)
    assert response.status_code == 404


def test_tasks_are_tenant_scoped(client, admin_headers, monkeypatch, tmp_path):
    _ws_root(monkeypatch, tmp_path)
    _init(client, admin_headers)

    task = _create_task(client, admin_headers)
    task_id = task["task_id"]

    # Same caller, same tenant -> readable.
    assert client.get(f"/v1/brain/tasks/{task_id}", headers=admin_headers).status_code == 200

    # Another tenant must not reach this tenant's task.
    other = client.get(f"/v1/brain/tasks/{task_id}", headers={"Authorization": "Bearer sk_beta_admin_0001", "X-Slidein-Tenant": TENANT_B})
    assert other.status_code == 404


def test_task_lifecycle_rejects_transition_out_of_terminal_state(client, admin_headers, monkeypatch, tmp_path):
    _ws_root(monkeypatch, tmp_path)
    _init(client, admin_headers)

    task = _create_task(client, admin_headers)
    task_id = task["task_id"]
    _transition(client, admin_headers, task_id, "planning")
    _transition(client, admin_headers, task_id, "running")
    _transition(client, admin_headers, task_id, "verifying")
    _transition(client, admin_headers, task_id, "completed")

    response = _transition(client, admin_headers, task_id, "queued")
    assert response.status_code == 422


def test_brain_status_uninitialized_workspace(client, admin_headers, monkeypatch, tmp_path):
    _ws_root(monkeypatch, tmp_path)
    status = client.get("/v1/brain", headers=admin_headers).json()
    assert status["initialized"] is False
    assert status["valid"] is False
