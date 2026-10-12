#!/usr/bin/env python3
"""
Acquisition OS — Startup Script
Initializes database, creates demo tenant, starts API.
"""

import asyncio
import os
import sys
import uuid
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Ensure product/ is importable — repo root is parent of this file's grandparent
SCRIPT_PATH = os.path.abspath(__file__)
PRODUCT_DIR = os.path.dirname(os.path.dirname(SCRIPT_PATH))
REPO_DIR = os.path.dirname(PRODUCT_DIR)
sys.path.insert(0, REPO_DIR)
sys.path.insert(0, PRODUCT_DIR)


async def init_database():
    """Initialize database tables."""
    from product.db.session import init_db
    logger.info("Initializing database...")
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database init failed: {e}")
        raise


async def create_demo_tenant():
    """Create demo tenant with sample data."""
    from product.db.session import get_db_session
    from product.db.repositories import OrganizationRepository
    from product.services.demo_data import DemoDataService
    from product.db.models import User

    logger.info("Creating demo tenant...")
    async with get_db_session() as session:
        # Check if demo org already exists
        org_repo = OrganizationRepository(session)
        existing = await org_repo.get_by_slug("abc-mortgage")
        if existing:
            logger.info(f"Demo tenant already exists: {existing['id']}")
            return existing["id"]

        # Create demo organization
        org_id = f"org_{uuid.uuid4().hex[:8]}"
        tenant_id = org_id

        org = {
            "id": org_id,
            "org_id": org_id,
            "tenant_id": tenant_id,
            "name": "ABC Mortgage",
            "slug": "abc-mortgage",
            "plan": "growth",
            "plan_status": "active",
            "settings": {
                "brand_voice": "professional_but_warm",
                "icp": {
                    "segments": ["first_time_buyer", "move_up_buyer", "refinance"],
                    "locations": ["Austin, TX", "Round Rock, TX", "Cedar Park, TX"],
                    "property_range": {"min": 300000, "max": 1000000},
                    "income_range": {"min": 60000, "max": 250000},
                },
                "business_policy": {
                    "allowed_actions": ["explain_general_concepts", "collect_preliminary_info", "schedule_conversation"],
                    "escalate_actions": ["specific_underwriting_questions", "complex_financial_circumstances"],
                    "forbidden_claims": ["guaranteed_approval", "guaranteed_rates"],
                },
            },
            "monthly_send_limit": 10000,
            "monthly_opportunity_limit": 1000,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        created_org = await org_repo.create(org)
        logger.info(f"Created demo organization: {created_org['id']} ({created_org['name']})")

        # Create demo user
        from sqlalchemy import insert as sa_insert
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        user = {
            "id": user_id,
            "org_id": org_id,
            "tenant_id": tenant_id,
            "email": "john@abcmortgage.com",
            "name": "John Smith",
            "role": "admin",
            "active": True,
            "email_verified": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        await session.execute(User.__table__.insert().values(**user))
        await session.flush()
        logger.info(f"Created demo user: {user['email']}")

        # Seed demo data
        demo_service = DemoDataService(session, org_id, tenant_id)
        await demo_service.seed_all()
        logger.info("Demo data seeded")

        return org_id


async def main():
    """Main startup sequence."""
    logger.info("=" * 60)
    logger.info("ACQUISITION OS — STARTUP")
    logger.info("=" * 60)

    await init_database()
    org_id = await create_demo_tenant()

    logger.info("=" * 60)
    logger.info("STARTUP COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Demo organization ID: {org_id}")
    logger.info("")
    logger.info("To start the API:")
    logger.info("  source venv_product/bin/activate")
    logger.info("  uvicorn product.api.main:app --host 0.0.0.0 --port 8000 --reload")
    logger.info("")
    logger.info("To view API docs:")
    logger.info("  http://localhost:8000/docs")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
