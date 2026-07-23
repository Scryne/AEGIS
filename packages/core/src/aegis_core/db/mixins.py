"""Ortak ORM mixin'leri: UUID birincil anahtar, kiracı kolonu ve saklama süresi."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPKMixin:
    """UUID birincil anahtar (DB tarafında ``gen_random_uuid()`` ile üretilir).

    Not: ``gen_random_uuid()`` PostgreSQL 13+ çekirdeğinde yerleşiktir; ekstra
    uzantı (pgcrypto) gerekmez.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )


class TenantMixin:
    """Kiracıya-özel *veri* tabloları için ``tenant_id`` (PostgreSQL RLS ile zorlanır).

    Bu mixin'i taşıyan her tablo, migration'ında ENABLE+FORCE RLS ve kiracı izolasyon
    politikasını da almalıdır (bkz. CLAUDE.md, ADR-0002). Kimlik/kontrol-düzlemi
    tabloları (organization/user_account/membership) bu mixin'i taşımaz ve RLS'siz kalır.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class RetentionMixin:
    """Saklama süresi (``retention_until``) — KVKK ≥5 yıl (Invariant 4).

    Belge/dosya tabloları (E1.4/E1.5) bu kolonu **doğuşundan** taşır; süresi geçmiş
    kayıtları, E3.7'de gerçek silmeye dönüşecek zamanlanmış imha job'ı (şimdilik kuru
    çalışma; bkz. ``aegis_worker.tasks.retention``) temizler. NULL = süre işletilmemiş
    (ör. henüz aktif ilişki). Saklama süresi ``document_retention_years`` ile hesaplanır.
    """

    retention_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
