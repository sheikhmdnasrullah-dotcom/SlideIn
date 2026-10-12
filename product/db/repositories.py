"""
Acquisition OS — Database Repositories
Data access layer for all product entities.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select, insert, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import expression
import uuid
import logging

from product.db.models import (
    Organization,
    User,
    Opportunity,
    OpportunityEvent,
    ResearchDossier,
    Content,
    Campaign,
    Automation,
    Mission,
    Conversation,
    Message,
    SystemActivity,
    AcquisitionHealth,
    Integration,
    SentMessage,
    ContentAttribution,
)

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository with common operations."""

    def __init__(self, session: AsyncSession, model):
        self.session = session
        self.model = model

    async def get(self, id: str, org_id: str) -> Optional[Dict[str, Any]]:
        """Get a single record by ID, ensuring tenant isolation."""
        result = await self.session.execute(
            select(self.model).where(
                and_(self.model.id == id, self.model.org_id == org_id)
            )
        )
        record = result.scalar_one_or_none()
        return {c.name: getattr(record, c.name) for c in record.__table__.columns} if record else None

    async def list(
        self,
        org_id: str,
        filters: Dict[str, Any],
        pagination: Dict[str, int],
        order_by: Optional[str] = None,
        order_dir: str = "desc",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List records with filters and pagination."""
        query = select(self.model).where(self.model.org_id == org_id)

        # Apply filters
        for key, value in filters.items():
            if value is None:
                continue
            column = getattr(self.model, key, None)
            if column is None:
                continue
            if isinstance(value, list):
                query = query.where(column.in_(value))
            elif key == "search":
                # Search in person JSON field for opportunities
                if hasattr(self.model, "person"):
                    query = query.where(
                        or_(
                            self.model.person["name"].astext.ilike(f"%{value}%"),
                            self.model.person["email"].astext.ilike(f"%{value}%"),
                        )
                    )
            else:
                query = query.where(column == value)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Order
        if order_by and hasattr(self.model, order_by):
            column = getattr(self.model, order_by)
            if order_dir == "desc":
                query = query.order_by(column.desc())
            else:
                query = query.order_by(column.asc())

        # Paginate
        limit = pagination.get("limit", 20)
        offset = pagination.get("offset", 0)
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        records = result.scalars().all()
        return (
            [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in records],
            total,
        )

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new record."""
        record = self.model(**data)
        self.session.add(record)
        await self.session.flush()
        return {c.name: getattr(record, c.name) for c in record.__table__.columns}

    async def update(self, id: str, org_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a record."""
        result = await self.session.execute(
            update(self.model)
            .where(and_(self.model.id == id, self.model.org_id == org_id))
            .values(**data)
        )
        await self.session.flush()
        if result.rowcount == 0:
            return None
        # Return updated record
        return await self.get(id, org_id)

    async def delete(self, id: str, org_id: str) -> bool:
        """Soft delete a record."""
        result = await self.session.execute(
            update(self.model)
            .where(and_(self.model.id == id, self.model.org_id == org_id))
            .values(deleted_at=datetime.utcnow())
        )
        await self.session.flush()
        return result.rowcount > 0


class OrganizationRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Organization)

    async def get_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        result = await self.session.execute(
            select(Organization).where(and_(Organization.slug == slug, Organization.deleted_at.is_(None)))
        )
        record = result.scalar_one_or_none()
        return {c.name: getattr(record, c.name) for c in record.__table__.columns} if record else None


class OpportunityRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Opportunity)

    async def list_by_state(
        self, org_id: str, state: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List opportunities by state."""
        result = await self.session.execute(
            select(Opportunity)
            .where(and_(Opportunity.org_id == org_id, Opportunity.state == state))
            .order_by(Opportunity.opportunity_score.desc())
            .limit(limit)
        )
        records = result.scalars().all()
        return [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in records]

    async def list_high_value(
        self, org_id: str, min_score: int = 70, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List high-value opportunities."""
        result = await self.session.execute(
            select(Opportunity)
            .where(
                and_(
                    Opportunity.org_id == org_id,
                    Opportunity.opportunity_score >= min_score,
                    Opportunity.state.notin_(["disqualified", "customer"]),
                )
            )
            .order_by(Opportunity.opportunity_score.desc())
            .limit(limit)
        )
        records = result.scalars().all()
        return [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in records]

    async def get_pipeline_counts(self, org_id: str) -> Dict[str, Dict[str, Any]]:
        """Get pipeline counts by state."""
        result = await self.session.execute(
            select(Opportunity.state, func.count())
            .where(Opportunity.org_id == org_id)
            .group_by(Opportunity.state)
        )
        rows = result.all()
        pipeline = {}
        for state, count in rows:
            pipeline[state] = {"count": count, "value": count * 15000}
        return pipeline

    async def record_state_change(
        self, org_id: str, opportunity_id: str, from_state: str, to_state: str, reason: Optional[str] = None
    ):
        """Record an opportunity state change event."""
        event = OpportunityEvent(
            org_id=org_id,
            opportunity_id=opportunity_id,
            event_type="state_changed",
            event_data={"from_state": from_state, "to_state": to_state, "reason": reason},
        )
        self.session.add(event)
        await self.session.flush()


class ConversationRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Conversation)

    async def list_for_opportunity(self, org_id: str, opportunity_id: str) -> List[Dict[str, Any]]:
        result = await self.session.execute(
            select(Conversation)
            .where(and_(Conversation.org_id == org_id, Conversation.opportunity_id == opportunity_id))
            .order_by(Conversation.created_at.desc())
        )
        records = result.scalars().all()
        return [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in records]


class MessageRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Message)

    async def list_for_conversation(self, org_id: str, conversation_id: str) -> List[Dict[str, Any]]:
        result = await self.session.execute(
            select(Message)
            .where(and_(Message.org_id == org_id, Message.conversation_id == conversation_id))
            .order_by(Message.received_at.asc())
        )
        records = result.scalars().all()
        return [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in records]


class SystemActivityRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, SystemActivity)

    async def log(self, org_id: str, activity_type: str, description: str, entity_id: Optional[str] = None, metadata: Optional[Dict] = None):
        activity = SystemActivity(
            org_id=org_id,
            type=activity_type,
            description=description,
            entity_id=entity_id,
            metadata=metadata or {},
            timestamp=datetime.utcnow(),
        )
        self.session.add(activity)
        await self.session.flush()
        return {c.name: getattr(activity, c.name) for c in activity.__table__.columns}


class AutomationRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Automation)

    async def get_by_trigger(self, org_id: str, trigger_type: str) -> List[Dict[str, Any]]:
        result = await self.session.execute(
            select(Automation).where(
                and_(Automation.org_id == org_id, Automation.trigger_type == trigger_type, Automation.active == True)
            )
        )
        records = result.scalars().all()
        return [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in records]


class MissionRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Mission)

    async def get_active(self, org_id: str) -> List[Dict[str, Any]]:
        result = await self.session.execute(
            select(Mission).where(and_(Mission.org_id == org_id, Mission.active == True))
        )
        records = result.scalars().all()
        return [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in records]
