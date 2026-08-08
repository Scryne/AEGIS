"""Varlık kütüğü — ``Entity``, ``EntityAttribute``, ``Relationship`` (E1.4).

FollowTheMoney (FtM) hizalı: varlıklar ``Person`` ya da ``Company``, aralarındaki bağlar
``Relationship``. Üçü de kiracıya-özel *veri* tablosudur → ``TenantMixin`` + ENABLE/FORCE
RLS (bkz. migration 0004, Invariant 1).

**Neden ayrı bir öznitelik tablosu var?** ROADMAP E1.4: *"provenance on every attribute
(source + timestamp)"*. Bunu yalnız ``entity`` kolonlarıyla karşılamak mümkün değildir,
çünkü tutarsızlık tespiti (declared vs. extracted/registry) aynı özniteliğin **birden çok
gözlemini** gerektirir: müşterinin beyan ettiği adres ile faaliyet belgesindeki adres iki
ayrı satırdır ve ikisi de kaynağıyla saklanmalıdır. ``entity`` satırı "şu an geçerli
kabul ettiğimiz değer"i, ``entity_attribute`` satırları "kim, ne zaman, nereden söyledi"yi
taşır.

**TCKN şifrelidir** (ADR-0005): ``national_id`` ``EncryptedString``, aramak için de
``national_id_fingerprint`` (anahtarlı HMAC kör indeksi) vardır. Vergi/MERSİS/LEI
numaraları tüzel kişilerin kamuya açık kütük tanımlayıcılarıdır ve düz saklanır — ki
varlık çözümlemesi (ER) bunlar üzerinde deterministik eşleşme yapabilsin.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
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
from aegis_core.security.encryption import EncryptedString

# Kör indeks alan ayrımı (bkz. security.encryption.blind_index).
NATIONAL_ID_DOMAIN = "entity.national_id"


class EntitySchema(StrEnum):
    """FtM şeması — Phase 1'de yalnız iki tür."""

    PERSON = "Person"
    COMPANY = "Company"


class EntityStatus(StrEnum):
    """Varlığın kütükteki durumu."""

    ACTIVE = "active"
    MERGED = "merged"
    """Varlık çözümlemesiyle başka bir kayda birleştirildi; ``merged_into_id`` doludur.

    Kayıt **silinmez**: eski taramalar ve belgeler ona bağlıdır ve denetim izi
    "o gün hangi kaydı gördük" sorusuna cevap verebilmelidir.
    """


class SourceType(StrEnum):
    """Bir gözlemin nereden geldiği — provenansın çekirdeği (Invariant 4)."""

    DECLARED = "declared"
    """Müşteri/kullanıcı beyanı (manuel giriş)."""

    DOCUMENT = "document"
    """Yüklenen belgeden çıkarıldı (imza sirküleri, faaliyet belgesi …)."""

    REGISTRY = "registry"
    """Resmî kütük (Ticaret Sicil Gazetesi). MERSİS Phase 1'de YOKTUR (Revizyon R1)."""

    GLEIF = "gleif"
    """Kamuya açık GLEIF LEI kütüğü."""

    SCREENING = "screening"
    """Tarama sonucundan türeyen bilgi."""


class RelationshipType(StrEnum):
    """İki varlık arasındaki bağ türü.

    ``UBO`` burada yalnız **beyan/tespit edilmiş** gerçek faydalanıcıyı işaretler;
    ortaklık zincirinden UBO **hesaplama** (özyinelemeli CTE, %25 eşiği, döngü tespiti)
    Phase 2'nin işidir ve bu fazda yapılmaz.
    """

    OFFICER = "officer"
    SHAREHOLDER = "shareholder"
    UBO = "ubo"
    FAMILY = "family"
    CONTROL = "control"
    REPRESENTATIVE = "representative"


