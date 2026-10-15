"""Database session and engine setup.

SQLite is the default so a workspace can run locally and the full journey
is testable without external services. Set `SLIDEIN_DATABASE_URL` (or
`DATABASE_URL`) to a `postgresql+asyncpg://` URL for deployment — the
model definition is identical.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base

DEFAULT_SQLITE = (
    Path(__file__).resolve().parents[2] / "data" / "slidein.db"
).as_posix()


def database_url() -> str:
    url = (
        os.getenv("SLIDEIN_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or f"sqlite+aiosqlite:///{DEFAULT_SQLITE}"
    )
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def make_engine(url: str | None = None):
    url = url or database_url()
    connect_args: dict = {}
    kwargs: dict = {"echo": False, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        path = url.split("///", 1)[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # File-backed SQLite is shared by the API, the tests and the CLI.
        # NullPool keeps every connection inside the event loop that made it.
        from sqlalchemy.pool import NullPool

        kwargs["poolclass"] = NullPool
    return create_async_engine(url, connect_args=connect_args, **kwargs)


engine = make_engine()
SessionFactory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Transactional unit of work. Commits on clean exit."""
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def reset_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
