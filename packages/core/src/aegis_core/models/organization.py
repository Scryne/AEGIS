"""Organization (Tenant) modeli — kiracı kökü (kimlik/kontrol düzlemi, RLS'siz)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, String, text
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin
from aegis_core.db.mixins import UUIDPKMixin


class Organization(UUIDPKMixin, TimestampMixin, Base):
    """Kiracı (ofis/firma). Tüm kiracı-özel *veri* ``tenant_id`` ile buna bağlanır.

    Kimlik/kontrol-düzlemi tablosudur; kayıt/giriş öncesi (tenant bağlamı yokken)
    sorgulanır, bu yüzden RLS taşımaz (bkz. ADR-0002).
    """

    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # E2.6 (ADR-0012): elle atanan plan; katalog kodda (aegis_core.billing.plans).
    plan_code: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'pilot'")
    )
    plan_started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
