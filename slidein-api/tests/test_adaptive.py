"""Console adaptation engine: registry invariants and proposal lifecycle.

Verifies the anti-loophole guarantees:
  * sections are always a validated subset of the module registry,
  * `settings` can never be removed,
  * a proposal never changes Console state until explicitly approved,
  * behavior evidence never promotes into persisted sections.
"""

from __future__ import annotations

import pytest

from slidein_api.services.adaptive import (
    AdaptiveService,
    Proposal,
)
from slidein_api.services.modules import MODULE_IDS


def _dash(tenant_id: str) -> str:
    return f"/v1/tenants/{tenant_id}/console"


def test_effective_sections_default_to_full_registry(client, admin_headers):
    resp = client.get(f"{_dash('ten_alpha')}/sections", headers=admin_headers)
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()["sections"]]
    # Full default registry, ordered, settings pinned.
    assert ids == list(MODULE_IDS)
    assert "settings" in ids


def test_set_sections_validates_against_registry(client, admin_headers):
    body = [{"id": "overview"}, {"id": "discovery"}, {"id": "settings"}]
    resp = client.put(
        f"{_dash('ten_alpha')}/sections", json=body, headers=admin_headers
    )
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()["sections"]]
    assert ids == ["overview", "discovery", "settings"]


def test_set_sections_rejects_unknown_section(client, admin_headers):
    resp = client.put(
        f"{_dash('ten_alpha')}/sections",
        json=[{"id": "console"}, {"id": "made_up"}],
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_settings_can_never_be_removed():
    """apply_preferences must silently pin `settings` even if omitted."""
    import asyncio

    service = AdaptiveService()
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            service.apply_preferences(
                "ten_pin", [{"id": "overview"}, {"id": "discovery"}]
            )
        )
        # `settings` was auto-pinned and is always present.
        assert "settings" in [s.id for s in result]
        sections = loop.run_until_complete(service.effective_sections("ten_pin"))
        assert "settings" in [s.id for s in sections]
    finally:
        loop.close()


def test_proposal_does_not_mutate_state(client, admin_headers):
    # Propose adding a section the registry allows (already default, so pick
    # a label change to prove the proposal is inert until approved).
    resp = client.post(
        f"{_dash('ten_alpha')}/sections/propose",
        json={
            "section_id": "discovery",
            "action": "label",
            "evidence": {"label": "Prospects"},
            "reasoning": "user calls them Prospects",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "proposed"
    # State unchanged: discovery label still None.
    sections = client.get(
        f"{_dash('ten_alpha')}/sections", headers=admin_headers
    ).json()["sections"]
    assert next(s for s in sections if s["id"] == "discovery")["label"] is None


def test_propose_rejects_unknown_section(client, admin_headers):
    resp = client.post(
        f"{_dash('ten_alpha')}/sections/propose",
        json={"section_id": "nope", "action": "add"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_proposal_approve_applies_label_change(client, admin_headers):
    propose = client.post(
        f"{_dash('ten_alpha')}/sections/propose",
        json={
            "section_id": "discovery",
            "action": "label",
            "evidence": {"label": "Prospects"},
            "reasoning": "rename",
        },
        headers=admin_headers,
    )
    pid = propose.json()["id"]
    approve = client.post(
        f"{_dash('ten_alpha')}/sections/{pid}/approve", headers=admin_headers
    )
    assert approve.status_code == 200
    sections = client.get(
        f"{_dash('ten_alpha')}/sections", headers=admin_headers
    ).json()["sections"]
    assert next(s for s in sections if s["id"] == "discovery")["label"] == "Prospects"


def test_proposal_approve_unknown_id_rejected(client, admin_headers):
    resp = client.post(
        f"{_dash('ten_alpha')}/sections/does_not_exist/approve",
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_behavior_records_do_not_promote_into_sections():
    """Behavior evidence only feeds proposals; it never becomes a section."""
    import asyncio

    service = AdaptiveService()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(service.record_user_interaction(
            "ten_behavior", "overview", "clicked"
        ))
        loop.run_until_complete(service.record_user_interaction(
            "ten_behavior", "discovery", "clicked"
        ))
        sections = loop.run_until_complete(service.effective_sections("ten_behavior"))
        # Still the default registry — evidence never promoted.
        assert [s.id for s in sections] == list(MODULE_IDS)
    finally:
        loop.close()


def test_viewer_can_read_sections_but_not_write(client, viewer_headers):
    resp = client.get(
        f"{_dash('ten_alpha')}/sections", headers=viewer_headers
    )
    assert resp.status_code == 200
    bad = client.put(
        f"{_dash('ten_alpha')}/sections",
        json=[{"id": "overview"}],
        headers=viewer_headers,
    )
    assert bad.status_code == 403
