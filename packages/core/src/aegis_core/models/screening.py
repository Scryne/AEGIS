"""Tarama kayıtları — ``Screening`` (koşu) + ``MatchCandidate`` (aday eşleşme), E1.3.

İkisi de kiracıya-özel *veri* tablosudur → ``TenantMixin`` + ENABLE/FORCE RLS
(bkz. migration 0003, Invariant 1).

**Neden özne anlık görüntüsü (snapshot) saklanır?** Varlık kütüğü (``Entity``) E1.4'te
gelir. Tarama ondan önce çalışabilmelidir; ayrıca çalışabilmesi *gerekir*: bir tarama,
"o an neyi taradık" sorusuna kendi başına cevap verebilmelidir. Varlık adı sonradan
düzeltilse bile eski tarama, taranmış hâli göstermeye devam eder — denetim izinin
anlamı budur. ``entity_id`` kolonu E1.4'te bağ kurmak için baştan ayrılmıştır.

``Screening`` ``RetentionMixin`` taşır: tarama, dosyanın kanıtıdır ve KVKK saklama
saatine tabidir (Invariant 4).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
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


class ScreeningStatus(StrEnum):
    """Tarama koşusunun yaşam döngüsü."""

    QUEUED = "queued"
    """Derin koşu kuyruğa alındı (Celery); henüz başlamadı."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    """yente erişilemedi/hata verdi. Sonuç YOK demektir — 'temiz' ile karıştırılmamalı."""


class SubjectRole(StrEnum):
    """Öznenin dosyadaki rolü (şirketin kendisi mi, yöneticisi mi, gerçek faydalanıcısı mı)."""

    SELF = "self"
    OFFICER = "officer"
    UBO = "ubo"
    SHAREHOLDER = "shareholder"


class Screening(UUIDPKMixin, TenantMixin, TimestampMixin, RetentionMixin, Base):
    """Bir tarama koşusu: girdi anlık görüntüsü + motor/veri kümesi sürümü + sonuç."""

    __tablename__ = "screening"
    __table_args__ = (
        # Panel ve dosya ekranı "bu kiracının son taramaları"nı sorar.
        Index("ix_screening_tenant_id_created_at", "tenant_id", "created_at"),
    )

    # ── Özne anlık görüntüsü ─────────────────────────────────────────────────
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    """``person`` | ``company`` (bkz. ``screening.normalization.SubjectType``)."""

    subject_name: Mapped[str] = mapped_column(String(512), nullable=False)
    """Birincil öznenin ham adı (kullanıcının girdiği hâliyle)."""

    subject_normalized: Mapped[str] = mapped_column(String(512), nullable=False)
    """Birincil öznenin kanonik adı — hangi normalizasyonla tarandığının kanıtı."""

    subject_country: Mapped[str | None] = mapped_column(String(8), nullable=True)

    subjects: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    """Taranan tüm öznelerin listesi (şirket + yöneticiler/UBO'lar), rolleriyle."""

    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    """E1.4'te ``entity`` tablosuna bağlanacak (şimdilik FK yok, kütük henüz yok)."""

    # ── Motor / veri kümesi provenansı (Invariant 4) ─────────────────────────
    dataset: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_versions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    """Koşu anındaki veri kümesi sürümleri — rapor "hangi listeye göre" der (E1.5)."""

    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    thresholds: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    """Koşu anındaki eşik bandı. Sonradan eşik değişirse eski karar yeniden yorumlanmaz."""

    # ── Durum ────────────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'queued'"), index=True
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Koşu süresi — NFR ölçümü (tek varlık özeti < 30 sn) buradan raporlanır."""

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    """Kaydedilen aday sayısı (koşudan sonra değişmez; karar sayıları sorguyla bulunur).

    **Adaylar bilinçli olarak ORM ilişkisiyle bağlanmaz.** Async oturumda tembel yükleme
    (``lazy load``) greenlet dışında IO denemesine yol açar; ayrıca yeni oluşturulmuş bir
    nesnede koleksiyona erişmek sessiz bir ek sorgu doğururdu. Adaylar her zaman açık
    sorguyla çekilir: ``screening.service.list_candidates``. Silme, FK'nın ``ON DELETE
    CASCADE``ıyla veritabanında olur.
    """


class MatchCandidate(UUIDPKMixin, TenantMixin, TimestampMixin, Base):
    """Bir taramada bulunan aday eşleşme + insan kararı (HITL).

    Aday **silinmez**: otomatik elenenler de saklanır, çünkü dosya raporu "gerekçesiyle
    elenen eşleşmeler"i göstermek zorundadır (E1.5, MASAK denetiminde savunmanın parçası).
    """

    __tablename__ = "match_candidate"
    __table_args__ = (
        # Aynı özne için aynı dış varlık iki kez kaydedilmez (yeniden koşu idempotent).
        UniqueConstraint(
            "screening_id",
            "subject_key",
            "external_id",
            name="uq_match_candidate_screening_id_subject_key_external_id",
        ),
        Index("ix_match_candidate_tenant_id_decision", "tenant_id", "decision"),
    )

    screening_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("screening.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── Hangi özneden geldi ──────────────────────────────────────────────────
    subject_key: Mapped[str] = mapped_column(String(64), nullable=False)
    """Koşu içindeki özne anahtarı (yente sorgu anahtarıyla aynı)."""

    subject_name: Mapped[str] = mapped_column(String(512), nullable=False)
    subject_role: Mapped[str] = mapped_column(String(16), nullable=False)

    # ── Dış varlık (yente/OpenSanctions) ─────────────────────────────────────
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    caption: Mapped[str] = mapped_column(String(512), nullable=False)
    schema_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """FtM şeması (``Person``, ``Company`` …). ``schema`` SQLAlchemy'de ayrılmış addır."""

    score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    engine_matched: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    """yente'nin kendi eşik kararı (bizim bandımızdan bağımsız; kıyas için saklanır)."""

    datasets: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    topics: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    countries: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    features: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    """"Neden eşleşti": skoru oluşturan özellik→ağırlık kırılımı (şeffaflık gereği)."""

    properties: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    """Dış varlığın özellik anlık görüntüsü (doğum tarihi, uyruk, program …)."""

    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    """Kanıt bağlantısı (Invariant 4) — raporda her bulgunun altında görünür."""

    # ── Karar (HITL) ─────────────────────────────────────────────────────────
    band: Mapped[str] = mapped_column(String(16), nullable=False)
    decision: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    decided_automatically: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Eleme gerekçesi — MASAK denetiminde "neden elendi" sorusunun cevabı."""
