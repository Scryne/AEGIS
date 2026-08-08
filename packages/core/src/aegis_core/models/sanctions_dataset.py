"""SanctionsDataset — yaptırım veri kümesi tazelik durumu (E1.3).

**Neden RLS yok (bilinçli).** Bu tablo müşteri verisi değildir: kamuya açık yaptırım
veri kümelerinin katalog *meta*'sıdır (ad, sürüm, son dışa aktarım zamanı, varlık
sayısı). Kiracıya ait hiçbir bilgi taşımaz ve tüm kiracılar aynı motoru paylaşır —
kiracı başına kopyalamak yanlış olurdu. Kimlik/kontrol-düzlemi tablolarıyla aynı
gerekçeyle RLS-muaftır (bkz. ADR-0002, ADR-0006); kiracıya-özel *veri* tabloları
(``screening``, ``match_candidate``) RLS'lidir.

Tazelik metriği buradan okunur: günlük senkron job'ı (``sanctions.sync``) kataloğu
yazar, ``/api/v1/screening/datasets`` okur ve ``last_export_at`` 24 saatten eskiyse
bayatlık alarmı üretilir (Ürün Planı: veri tazeliği < 24 saat).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin


class SanctionsDataset(TimestampMixin, Base):
    """Bir yaptırım/PEP veri kümesinin son bilinen durumu (kiracıdan bağımsız)."""

    __tablename__ = "sanctions_dataset"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    """Katalogdaki veri kümesi adı (ör. ``default``, ``masak_dondurma``)."""

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_export_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    """Kaynağın kendi dışa aktarım zamanı — tazeliğin ÖLÇÜSÜ budur, ``checked_at`` değil."""

    entity_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    """Bu satırın en son ne zaman doğrulandığı (senkron job'ı her koşuda günceller)."""
