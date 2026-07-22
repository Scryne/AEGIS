"""Kiracı (tenant) bağlamı — RLS için PostgreSQL oturum değişkeni yönetimi.

Aktif kiracı, ``app.current_tenant`` GUC'una **transaction-local** olarak yazılır;
RLS politikaları bu değeri kullanır. Local olması (üçüncü argüman ``true``), bağlantı
havuzunda bir isteğin kiracısının başka bir isteğe sızmasını yapısal olarak önler.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

TENANT_SETTING = "app.current_tenant"


async def set_tenant_context(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Aktif transaction için RLS kiracı bağlamını ayarlar (transaction-local).

    Aynı transaction içinde çağrılmalıdır (ör. ``async with session.begin(): ...``).
    """
    await session.execute(
        text("SELECT set_config(:key, :value, true)"),
        {"key": TENANT_SETTING, "value": str(tenant_id)},
    )


def set_tenant_context_sync(session: Session, tenant_id: uuid.UUID) -> None:
    """``set_tenant_context``'in senkron eşleniği (Celery worker oturumları için)."""
    session.execute(
        text("SELECT set_config(:key, :value, true)"),
        {"key": TENANT_SETTING, "value": str(tenant_id)},
    )
