"""Üretilmiş dosya raporu — ``Report`` (E1.5).

Kiracıya-özel *veri* tablosudur → ``TenantMixin`` + ENABLE/FORCE RLS (migration 0005,
Invariant 1). ``RetentionMixin`` taşır: dışa aktarılmış dosya, müşteri tanıma
yükümlülüğünün **kanıtıdır** ve KVKK saklama saatine tabidir (Invariant 4, ≥5 yıl).

**Neden dosyanın kendisi saklanıyor?** ROADMAP E1.5: *"Dossiers stored under retention
policy with hash for integrity evidence"*. Rapor her istendiğinde yeniden üretilseydi,
"denetime sunduğum belge buydu" iddiası kanıtlanamazdı: aradan geçen sürede kütük
değişir, eşikler değişir, veri kümesi güncellenir. Bu yüzden dosya nesne deposunda
donar ve ``sha256`` bütünlük kanıtı olarak burada durur — sunulan PDF ile saklanan
PDF'in aynı olduğu gösterilebilir.

**Provenans koşu anında donar.** ``risk_level``, ``risk_findings`` ve
``dataset_versions`` rapor üretildiği andaki hâlleriyle yazılır. Sonradan eşik ya da
veri kümesi değişirse eski rapor yeniden yorumlanmaz (``screening`` satırındaki aynı
duruş — ADR-0006).

Dosyanın kendisi **asla veritabanında tutulmaz**; nesne deposundadır (bkz.
``documents.storage`` modül başlığı).
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin
from aegis_core.db.mixins import RetentionMixin, TenantMixin, UUIDPKMixin


class ReportType(StrEnum):
    """Rapor türü. Phase 1'de tek tür vardır; ŞİB taslağı Phase 2'dir."""

    DOSSIER = "dossier"
    """Müşteri tanıma / durum tespiti dosyası."""


class ReportFormat(StrEnum):
    """Dışa aktarma biçimi (ROADMAP E1.5: PDF + Word)."""

    PDF = "pdf"
    DOCX = "docx"


REPORT_CONTENT_TYPES: dict[str, str] = {
    ReportFormat.PDF.value: "application/pdf",
    ReportFormat.DOCX.value: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
}


class Report(UUIDPKMixin, TenantMixin, TimestampMixin, RetentionMixin, Base):
    """Dışa aktarılmış bir dosya raporu (meta + bütünlük kanıtı)."""

    __tablename__ = "report"
    __table_args__ = (
        # Varlık ekranı "bu dosyanın raporları"nı, rapor listesi ise kiracının
        # tüm raporlarını en yeniden eskiye sorar.
        Index("ix_report_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_report_entity_id_created_at", "entity_id", "created_at"),
    )

    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("entity.id", ondelete="CASCADE"), nullable=True, index=True
    )
    report_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'dossier'")
    )
    report_format: Mapped[str] = mapped_column(String(8), nullable=False)
    """``format`` bilinçli olarak kullanılmadı: Python'da yerleşik ad gölgelemesi yaratır."""

    title: Mapped[str] = mapped_column(String(512), nullable=False)

    # ── Donmuş risk özeti (üretim anındaki hâli) ─────────────────────────────
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_rationale: Mapped[str] = mapped_column(String(1024), nullable=False)
    risk_findings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    """Kuralların ürettiği bulgular (kod + gerekçe + kanıt) — raporun savunması."""

    # ── Kapsam ve provenans (Invariant 4) ────────────────────────────────────
    screening_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    """Rapora giren tarama koşuları — "hangi koşuya dayanıyor" sorusunun cevabı."""

    dataset_versions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    """Koşuların veri kümesi sürümleri: "hangi listeye göre" (raporda basılır)."""

    # ── Saklanan dosya ───────────────────────────────────────────────────────
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    """Bütünlük kanıtı: sunulan dosya ile saklanan dosyanın aynı olduğunu gösterir."""

    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
