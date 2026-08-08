"""Belgeler ve çıkarım önerileri — ``Document``, ``ExtractionProposal`` (E1.4).

Revizyon R2: belge çıkarımı Phase 1'e alındı, **iki belge türüyle sınırlı** (imza
sirküleri, faaliyet belgesi). Revizyon R1: kütük entegrasyonu (MERSİS) Phase 1'de yok;
Ticaret Sicil Gazetesi "kılavuzlu manuel ekleme" olarak aynı belge hattından geçer.

**Çıkarım hiçbir zaman doğrudan kütüğe yazmaz.** Docling'in bulduğu her şey bir
``ExtractionProposal`` satırıdır ve varlık grafiğine girmesi için insan onayı gerekir
(R2'nin açık koşulu: *"suggested officers/owners as proposals requiring user
confirmation"*). Gerekçe ürünün duruşuyla aynı: AEGIS kararı belgeler, vermez —
OCR'ın okuduğu bir ismi sessizce "şirketin yöneticisi" yapmak bu duruşu bozardı.

``Document`` ``RetentionMixin`` taşır: yüklenen her belge KVKK saklama saatine tabidir
(Invariant 4, ≥5 yıl).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
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


class DocumentType(StrEnum):
    """Desteklenen belge türleri (R2: kapsam bilinçli olarak dar)."""

    IMZA_SIRKULERI = "imza_sirkuleri"
    FAALIYET_BELGESI = "faaliyet_belgesi"
    TICARET_SICIL_GAZETESI = "ticaret_sicil_gazetesi"
    """Kılavuzlu manuel ekleme (R1): kullanıcı gazete PDF'ini ve kaynak referansını verir."""

    OTHER = "other"
    """Çıkarım denenmez; yalnız saklanır ve dosyaya kanıt olarak eklenir."""


class ExtractionStatus(StrEnum):
    """Belgeden çıkarımın durumu."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    """Bu belge türü için çıkarım tanımlı değil (``other``) ya da motor kurulu değil."""


class ProposalKind(StrEnum):
    """Önerinin neye dair olduğu."""

    ATTRIBUTE = "attribute"
    """Varlığın bir özniteliği (adres, vergi no, kuruluş tarihi …)."""

    RELATIONSHIP = "relationship"
    """Bir kişi–şirket bağı (yönetici, ortak)."""


class ProposalStatus(StrEnum):
    """Önerinin insan incelemesindeki durumu."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Document(UUIDPKMixin, TenantMixin, TimestampMixin, RetentionMixin, Base):
    """Yüklenmiş bir belge (nesne deposunda saklanır, meta burada)."""

    __tablename__ = "document"
    __table_args__ = (
        Index("ix_document_tenant_id_created_at", "tenant_id", "created_at"),
        # Aynı dosya aynı varlığa iki kez yüklenmez (içerik özeti üzerinden).
        UniqueConstraint("tenant_id", "entity_id", "sha256", name="uq_document_tenant_entity_sha"),
    )

    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="CASCADE"), nullable=True, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    """İçerik özeti — bütünlük kanıtı ve tekilleştirme anahtarı."""

    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    """Nesne deposundaki anahtar. Dosyanın kendisi ASLA veritabanında tutulmaz."""

    source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    """Belgenin dış kaynağı (ör. Ticaret Sicil Gazetesi sayı/tarih/URL bilgisi)."""

    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    extraction_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'"), index=True
    )
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """Hangi motorla çıkarıldı (``docling``, ``text``) — sonuçların kıyaslanabilirliği için."""


class ExtractionProposal(UUIDPKMixin, TenantMixin, TimestampMixin, Base):
    """Belgeden çıkan, **insan onayı bekleyen** bir öneri.

    Kabul edilene kadar varlık grafiğini etkilemez. Reddedilen öneri de silinmez:
    "belgede bu yazıyordu ama uzman kabul etmedi" bilgisi denetimde anlamlıdır.
    """

    __tablename__ = "extraction_proposal"
    __table_args__ = (Index("ix_extraction_proposal_tenant_id_status", "tenant_id", "status"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    """Önerinin içeriği: öznitelik için ``{name, value}``; ilişki için ``{person_name,
    rel_type, role_title, ownership_percent, national_id?}``."""

    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    """0..1 — kontrol basamağı tutan bir vergi no, tutmayandan yüksek güven alır."""

    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Belgedeki kaynak metin parçası — kullanıcı kararını buna bakarak verir."""

    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resulting_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True
    )
    """Kabul edilince oluşan/eşleşen varlık — öneriden kütüğe giden izin ucu."""
