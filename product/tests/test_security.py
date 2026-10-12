"""
Security contract tests for the Acquisition OS API (product/API_SPEC.md §1).

Covers: credential requirement, tenant isolation, public-path carve-outs,
the documented error envelope, and explicit development-only auth bypass.
"""

import json

from fastapi.testclient import TestClient

from product.api import security
from product.api.main import create_app
from product.tests.conftest import OTHER_ORG, TEST_KEY, TEST_ORG

ORG_PATH = f"/v1/organizations/{TEST_ORG}"


class TestAuthenticationRequired:
    def test_missing_token_is_401_with_envelope(self, client):
        r = client.get(f"{ORG_PATH}/opportunities")
        assert r.status_code == 401
        body = r.json()["error"]
        assert body["code"] == "UNAUTHENTICATED"
        assert body["details"] == []
        assert r.headers.get("WWW-Authenticate") == "Bearer"

    def test_non_bearer_header_is_401(self, client):
        r = client.get(f"{ORG_PATH}/opportunities", headers={"Authorization": f"Basic {TEST_KEY}"})
        assert r.status_code == 401

    def test_empty_bearer_is_401(self, client):
        r = client.get(f"{ORG_PATH}/opportunities", headers={"Authorization": "Bearer "})
        assert r.status_code == 401

    def test_wrong_key_is_401(self, client):
        r = client.get(f"{ORG_PATH}/opportunities", headers={"Authorization": "Bearer wrong-key"})
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_valid_key_is_accepted(self, client, auth_headers):
        r = client.get(f"{ORG_PATH}/opportunities", headers=auth_headers)
        assert r.status_code == 200


class TestTenantIsolation:
    def test_key_from_other_org_cannot_read_target_org(self, client, api_keys):
        # Simulate a key belonging to a different tenant.
        other_headers = {"Authorization": "Bearer other-tenant-key"}
        api_keys._keys[OTHER_ORG] = "other-tenant-key"
        r = client.get(f"{ORG_PATH}/opportunities", headers=other_headers)
        # 404 (not 403): do not confirm that the target organization exists.
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "ORG_NOT_FOUND"

    def test_cross_org_list_is_404_even_with_valid_key(self, client, auth_headers):
        r = client.get(f"/v1/organizations/{OTHER_ORG}/opportunities", headers=auth_headers)
        assert r.status_code == 404

    def test_cross_org_health_is_404(self, client, auth_headers):
        r = client.get(f"/v1/organizations/{OTHER_ORG}/health", headers=auth_headers)
        assert r.status_code == 404


class TestPublicPaths:
    def test_liveness_probe_is_public(self, client):
        assert client.get("/health").status_code == 200

    def test_openapi_document_is_public(self, client):
        assert client.get("/openapi.json").status_code == 200

    def test_docs_are_public(self, client):
        assert client.get("/docs").status_code == 200

    def test_org_scoped_health_requires_auth(self, client):
        assert client.get(f"{ORG_PATH}/health").status_code == 401


class TestErrorEnvelope:
    def test_unknown_path_uses_envelope(self, client):
        r = client.get("/definitely-not-a-route")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NOT_FOUND"

    def test_validation_error_uses_envelope(self, client, auth_headers):
        r = client.post(f"{ORG_PATH}/opportunities", headers=auth_headers, json={"nonsense": True})
        assert r.status_code == 422
        body = r.json()["error"]
        assert body["code"] == "VALIDATION_ERROR"
        assert isinstance(body["details"], list) and body["details"]


class TestAuthBypassIsExplicit:
    def test_disabled_mode_allows_access_without_key(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_API_KEYS", "")
        monkeypatch.setenv("PRODUCT_AUTH_MODE", "disabled")
        security.set_key_store(None)
        try:
            with TestClient(create_app()) as client:
                r = client.get(f"{ORG_PATH}/opportunities")
                assert r.status_code == 200
        finally:
            security.set_key_store(None)

    def test_default_mode_is_enforced(self, monkeypatch):
        monkeypatch.delenv("PRODUCT_AUTH_MODE", raising=False)
        assert security.auth_mode() == "enforced"

    def test_unknown_mode_falls_back_to_enforced(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_AUTH_MODE", "whatever")
        assert security.auth_mode() == "enforced"


class TestKeyStore:
    def test_verify_returns_owning_org(self, api_keys):
        assert api_keys.verify(TEST_KEY) == TEST_ORG

    def test_verify_rejects_unknown_and_empty(self, api_keys):
        assert api_keys.verify("nope") is None
        assert api_keys.verify("") is None

    def test_empty_env_yields_empty_store(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_API_KEYS", "")
        assert len(security.ApiKeyStore.from_env()) == 0

    def test_malformed_env_raises_helpful_error(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_API_KEYS", "{not json")
        try:
            security.ApiKeyStore.from_env()
        except RuntimeError as exc:
            assert "PRODUCT_API_KEYS" in str(exc)
        else:
            raise AssertionError("malformed PRODUCT_API_KEYS must raise")


class TestSpecConformancePaths:
    """API_SPEC.md path contract (§list/create/item/pipeline/command/health)."""

    def test_opportunities_list_path(self, client, auth_headers):
        assert client.get(f"{ORG_PATH}/opportunities", headers=auth_headers).status_code == 200

    def test_pipeline_path_not_shadowed_by_item_route(self, client, auth_headers):
        r = client.get(f"{ORG_PATH}/opportunities/pipeline", headers=auth_headers)
        assert r.status_code == 200
        assert "pipeline" in r.json()

    def test_command_center_path(self, client, auth_headers):
        assert client.get(f"{ORG_PATH}/command-center", headers=auth_headers).status_code == 200

    def test_health_path(self, client, auth_headers):
        assert client.get(f"{ORG_PATH}/health", headers=auth_headers).status_code == 200

    def test_acquisition_health_alias_still_works(self, client, auth_headers):
        r = client.get(f"{ORG_PATH}/acquisition-health", headers=auth_headers)
        assert r.status_code == 200
