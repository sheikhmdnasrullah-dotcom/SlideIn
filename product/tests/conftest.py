"""
Acquisition OS — shared test fixtures.

Provides the security-contract constants (API_SPEC.md §1), the API key store
setup, and a TestClient factory that seeds the test organization inside the
app's own event loop (no cross-loop SQLAlchemy/asyncpg pool reuse).
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from product.api import security
from product.api.main import create_app

TEST_ORG = "org_test"
OTHER_ORG = "org_other"
TEST_KEY = "pk_test_" + "x" * 32

# The suite always runs with authentication enforced; individual tests opt
# out explicitly (e.g. TestAuthBypassIsExplicit monkeypatches the mode).
os.environ["PRODUCT_API_KEYS"] = json.dumps({TEST_ORG: TEST_KEY})
os.environ["PRODUCT_AUTH_MODE"] = "enforced"
security.set_key_store(None)


def _seed_org(client: TestClient, org_id: str) -> None:
    """Create the test organization (idempotent) inside the app loop."""
    from product.db.models import Organization
    from product.db.session import get_db_session

    async def _ensure() -> None:
        async with get_db_session() as session:
            from sqlalchemy import select

            existing = (
                await session.execute(select(Organization).where(Organization.id == org_id))
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    Organization(
                        id=org_id,
                        org_id=org_id,
                        tenant_id=org_id,
                        name="Test Organization",
                        slug=f"test-{org_id}",
                    )
                )

    client.portal.call(_ensure)


@pytest.fixture
def api_keys():
    """The process-wide key store, freshly loaded from the env."""
    store = security.ApiKeyStore.from_env()
    security.set_key_store(store)
    yield store
    security.set_key_store(None)


@pytest.fixture
def client(api_keys):
    """Authenticated TestClient (enforced mode) with the test org seeded.

    Connections are disposed inside the client's event loop so pooled
    asyncpg connections never leak into another test's loop.
    """
    with TestClient(create_app()) as test_client:
        try:
            _seed_org(test_client, TEST_ORG)
            yield test_client
        finally:
            from product.db.session import engine

            test_client.portal.call(engine.dispose)
            security.set_key_store(None)


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {TEST_KEY}"}
