"""Organization (Tenant) modeli — kiracı kökü (kimlik/kontrol düzlemi, RLS'siz)."""

from __future__ import annotations

from sqlalchemy import String
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
