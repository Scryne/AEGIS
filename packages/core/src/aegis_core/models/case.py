"""Uyum vakası — ``ComplianceCase`` + ``CaseComment`` (E3.2, ADR-0014).

Bir varlık hakkında karar gerektiren her konu bir vakadır: elle açılan, bir tarama
incelemesinden doğan ya da izleme alarmından otomatik açılan. Tablo adı ``compliance_case``
(``case`` SQL'de ayrılmış sözcük). Yaşam döngüsü ``cases/lifecycle.py``'dedir; her geçiş
denetim izine bir olay yazar, vaka geçmişi de oradan okunur (ayrı bir olay tablosu yok).

Yorumlar silinmez ve düzenlenmez. Kiracıya özel veri tabloları → ``TenantMixin`` +
ENABLE/FORCE RLS (migration 0012).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin
from aegis_core.db.mixins import TenantMixin, UUIDPKMixin


class ComplianceCase(UUIDPKMixin, TenantMixin, TimestampMixin, Base):
    """Bir varlık için açılmış uyum vakası."""

    __tablename__ = "compliance_case"
    __table_args__ = (Index("ix_compliance_case_tenant_id_status", "tenant_id", "status"),)

    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    source_alert_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("monitoring_alert.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,  # bir alarm en çok bir vaka açar (gece koşusu tekrarlansa bile)
    )
    source_screening_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("screening.id", ondelete="SET NULL"), nullable=True
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'new'"), index=True
    )
    edd: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    edd_template_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    edd_checklist: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    opened_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)


class CaseComment(UUIDPKMixin, TenantMixin, Base):
    """Vakaya eklenen yorum (silinmez, düzenlenmez)."""

    __tablename__ = "case_comment"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("compliance_case.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    author_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
