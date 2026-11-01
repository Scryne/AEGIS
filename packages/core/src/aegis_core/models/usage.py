"""Ay sonu kullanım dökümü — ``UsageStatement`` (E3.5, ADR-0018).

Bir dönemin (İstanbul takvim ayı) ölçülen işi donmuş olarak: plan, dahil kota, kullanılan sorgu,
aşım, izlenen varlık, kaynağa göre döküm. Fiyat yoktur (ticari karar, sözleşmede). Kiracıya özel
veri tablosu → ``TenantMixin`` + ENABLE/FORCE RLS (migration 0016); dönem başına tek satır.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base
from aegis_core.db.mixins import TenantMixin, UUIDPKMixin


class UsageStatement(UUIDPKMixin, TenantMixin, Base):
    __tablename__ = "usage_statement"
    __table_args__ = (UniqueConstraint("tenant_id", "period_start"),)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    included_queries: Mapped[int] = mapped_column(Integer, nullable=False)
    used_queries: Mapped[int] = mapped_column(Integer, nullable=False)
    overage_queries: Mapped[int] = mapped_column(Integer, nullable=False)
    monitored_entities: Mapped[int] = mapped_column(Integer, nullable=False)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
