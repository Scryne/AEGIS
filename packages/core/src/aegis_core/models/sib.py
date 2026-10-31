"""ŞİB taslağı — ``SibDraft`` (E2.2, ADR-0011).

MASAK'a yapılacak şüpheli işlem bildiriminin **taslağı**dır; resmî gönderim yükümlünün MASAK
Online'da yaptığı iştir. Form içeriği kişisel veri (TCKN, adres, anne/baba adı) taşıdığı için
tek bir şifreli metin olarak saklanır (ADR-0005); listeleme için gereken iki alan (kategori,
durum) düz kolondadır ve kişisel veri içermez.

Bildirimin varlığı da gizlidir (5549 s.K. m.4/2): satırlar yalnız ``owner`` ve
``compliance_officer`` rollerine açılır (router). Kiracıya özel veri tablosu → ``TenantMixin``
+ ENABLE/FORCE RLS (migration 0009). Bildirim belgesi ≥5 yıl saklanır (Invariant 4).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin
from aegis_core.db.mixins import RetentionMixin, TenantMixin, UUIDPKMixin
from aegis_core.security.encryption import EncryptedString


class SibStatus(StrEnum):
    DRAFT = "taslak"
    EXPORTED = "disa_aktarildi"
    CANCELLED = "iptal"


class SibDraft(UUIDPKMixin, TenantMixin, TimestampMixin, RetentionMixin, Base):
    """Bir varlık için hazırlanan ŞİB taslağı."""

    __tablename__ = "sib_draft"
    __table_args__ = (UniqueConstraint("tenant_id", "reference_no"),)

    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reference_no: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'taslak'"), index=True
    )
    category: Mapped[str | None] = mapped_column(String(8), nullable=True)
    form_encrypted: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    skeleton_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    guide_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    export_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_exported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
