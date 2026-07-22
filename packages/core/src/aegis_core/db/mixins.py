"""Ortak ORM mixin'leri: UUID birincil anahtar ve kiracı (tenant) kolonu."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Uuid, func
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
