"""API anahtarı ve webhook'lar (E3.4, ADR-0016).

* ``ApiKey`` — **kimlik denetim düzlemi** tablosudur (``organization``/``membership`` gibi):
  istek geldiğinde kiracı bağlamı henüz yoktur, anahtar önekle aranır. Bu yüzden RLS'siz; her uç
  ``principal.tenant_id`` ile uygulama kodunda süzer (ADR-0002'deki istisnanın aynısı). Gizli
  kısım saklanmaz, yalnız SHA-256 özeti.
* ``WebhookEndpoint``, ``WebhookDelivery`` — kiracıya özel **veri** tabloları → ``TenantMixin`` +
  ENABLE/FORCE RLS (migration 0014). İmza sırrı şifreli (ADR-0005). Teslim yükü kişisel veri
  taşımaz: yalnız kimlikler ve durumlar; ayrıntı API'den çekilir.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin
from aegis_core.db.mixins import TenantMixin, UUIDPKMixin
from aegis_core.security.encryption import EncryptedString


class ApiKey(UUIDPKMixin, Base):
    __tablename__ = "api_key"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    prefix: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    key_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class WebhookEndpoint(UUIDPKMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "webhook_endpoint"

    url: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    secret: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    events: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class WebhookDelivery(UUIDPKMixin, TenantMixin, Base):
    __tablename__ = "webhook_delivery"
    __table_args__ = (Index("ix_webhook_delivery_status_next", "status", "next_attempt_at"),)

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("webhook_endpoint.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
