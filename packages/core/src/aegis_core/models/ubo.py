"""UBO hesap anlık görüntüsü — ``UboComputation`` (E2.1).

ROADMAP E2.1: *"UBO computation snapshots persisted with inputs + timestamp (audit: 'what
did we know when we decided')"*. Her hesap, kullandığı kenarların ve düğümlerin donmuş bir
kopyasıyla birlikte saklanır; kütük sonradan değişse de eski karar yeniden yorumlanmaz
(``screening``/``report`` satırlarındaki aynı duruş — ADR-0006). ``input_sha256`` girdilerin
kanonik JSON'unun özetidir: aynı girdiyle yeniden hesap aynı özeti verir.

Kiracıya-özel *veri* tablosudur → ``TenantMixin`` + ENABLE/FORCE RLS (migration 0006,
Invariant 1) ve ``RetentionMixin`` (karar kanıtıdır, Invariant 4).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin
from aegis_core.db.mixins import RetentionMixin, TenantMixin, UUIDPKMixin


class UboComputation(UUIDPKMixin, TenantMixin, TimestampMixin, RetentionMixin, Base):
    """Bir şirket için yapılmış tek bir UBO hesabı (değiştirilmez; yeni hesap yeni satır)."""

    __tablename__ = "ubo_computation"
    __table_args__ = (Index("ix_ubo_computation_entity_id_created_at", "entity_id", "created_at"),)

    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    threshold_percent: Mapped[Any] = mapped_column(Numeric(7, 4), nullable=False)
    threshold_inclusive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    """``compute.UboResult.to_dict()`` — UBO'lar, yollar, döngüler, çözülemeyenler."""

    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    """Hesabın gördüğü düğümler ve kenarlar (kanonik, sıralı)."""

    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    computed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
