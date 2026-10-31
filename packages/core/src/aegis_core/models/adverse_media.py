"""Olumsuz haber adayı (E2.5 beta, ADR-0013).

Haberin kendisi saklanmaz: başlık, kaynak adı, bağlantı, yayın tarihi ve hangi sorguyla bulunduğu.
Aday, bir insan "ilgili" diyene kadar dosyaya bağlanmaz (HITL) ve risk puanına hiç girmez (E3.6
isabet ölçümü bitene kadar). Kiracıya özel veri → ``TenantMixin`` + RLS (göç 0011).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin
from aegis_core.db.mixins import TenantMixin, UUIDPKMixin


class AdverseMediaStatus(StrEnum):
    CANDIDATE = "aday"
    RELEVANT = "ilgili"
    IRRELEVANT = "ilgisiz"


class AdverseMediaItem(UUIDPKMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "adverse_media_item"
    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_id", "url_hash", name="uq_adverse_media_item_url"),
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    query: Mapped[str] = mapped_column(String(512), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    negative_terms: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, server_default=text("'{}'")
    )
    """Başlıkta geçen olumsuz terimler — sıralama ipucu, karar değil."""
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'aday'"), index=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
