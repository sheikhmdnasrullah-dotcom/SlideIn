"""
Acquisition OS — End-to-End Tests
Tests the complete acquisition workflows.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from datetime import datetime, timedelta
import uuid

from product.api.main import app
from product.db.session import init_db, drop_all_tables, get_db_session
from product.db.repositories import OrganizationRepository, OpportunityRepository
from product.services.service_impl import DemoDataService


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def setup_database():
    """Set up test database."""
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://acquisition:acquisition@localhost:5432/acquisition_os_test"
    await drop_all_tables()
    await init_db()
    yield
    await drop_all_tables()


@pytest_asyncio.fixture
async def client(setup_database):
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def demo_org(setup_database):
    """Create demo organization for testing."""
    async with get_db_session() as session:
        org_id = f"org_test_{uuid.uuid4().hex[:8]}"
        tenant_id = org_id

        org = {
            "id": org_id,
            "tenant_id": tenant_id,
            "name": "Test Mortgage Co",
            "slug": f"test-mortgage-{uuid.uuid4().hex[:8]}",
            "plan": "starter",
            "plan_status": "active",
            "settings": {
                "icp": {
                    "segments": ["first_time_buyer"],
                    "locations": ["Austin, TX"],
                    "property_range": {"min": 300000, "max": 800000},
                },
            },
            "monthly_send_limit": 1000,
            "monthly_opportunity_limit": 100,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        org_repo = OrganizationRepository(session)
        created = await org_repo.create(org)

        # Seed demo data
        demo_service = DemoDataService(session, org_id, tenant_id)
        await demo_service.seed_all()

        return {"org_id": org_id, "tenant_id": tenant_id, "name": created["name"]}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHealth:
    async def test_health_endpoint(self, client: AsyncClient):
        """Test health endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "acquisition-os-api"


