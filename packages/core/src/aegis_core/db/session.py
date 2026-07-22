"""SQLAlchemy engine ve session fabrikaları (async API + sync worker)."""

from __future__ import annotations

from sqlalchemy import Engine
from sqlalchemy import create_engine as _sa_create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from aegis_core.config import Settings, get_settings


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    """Ayarlardaki ``DATABASE_URL`` ile bir async engine üretir (RLS'ye tabi app rolü)."""
    resolved = settings or get_settings()
    return create_async_engine(
        resolved.database_url,
        pool_pre_ping=True,
        future=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Verilen engine için bir async session fabrikası üretir."""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def create_sync_engine(settings: Settings | None = None) -> Engine:
    """Senkron engine (Celery worker) — aynı ``DATABASE_URL`` (RLS'ye tabi app rolü)."""
    resolved = settings or get_settings()
    return _sa_create_engine(
        resolved.database_url,
        pool_pre_ping=True,
        future=True,
    )


def create_sync_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Verilen senkron engine için bir session fabrikası üretir."""
    return sessionmaker(engine, expire_on_commit=False)