class Entity(UUIDPKMixin, TenantMixin, TimestampMixin, RetentionMixin, Base):
    """Bir gerçek ya da tüzel kişi (FtM ``Person`` / ``Company``)."""

    __tablename__ = "entity"
    __table_args__ = (
        Index("ix_entity_tenant_id_schema_type", "tenant_id", "schema_type"),
        # Deterministik tanımlayıcılar kiracı içinde tekildir: aynı vergi numarası iki
        # ayrı varlığa bağlanamaz (ER'in "birleştir-ya-da-oluştur" güvencesi DB'de de).
        UniqueConstraint("tenant_id", "tax_number", name="uq_entity_tenant_id_tax_number"),
        UniqueConstraint("tenant_id", "mersis_number", name="uq_entity_tenant_id_mersis_number"),
        UniqueConstraint("tenant_id", "lei_code", name="uq_entity_tenant_id_lei_code"),
        UniqueConstraint(
            "tenant_id",
            "national_id_fingerprint",
            name="uq_entity_tenant_id_national_id_fingerprint",
        ),
    )

    schema_type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    """Şu an geçerli kabul edilen ad (unvan)."""

    name_normalized: Mapped[str] = mapped_column(String(512), nullable=False)
    """Türkçe kanonik ad (``screening.normalization``) — tarama ile AYNI fonksiyondan."""

    name_ascii: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    """ASCII biçim — ``pg_trgm`` bulanık eşleşmesinin çalıştığı kolon (ER v1, R4)."""

    # ── Deterministik tanımlayıcılar (ER'in birincil anahtarları) ────────────
    tax_number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    mersis_number: Mapped[str | None] = mapped_column(String(24), nullable=True)
    lei_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    trade_registry_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """Ticaret sicil numarası — tekil kısıt YOK: farklı sicil dairelerinde tekrar edebilir."""

    # ── Kişisel veri (KVKK, ADR-0005) ────────────────────────────────────────
    national_id: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    """TCKN — AES-256-GCM ile şifreli saklanır; DB dökümünde düz metin görünmez."""

    national_id_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """``blind_index(tckn)`` — şifreli alanda eşitlik araması için (ADR-0005)."""

    # ── Tanımlayıcı olmayan öznitelikler (şu anki geçerli değerler) ──────────
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    incorporation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'active'"), index=True
    )
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class EntityAttribute(UUIDPKMixin, TenantMixin, TimestampMixin, Base):
    """Bir özniteliğin **tek bir gözlemi**, kaynağıyla birlikte (Invariant 4).

    Aynı öznitelik için birden çok satır normaldir ve istenen durumdur: beyan bir satır,
    belgeden çıkan bir satır, kütükten gelen bir satır. Tutarsızlık tespiti (``discrepancy``)
    tam olarak bu satırları karşılaştırır.
    """

    __tablename__ = "entity_attribute"
    __table_args__ = (
        Index("ix_entity_attribute_entity_id_name", "entity_id", "name"),
        # Aynı kaynaktan gelen aynı değer iki kez yazılmaz (yeniden çıkarım idempotent).
        UniqueConstraint(
            "entity_id",
            "name",
            "value",
            "source_type",
            name="uq_entity_attribute_entity_id_name_value_source_type",
        ),
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    """FtM özellik adı (``name``, ``address``, ``taxNumber``, ``incorporationDate`` …)."""

    value: Mapped[str] = mapped_column(Text, nullable=False)
    """Gözlemin metin değeri. Hassas değerler burada TUTULMAZ (bkz. sınıf notu)."""

    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    """Kanıt bağlantısı: belge adı/sayfası, gazete URL'i, GLEIF kaydı."""

    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("document.id", ondelete="SET NULL"), nullable=True, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    """Bu gözlem ``entity`` satırındaki geçerli değere mi karşılık geliyor."""


class Relationship(UUIDPKMixin, TenantMixin, TimestampMixin, Base):
    """İki varlık arasındaki bağ (yönetici, ortak, UBO, aile, kontrol).

    Yön: ``source`` → ``target``. Örnek: "Ahmet Yılmaz **şirketin** yöneticisidir" satırı
    ``source=Ahmet``, ``target=Şirket``, ``rel_type=officer`` olarak yazılır.
    """

    __tablename__ = "relationship"
    __table_args__ = (
        Index("ix_relationship_tenant_id_target_entity_id", "tenant_id", "target_entity_id"),
        UniqueConstraint(
            "source_entity_id",
            "target_entity_id",
            "rel_type",
            "role_title",
            name="uq_relationship_source_target_type_role",
        ),
    )

    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rel_type: Mapped[str] = mapped_column(String(24), nullable=False)
    role_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    """Unvan/yetki metni ("Yönetim Kurulu Başkanı", "münferiden temsile yetkili")."""

    ownership_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    """Ortaklık payı (%). Phase 2'de UBO hesabının girdisi olacak; burada yalnız saklanır."""

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("document.id", ondelete="SET NULL"), nullable=True
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
