"""TenantSetting servisi — kiracı-özel yapılandırma okuma/yazma (RLS'ye tabi oturum).

Bu servis her zaman *tenant bağlamı ayarlı* bir oturumla çağrılır; RLS zaten
kiracıyı zorlar. Yine de ``tenant_id`` açıkça yazılır (WITH CHECK ile tutarlı).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.models import TenantSetting


async def list_settings(session: AsyncSession) -> list[TenantSetting]:
    """Aktif kiracının tüm ayarlarını döndürür (RLS yalnız kendi kiracısını gösterir)."""
    result = await session.scalars(select(TenantSetting).order_by(TenantSetting.key))
    return list(result)


async def get_setting(session: AsyncSession, key: str) -> TenantSetting | None:
    """Anahtara göre tek ayar döndürür (kiracı RLS ile sınırlı)."""
    setting: TenantSetting | None = await session.scalar(
        select(TenantSetting).where(TenantSetting.key == key)
    )
    return setting


async def upsert_setting(
    session: AsyncSession, *, tenant_id: uuid.UUID, key: str, value: dict[str, Any]
) -> TenantSetting:
    """Ayarı oluşturur veya günceller (kiracı başına anahtar tekildir)."""
    existing = await get_setting(session, key)
    if existing is not None:
        existing.value = value
        await session.flush()
        return existing
    setting = TenantSetting(tenant_id=tenant_id, key=key, value=value)
    session.add(setting)
    await session.flush()
    return setting
