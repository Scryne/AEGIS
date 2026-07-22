"""Worker DB erişimi — senkron engine/session (RLS'ye tabi app rolüyle bağlanır)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from aegis_core.db import (
    create_sync_engine,
    create_sync_session_factory,
    set_tenant_context_sync,
)

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_session_factory() -> sessionmaker[Session]:
    """Süreç başına tek (tembel) senkron session fabrikası döndürür."""
    global _engine, _factory
    if _factory is None:
        _engine = create_sync_engine()
        _factory = create_sync_session_factory(_engine)
    return _factory


@contextmanager
def tenant_session(tenant_id: uuid.UUID) -> Iterator[Session]:
    """RLS kiracı bağlamı kurulu, transaction'lı bir oturum açar (çıkışta commit)."""
    factory = get_session_factory()
    with factory() as session, session.begin():
        set_tenant_context_sync(session, tenant_id)
        yield session
