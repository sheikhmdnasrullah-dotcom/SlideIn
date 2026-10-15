"""Test configuration for the Slidein workflow backend.

Everything runs against a file-backed SQLite database so the whole
journey is testable without external services. Production uses Postgres
through the same models.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="slidein-tests-"))
TEST_DB = _TMP / "slidein-test.db"

os.environ["SLIDEIN_DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB}"
os.environ.setdefault("SLIDEIN_AUTH_MODE", "enforced")

TENANT_A = "ten_alpha"
TENANT_B = "ten_beta"
KEY_A_ADMIN = "sk_alpha_admin_0001"
KEY_A_OPERATOR = "sk_alpha_operator_0001"
KEY_A_VIEWER = "sk_alpha_viewer_0001"
KEY_A_SERVICE = "sk_alpha_service_0001"
KEY_B_ADMIN = "sk_beta_admin_0001"

os.environ["SLIDEIN_API_KEYS"] = json.dumps(
    {
        TENANT_A: {"key": KEY_A_ADMIN, "role": "admin"},
    }
)
# Extra roles are configured through a second store so tests can exercise
# permissions without exposing role switching on a single key.
os.environ["SLIDEIN_TEST_ROLE_KEYS"] = json.dumps(
    {
        TENANT_A: {
            KEY_A_ADMIN: "admin",
            KEY_A_OPERATOR: "operator",
            KEY_A_VIEWER: "viewer",
            KEY_A_SERVICE: "service",
        },
        TENANT_B: {KEY_B_ADMIN: "admin"},
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from slidein_api import security  # noqa: E402
from slidein_api.api.app import create_app  # noqa: E402
from slidein_api.db import init_db, session_scope  # noqa: E402
from slidein_api.services.config import ConfigService  # noqa: E402


class _TestKeyStore(security.KeyStore):
    """Key store that maps several keys per workspace for role tests."""

    def __init__(self, by_tenant: dict[str, dict[str, str]]) -> None:
        super().__init__({})
        self._by_tenant = by_tenant

    def verify(self, presented: str) -> tuple[str, str] | None:
        import hmac

        match: tuple[str, str] | None = None
        for _tenant_id, keys in self._by_tenant.items():
            for key, role in keys.items():
                if hmac.compare_digest(presented, key):
                    match = (self._tenant_for(presented), role)
        return match

    def _tenant_for(self, presented: str) -> str:
        for tenant_id, keys in self._by_tenant.items():
            if presented in keys:
                return tenant_id
        return ""

    @property
    def tenant_ids(self) -> list[str]:
        return sorted(self._by_tenant)


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_database():
    import asyncio

    async def _init():
        await init_db()

    asyncio.run(_init())


@pytest.fixture(autouse=True)
def _clean_database():
    """Every test starts from an empty database so journeys are isolated."""
    import asyncio

    from slidein_api.db import reset_db

    asyncio.run(reset_db())
    yield


@pytest.fixture(autouse=True)
def _restore_key_store():
    role_keys = json.loads(os.environ["SLIDEIN_TEST_ROLE_KEYS"])
    security.set_key_store(_TestKeyStore(role_keys))
    yield
    security.set_key_store(None)


@pytest.fixture()
def client(_restore_key_store):
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {KEY_A_ADMIN}", "X-Slidein-Tenant": TENANT_A}


@pytest.fixture()
def operator_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {KEY_A_OPERATOR}", "X-Slidein-Tenant": TENANT_A}


@pytest.fixture()
def viewer_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {KEY_A_VIEWER}", "X-Slidein-Tenant": TENANT_A}


@pytest.fixture()
def service_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {KEY_A_SERVICE}", "X-Slidein-Tenant": TENANT_A}


@pytest.fixture()
def other_tenant_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {KEY_B_ADMIN}", "X-Slidein-Tenant": TENANT_B}


PROFILE_PAYLOAD = {
    "legal_name": "Northwind Cloud Systems",
    "website_url": "https://northwindcloud.example",
    "industry": "Cloud Infrastructure",
    "company_description": (
        "Automated multi-cloud cost optimization and FinOps tooling for "
        "platform engineering teams."
    ),
    "core_value_prop": (
        "Cut cloud spend by 30% through automated rightsizing without downtime."
    ),
    "markets_served": ["North America", "EMEA"],
    "target_roles": ["VP Engineering", "CTO", "Head of Infrastructure"],
    "brand_voice": "Direct, evidence-led, no hype.",
}

ICP_PAYLOAD = {
    "name": "Scaling Platform Teams",
    "industries": ["Cloud Infrastructure", "FinTech", "SaaS"],
    "company_size_min": 20,
    "company_size_max": 800,
    "geographies": ["North America"],
    "target_roles": ["VP Engineering", "CTO", "Head of Infrastructure"],
    "required_signals": ["Kubernetes", "cloud cost", "DevOps"],
    "exclusion_keywords": ["recruitment agency"],
    "qualify_threshold": 60,
}

OFFER_PAYLOAD = {
    "name": "FinOps Audit & Automated Rightsizing",
    "summary": (
        "14-day zero-risk audit that finds unattached volumes and oversized "
        "instances, then keeps them sized automatically."
    ),
    "pain_points_solved": ["runaway cloud bills", "no time for infrastructure cleanup"],
    "target_persona": "VP Engineering, CTO, Head of Infrastructure",
    "proof_points": ["Saved FinTech Corp $420k/yr in idle cloud spend"],
}


@pytest.fixture()
def configured_workspace(client, admin_headers) -> dict:
    """Business Profile + Offer + ICP persisted for tenant A."""
    profile = client.post(
        f"/v1/tenants/{TENANT_A}/profile",
        json={**PROFILE_PAYLOAD, "reason": "initial profile"},
        headers=admin_headers,
    ).json()["profile"]
    offer = client.post(
        f"/v1/tenants/{TENANT_A}/offers",
        json=OFFER_PAYLOAD,
        headers=admin_headers,
    ).json()["offer"]
    icp = client.post(
        f"/v1/tenants/{TENANT_A}/icps",
        json=ICP_PAYLOAD,
        headers=admin_headers,
    ).json()["icp"]
    return {
        "client": client,
        "profile": profile,
        "offer": offer,
        "icp": icp,
        "headers": admin_headers,
        "tenant_id": TENANT_A,
    }


def prospect_records(count: int = 2) -> list[dict]:
    rows = []
    for index in range(count):
        rows.append(
            {
                "first_name": f"Prospect{index}",
                "last_name": f"Tester{index}",
                "email": f"prospect{index}@cloudwave{index}.example",
                "company_name": f"CloudWave {index}",
                "company_domain": f"cloudwave{index}.example",
                "job_title": "VP Engineering",
                "company_size": 240,
                "location": "North America",
            }
        )
    return rows


SAMPLE_CLAIMS = [
    {
        "evidence_type": "hiring_signal",
        "claim_text": (
            "CloudWave posted four openings for Kubernetes and cloud cost engineers."
        ),
        "source_url": "https://careers.cloudwave0.example/jobs/7821",
        "source_name": "CloudWave careers",
        "confidence": 0.95,
        "verification_status": "verified",
    },
    {
        "evidence_type": "website_claim",
        "claim_text": (
            "The company states it is migrating to Kubernetes and cutting cloud cost."
        ),
        "source_url": "https://cloudwave0.example/about",
        "source_name": "CloudWave",
        "confidence": 1.0,
        "verification_status": "verified",
    },
    {
        "evidence_type": "tech_stack",
        "claim_text": "Detected technologies referenced by the page: Kubernetes, DevOps",
        "source_url": "https://cloudwave0.example/",
        "source_name": "CloudWave",
        "confidence": 0.6,
        "verification_status": "inferred",
    },
]
