"""TenantSetting — kiracı-özel yapılandırma (ilk RLS'li *veri* tablosu).

E1.1'de RLS desenini migration 0001'den itibaren gerçek bir uçla kilitlemek için
vardır; ileride kiracı yapılandırmasını tutar (E1.2 saklama süresi, E1.3 tarama
eşikleri). Kiracıya-özeldir → ``TenantMixin`` + ENABLE/FORCE RLS (bkz. migration 0001).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin
from aegis_core.db.mixins import TenantMixin, UUIDPKMixin


class TenantSetting(UUIDPKMixin, TenantMixin, TimestampMixin, Base):
    """Kiracı başına anahtar/değer yapılandırma kaydı."""

    __tablename__ = "tenant_setting"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_tenant_setting_tenant_id"),)

    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
