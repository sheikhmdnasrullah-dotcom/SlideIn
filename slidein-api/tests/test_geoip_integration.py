"""Offline GeoIP2 tests: network context is never personal identity."""

from slidein_api.integrations.geoip import GeoIP2Resolver
from tests.conftest import TENANT_A, TENANT_B


class _Value:
    def __init__(self, **values):
        for key, value in values.items():
            setattr(self, key, value)


class _Reader:
    def city(self, ip):
        assert ip == "8.8.8.8"
        return _Value(
            country=_Value(iso_code="US"),
            city=_Value(name="Mountain View"),
            traits=_Value(
                autonomous_system_number=15169,
                autonomous_system_organization="Example Network Operator",
            ),
        )


def test_geoip_returns_network_context_without_company_or_identity_inference():
    outcome = GeoIP2Resolver(reader=_Reader()).resolve("8.8.8.8")
    assert outcome["status"] == "network_context"
    assert outcome["network_name"] == "Example Network Operator"
    assert outcome["company_domain"] is None
    assert outcome["identity_resolved"] is False


def test_geoip_private_and_invalid_targets_do_not_open_database():
    def forbidden():
        raise AssertionError("database must not open for rejected input")

    resolver = GeoIP2Resolver()
    resolver._open = forbidden
    assert resolver.resolve("127.0.0.1")["status"] == "non_public_ip"
    assert resolver.resolve("not-an-ip")["status"] == "invalid_ip"


def test_geoip_missing_database_is_explicit(tmp_path):
    outcome = GeoIP2Resolver(mmdb_path=str(tmp_path / "missing.mmdb")).resolve("8.8.8.8")
    assert outcome["status"] == "database_unavailable"
    assert outcome["identity_resolved"] is False


def test_network_context_route_is_tenant_bound_and_offline(client, admin_headers, other_tenant_headers):
    unauthenticated = client.post(
        f"/v1/tenants/{TENANT_A}/analytics/network-context", json={"ip": "127.0.0.1"},
    )
    assert unauthenticated.status_code in {401, 403}
    response = client.post(
        f"/v1/tenants/{TENANT_A}/analytics/network-context",
        json={"ip": "127.0.0.1"}, headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"] == {"status": "non_public_ip", "identity_resolved": False}
    assert response.json()["network_io"] is False
    cross_tenant = client.post(
        f"/v1/tenants/{TENANT_A}/analytics/network-context",
        json={"ip": "127.0.0.1"}, headers=other_tenant_headers,
    )
    assert cross_tenant.status_code == 404
    own_tenant = client.post(
        f"/v1/tenants/{TENANT_B}/analytics/network-context",
        json={"ip": "not-an-ip"}, headers=other_tenant_headers,
    )
    assert own_tenant.status_code == 200
    assert own_tenant.json()["result"]["status"] == "invalid_ip"
