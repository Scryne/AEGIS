"""Risk puanı anlık görüntüsü — ``RiskScoreSnapshot`` (E2.3).

ROADMAP E2.3: *"Score history timeline per entity"*. Canlı puan her okumada yeniden hesaplanır
(``GET /reports/score/{id}``) ve hiçbir şey yazmaz; anlık görüntü, yetkili bir kullanıcının
"bu puanı kayda geçir" eylemidir (ya da UBO hesabı gibi kütüğü etkileyen bir eylemin yan ürünü).
Böylece zaman çizelgesi, kimin hangi puanı ne zaman gördüğünü kanıtlar. Girdi özeti aynıysa
yeni satır yazılmaz: çizelge yalnız değişimleri taşır.

Kiracıya-özel *veri* tablosudur → ``TenantMixin`` + ENABLE/FORCE RLS (migration 0007).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin
from aegis_core.db.mixins import RetentionMixin, TenantMixin, UUIDPKMixin


class RiskScoreSnapshot(UUIDPKMixin, TenantMixin, TimestampMixin, RetentionMixin, Base):
    """Bir varlığın belli bir andaki risk puanı ve faktör dökümü (değiştirilmez)."""

    __tablename__ = "risk_score_snapshot"
    __table_args__ = (
        Index("ix_risk_score_snapshot_entity_id_created_at", "entity_id", "created_at"),
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    band: Mapped[str] = mapped_column(String(16), nullable=False)
    weights_version: Mapped[str] = mapped_column(String(16), nullable=False)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    """Anlık görüntünün nedeni: ``manual`` · ``ubo_compute``."""

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
