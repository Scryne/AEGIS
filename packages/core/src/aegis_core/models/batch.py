"""Toplu tarama — ``ScreeningBatch`` + ``ScreeningBatchRow`` (E3.3, ADR-0015).

Bir CSV dosyasından gelen satırlar varlık çözümlemesinden (E1.4 ER) geçer, kütükte eşleşen
varlığa bağlanır ya da yeni varlık açılır, sonra varlık taraması koşar. Satır, girdisinin yalnız
eşlenen alanlarını taşır (TCKN alınmaz). İşleme parça parça ve sürdürülebilirdir: her satır kendi
alt işleminde ``pending`` → ``done`` / ``failed`` / ``needs_review`` olur; yarıda kalan bir koşu
kaldığı ``pending`` satırdan devam eder.

Kiracıya özel veri tabloları → ``TenantMixin`` + ENABLE/FORCE RLS (migration 0013).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin
from aegis_core.db.mixins import RetentionMixin, TenantMixin, UUIDPKMixin


class BatchStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RowStatus(StrEnum):
    INVALID = "invalid"
    DUPLICATE = "duplicate"
    PENDING = "pending"
    DONE = "done"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScreeningBatch(UUIDPKMixin, TenantMixin, TimestampMixin, RetentionMixin, Base):
    __tablename__ = "screening_batch"

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    column_map: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'draft'"), index=True
    )
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ScreeningBatchRow(UUIDPKMixin, TenantMixin, Base):
    __tablename__ = "screening_batch_row"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_no"),
        Index("ix_screening_batch_row_batch_id_status", "batch_id", "status"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("screening_batch.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    errors: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    duplicate_of: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(16), nullable=True)
    resolution_candidates: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True
    )
    screening_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("screening.id", ondelete="SET NULL"), nullable=True
    )
    candidate_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flagged_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sanction_hits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pep_hits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_rank: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
