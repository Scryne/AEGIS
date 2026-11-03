"""İzleme alarmı — ``MonitoringAlert`` (E2.4).

İzlenen bir varlığın gece yeniden taramasında önceki koşuya göre **önemli** bir fark çıktığında
bir satır yazılır: yeni eşleşme, onaylanmış eşleşmenin listeden çıkması ya da liste kaydının
konu etiketlerinin değişmesi. Alarm silinmez; görüldüğünde gerekçeyle ``acknowledged`` olur
(tam vaka yönetimi Phase 3).

E3.1 (migration 0012): ``severity`` (``monitoring/severity.py``) ve ``reassessment`` (alarm anında
kayda geçen risk puanı: önceki/sonraki). 0012 öncesi satırlarda ikisi de boştur; okuma tarafı
dereceyi farktan yeniden hesaplar.

Kiracıya-özel *veri* tablosudur → ``TenantMixin`` + ENABLE/FORCE RLS (migration 0008).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid, text
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
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    reassessment: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # E-posta sunucusu iletiyi kabul ettiği an; None ise sonraki bildirim turunda yeniden denenir.
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MonitoringRun(UUIDPKMixin, TenantMixin, Base):
    """Bir izleme koşusunun özeti. Taranamayan varlık burada kalır; hata yalnız log satırı olmaz."""

    __tablename__ = "monitoring_run"
    __table_args__ = (Index("ix_monitoring_run_tenant_started", "tenant_id", "started_at"),)

    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    checked: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False)
    alerts: Mapped[int] = mapped_column(Integer, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, nullable=False)
    retried: Mapped[int] = mapped_column(Integer, nullable=False)
    failures: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    stages: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
