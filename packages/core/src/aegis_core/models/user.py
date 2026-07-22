"""User (kullanıcı hesabı) modeli — kimlik düzlemi (RLS'siz)."""

from __future__ import annotations

from sqlalchemy import Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column

from aegis_core.db.base import Base, TimestampMixin
from aegis_core.db.mixins import UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    """Kullanıcı hesabı (Membership ile bir/birden çok organizasyona bağlanır).

    Not: ``user`` PostgreSQL'de ayrılmış sözcük olduğundan tablo ``user_account``.
    """

    __tablename__ = "user_account"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
