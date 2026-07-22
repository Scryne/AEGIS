"""Membership + Role — kullanıcı↔organizasyon ilişkisi ve RBAC rolü (kimlik düzlemi)."""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin
from aegis_core.db.mixins import UUIDPKMixin


class Role(StrEnum):
    """AEGIS RBAC rolleri (Ürün Planı §6.3).

    - ``OWNER``: ofis sahibi; tam yetki (kullanıcı yönetimi dahil).
    - ``COMPLIANCE_OFFICER``: uyum uzmanı; tarama/karar/rapor.
    - ``ANALYST``: dosya hazırlar; tarama çalıştırır, karar öneremez/onaylayamaz.
    - ``AUDITOR``: salt-okunur denetçi; hiçbir mutasyon yapamaz.
    """

    OWNER = "owner"
    COMPLIANCE_OFFICER = "compliance_officer"
    ANALYST = "analyst"
    AUDITOR = "auditor"


class Membership(UUIDPKMixin, TimestampMixin, Base):
    """Bir kullanıcının bir organizasyondaki üyeliği ve rolü."""

    __tablename__ = "membership"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_membership_user_organization"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[Role] = mapped_column(SAEnum(Role, native_enum=False, length=32), nullable=False)
