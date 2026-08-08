"""Tutarsızlık kaydı — beyan ile belge/kütük verisinin çelişmesi (E1.4).

ROADMAP E1.4: *"declared vs. extracted/registry data mismatches surfaced on profile +
report (MASAK suspicious-transaction precondition)"*. Bu tablo ürünün MASAK açısından en
anlamlı çıktılarından biridir: müşterinin beyan ettiği adres ile faaliyet belgesindeki
adresin tutmaması, tek başına suç değildir ama **açıklanması gereken** bir bulgudur ve
dosyada görünmelidir.

Tutarsızlık **kapatılmaz, karara bağlanır**: kullanıcı ya açıklamayı kabul eder
(``accepted``, gerekçesiyle) ya da düzeltir (``resolved``). Kayıt her hâlükârda durur —
dosya raporu (E1.5) "bu dosyada şu tutarsızlık vardı, şöyle açıklandı" diyebilmelidir.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin
from aegis_core.db.mixins import TenantMixin, UUIDPKMixin


class DiscrepancyStatus(StrEnum):
    """Tutarsızlığın karar durumu."""

    OPEN = "open"
    ACCEPTED = "accepted"
    """Fark açıklandı ve kabul edildi (gerekçe zorunlu)."""

    RESOLVED = "resolved"
    """Veri düzeltildi; fark ortadan kalktı."""


class DiscrepancySeverity(StrEnum):
    """Bulgunun ağırlığı — risk özetinde (E1.5) sıralamayı belirler."""

    INFO = "info"
    """Biçimsel fark (ör. adres yazımı) — bilgi amaçlı."""

    WARNING = "warning"
    """Anlamlı fark (ör. farklı adres, farklı kuruluş tarihi)."""

    CRITICAL = "critical"
    """Kimlik tanımlayıcısında fark (vergi no / MERSİS / TCKN) — kimlik şüphesi."""


class Discrepancy(UUIDPKMixin, TenantMixin, TimestampMixin, Base):
    """Bir öznitelikte beyan ile gözlem arasındaki fark."""

    __tablename__ = "discrepancy"
    __table_args__ = (
        Index("ix_discrepancy_tenant_id_status", "tenant_id", "status"),
        # Aynı fark tekrar tekrar üretilmez (çıkarım/zenginleştirme idempotent olsun).
        UniqueConstraint(
            "entity_id",
            "attribute_name",
            "declared_value",
            "observed_value",
            name="uq_discrepancy_entity_attribute_values",
        ),
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attribute_name: Mapped[str] = mapped_column(String(64), nullable=False)

    declared_value: Mapped[str] = mapped_column(Text, nullable=False)
    declared_source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    observed_value: Mapped[str] = mapped_column(Text, nullable=False)
    observed_source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("document.id", ondelete="SET NULL"), nullable=True
    )

    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'open'"))
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
