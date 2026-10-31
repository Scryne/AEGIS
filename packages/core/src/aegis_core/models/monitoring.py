"""İzleme alarmı — ``MonitoringAlert`` (E2.4).

İzlenen bir varlığın gece yeniden taramasında önceki koşuya göre **önemli** bir fark çıktığında
bir satır yazılır: yeni eşleşme, onaylanmış eşleşmenin listeden çıkması ya da liste kaydının
konu etiketlerinin değişmesi. Alarm silinmez; görüldüğünde gerekçeyle ``acknowledged`` olur
(tam vaka yönetimi Phase 3).

Kiracıya-özel *veri* tablosudur → ``TenantMixin`` + ENABLE/FORCE RLS (migration 0008).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin
from aegis_core.db.mixins import TenantMixin, UUIDPKMixin


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"


class MonitoringAlert(UUIDPKMixin, TenantMixin, TimestampMixin, Base):
    """Bir izleme koşusunun ürettiği fark alarmı."""

    __tablename__ = "monitoring_alert"
    __table_args__ = (Index("ix_monitoring_alert_tenant_id_status", "tenant_id", "status"),)

    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    screening_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("screening.id", ondelete="CASCADE"), nullable=False
    )
    previous_screening_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("screening.id", ondelete="SET NULL"), nullable=True
    )
    diff: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'open'"), index=True
    )
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledge_note: Mapped[str | None] = mapped_column(Text, nullable=True)
