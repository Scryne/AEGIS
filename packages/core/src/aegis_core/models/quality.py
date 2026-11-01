"""Eşleşme kalitesi ölçüm kaydı — ``MatchEvalRun`` (E3.6, ADR-0017).

Her satır, o anki eşiklerle insan kararlarından hesaplanan metriklerin donmuş kopyasıdır; eğilim
("yanlış pozitif ve inceleme oranı en az iki ayar turunda düşüyor" çıkış ölçütü) bu satırlardan
okunur. Kiracıya özel veri tablosu → ``TenantMixin`` + ENABLE/FORCE RLS (migration 0015).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base
from aegis_core.db.mixins import TenantMixin, UUIDPKMixin


class MatchEvalRun(UUIDPKMixin, TenantMixin, Base):
    __tablename__ = "match_eval_run"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), index=True
    )
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    label_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
