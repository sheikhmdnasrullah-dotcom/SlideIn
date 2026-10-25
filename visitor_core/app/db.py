"""Database ledger — SQLAlchemy async over SQLite by default (mock-friendly;
point VISITOR_DB_URL at Postgres for production)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, String, Text, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from .config import settings
from .schemas import VisitorRecord

Base = declarative_base()
_engine = create_async_engine(settings.db_url, echo=False)
_Session = async_sessionmaker(_engine, expire_on_commit=False)


class VisitorRow(Base):
    __tablename__ = "visitors"

    visitor_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_key = Column(String(64), index=True)
    site_domain = Column(String(255), index=True)
    ip = Column(String(64))
    user_agent = Column(Text)
    fingerprint_hash = Column(String(64), index=True)
    session_id = Column(String(128), index=True)
    resolution_tier = Column(String(32), default="ANONYMOUS")
    status = Column(String(32), default="COMPLETED")
    email = Column(String(255), index=True)
    first_name = Column(String(128))
    last_name = Column(String(128))
    linkedin_url = Column(Text)
    company_domain = Column(String(255), index=True)
    geo = Column(JSON, default=dict)
    error_logs = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


async def init_db() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def new_visitor_id() -> str:
    return str(uuid.uuid4())


async def upsert_visitor(record: VisitorRecord) -> None:
    """Insert on first sighting, merge identity fields on resolution updates."""
    async with _Session() as session:
        row = await session.get(VisitorRow, record.visitor_id)
        if row is None:
            row = VisitorRow(visitor_id=record.visitor_id)
            session.add(row)
        data = record.model_dump()
        data["geo"] = json.loads(json.dumps(data.get("geo") or {}))
        for key, value in data.items():
            if key == "visitor_id":
                continue
            if value is not None or key in ("geo", "status", "resolution_tier"):
                setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()


async def get_visitor(visitor_id: str) -> dict | None:
    async with _Session() as session:
        row = await session.get(VisitorRow, visitor_id)
        return None if row is None else {c.name: getattr(row, c.name) for c in VisitorRow.__table__.columns}


async def find_by_session(site_key: str, session_id: str) -> dict | None:
    async with _Session() as session:
        result = await session.execute(
            select(VisitorRow).where(
                VisitorRow.site_key == site_key,
                VisitorRow.session_id == session_id,
            ).limit(1)
        )
        row = result.scalar_one_or_none()
        return None if row is None else {c.name: getattr(row, c.name) for c in VisitorRow.__table__.columns}


async def list_visitors(site_domain: str | None = None, limit: int = 100) -> list[dict]:
    async with _Session() as session:
        q = select(VisitorRow).order_by(VisitorRow.created_at.desc()).limit(limit)
        if site_domain:
            q = q.where(VisitorRow.site_domain == site_domain)
        result = await session.execute(q)
        return [{c.name: getattr(r, c.name) for c in VisitorRow.__table__.columns}
                for r in result.scalars()]