class TestOpportunities:
    async def test_list_opportunities(self, client: AsyncClient, demo_org):
        """Test listing opportunities."""
        response = await client.get(f"/v1/organizations/{demo_org['org_id']}/opportunities")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "pagination" in data

    async def test_create_opportunity(self, client: AsyncClient, demo_org):
        """Test creating an opportunity."""
        response = await client.post(
            f"/v1/organizations/{demo_org['org_id']}/opportunities",
            json={
                "person": {
                    "name": "Test Prospect",
                    "email": "test@example.com",
                    "phone": "+1-555-0199",
                    "location": "Austin, TX",
                },
                "source": "inbound",
                "discovery_signals": ["calculator_use"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["person"]["name"] == "Test Prospect"
        assert data["state"] == "discovered"
        assert data["opportunity_score"] == 0

    async def test_get_opportunity(self, client: AsyncClient, demo_org):
        """Test getting a specific opportunity."""
        # First create one
        create_response = await client.post(
            f"/v1/organizations/{demo_org['org_id']}/opportunities",
            json={
                "person": {"name": "Get Test", "email": "get@example.com", "location": "Austin, TX"},
                "source": "inbound",
            },
        )
        opp_id = create_response.json()["id"]

        # Then get it
        response = await client.get(f"/v1/organizations/{demo_org['org_id']}/opportunities/{opp_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["person"]["name"] == "Get Test"

    async def test_research_opportunity(self, client: AsyncClient, demo_org):
        """Test researching an opportunity."""
        # Create opportunity
        create_response = await client.post(
            f"/v1/organizations/{demo_org['org_id']}/opportunities",
            json={
                "person": {"name": "Research Test", "email": "research@example.com", "location": "Austin, TX"},
                "source": "inbound",
            },
        )
        opp_id = create_response.json()["id"]

        # Research it
        response = await client.post(
            f"/v1/organizations/{demo_org['org_id']}/opportunities/{opp_id}/research",
            json={"depth": "standard"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "dossier" in data
        assert "evidence" in data
        assert data["confidence"] in ["high", "medium", "low"]

    async def test_qualify_opportunity(self, client: AsyncClient, demo_org):
        """Test qualifying an opportunity."""
        # Create and research
        create_response = await client.post(
            f"/v1/organizations/{demo_org['org_id']}/opportunities",
            json={
                "person": {"name": "Qualify Test", "email": "qualify@example.com", "location": "Austin, TX"},
                "source": "inbound",
            },
        )
        opp_id = create_response.json()["id"]

        await client.post(f"/v1/organizations/{demo_org['org_id']}/opportunities/{opp_id}/research", json={})

        # Qualify
        response = await client.post(
            f"/v1/organizations/{demo_org['org_id']}/opportunities/{opp_id}/qualify",
        )
        assert response.status_code == 200
        data = response.json()
        assert "fit_score" in data
        assert data["opportunity_score"] >= 0
        assert data["qualification_stage"] in ["qualified", "researching"]

    async def test_pipeline(self, client: AsyncClient, demo_org):
        """Test pipeline endpoint."""
        response = await client.get(f"/v1/organizations/{demo_org['org_id']}/opportunities/pipeline")
        assert response.status_code == 200
        data = response.json()
        assert "pipeline" in data
        assert "conversion_rates" in data


class TestCommandCenter:
    async def test_get_command_center(self, client: AsyncClient, demo_org):
        """Test command center endpoint."""
        response = await client.get(f"/v1/organizations/{demo_org['org_id']}/command-center")
        assert response.status_code == 200
        data = response.json()
        assert "greeting" in data
        assert "overnight_summary" in data
        assert "todays_priorities" in data
        assert "system_activity" in data


class TestAcquisitionEngine:
    async def test_valid_transitions(self):
        """Test valid state transitions."""
        from product.services.acquisition_engine import AcquisitionEngine, OpportunityState

        assert AcquisitionEngine.can_transition(OpportunityState.DISCOVERED, OpportunityState.RESEARCHED)
        assert AcquisitionEngine.can_transition(OpportunityState.RESEARCHED, OpportunityState.QUALIFIED)
        assert AcquisitionEngine.can_transition(OpportunityState.QUALIFIED, OpportunityState.CONTACTED)
        assert not AcquisitionEngine.can_transition(OpportunityState.DISCOVERED, OpportunityState.CUSTOMER)

    async def test_state_transition(self):
        """Test state transition execution."""
        from product.services.acquisition_engine import AcquisitionEngine, OpportunityState

        opportunity = {"state": OpportunityState.DISCOVERED.value, "version": 1}
        result = AcquisitionEngine.transition(opportunity, OpportunityState.RESEARCHED, reason="Test")
        assert result["state"] == OpportunityState.RESEARCHED.value
        assert result["version"] == 2

    async def test_invalid_transition(self):
        """Test invalid state transition raises error."""
        from product.services.acquisition_engine import AcquisitionEngine, OpportunityState

        opportunity = {"state": OpportunityState.DISCOVERED.value, "version": 1}
        with pytest.raises(ValueError):
            AcquisitionEngine.transition(opportunity, OpportunityState.CUSTOMER, reason="Test")


class TestAutomationEngine:
    async def test_dry_run(self):
        """Test automation dry run."""
        from product.services.service_impl import AutomationEngine
        from product.events import EventBus

        event_bus = EventBus.get()
        engine = AutomationEngine(None, event_bus, {})

        automation = {
            "id": "auto_test_1",
            "org_id": "org_test",
            "tenant_id": "org_test",
            "steps": [
                {"type": "action", "config": {"action": "send_message"}},
                {"type": "wait", "config": {"duration": 3600}},
            ],
        }

        result = await engine.dry_run("org_test", "auto_test_1", {"opportunity_id": "opp_test"})
        assert result["dry_run"] is True
        assert result["status"] in ["completed", "running"]


class TestTenantIsolation:
    async def test_tenant_isolation(self, client: AsyncClient, demo_org):
        """Test that tenants cannot access each other's data."""
        # Create opportunity in demo_org
        create_response = await client.post(
            f"/v1/organizations/{demo_org['org_id']}/opportunities",
            json={
                "person": {"name": "Isolation Test", "email": "iso@example.com", "location": "Austin, TX"},
                "source": "inbound",
            },
        )
        opp_id = create_response.json()["id"]

        # Try to access with different org_id
        fake_org_id = f"org_fake_{uuid.uuid4().hex[:8]}"
        response = await client.get(f"/v1/organizations/{fake_org_id}/opportunities/{opp_id}")
        assert response.status_code == 404
