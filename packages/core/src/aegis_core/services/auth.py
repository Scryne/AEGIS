"""Kimlik doğrulama servisi: kayıt, giriş, üyelik çözümleme, parola değiştirme.

organization/user/membership kimlik (kontrol düzlemi) tablolarıdır; RLS'siz olup
kayıt/giriş öncesi *tenant bağlamı olmadan* (no-tenant session) sorgulanır (ADR-0002).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.models import Membership, Organization, Role, User
from aegis_core.security.passwords import hash_password, verify_password

_dummy_hash_cache: str | None = None


def _dummy_hash() -> str:
    """Kullanıcı bulunamadığında da özet doğrulaması koşmak için sabit özet.

    E-posta var/yok durumları arasındaki yanıt süresi farkını (kullanıcı
    numaralandırma yan-kanalı) kapatır. İlk çağrıda üretilir, sonra önbellekte.
    """
    global _dummy_hash_cache
    if _dummy_hash_cache is None:
        _dummy_hash_cache = hash_password("aegis-timing-equalizer")
    return _dummy_hash_cache


class EmailAlreadyExistsError(Exception):
    """Bu e-posta ile bir kullanıcı zaten var."""


class SlugAlreadyExistsError(Exception):
    """Bu slug ile bir organizasyon zaten var."""


async def register(
    session: AsyncSession,
    *,
    org_name: str,
    org_slug: str,
    email: str,
    password: str,
    full_name: str | None = None,
) -> tuple[User, Membership]:
    """Yeni bir organizasyon + **owner** kullanıcı + üyelik oluşturur."""
    existing_user: User | None = await session.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise EmailAlreadyExistsError(email)
    existing_org: Organization | None = await session.scalar(
        select(Organization).where(Organization.slug == org_slug)
    )
    if existing_org is not None:
        raise SlugAlreadyExistsError(org_slug)

    organization = Organization(name=org_name, slug=org_slug)
    session.add(organization)
    await session.flush()

    user = User(email=email, full_name=full_name, hashed_password=hash_password(password))
    session.add(user)
    await session.flush()

    membership = Membership(user_id=user.id, organization_id=organization.id, role=Role.OWNER)
    session.add(membership)
    await session.flush()
    return user, membership


async def authenticate(
    session: AsyncSession, *, email: str, password: str
) -> tuple[User, Membership] | None:
    """E-posta/parola doğrular; başarılıysa (kullanıcı, üyelik) döndürür.

    Pasif (``is_active=False``) kullanıcılar da parola doğru olsa bile reddedilir;
    çağırana tüm başarısızlıklar tek tip ``None`` döner (bilgi sızdırmaz).
    """
    user: User | None = await session.scalar(select(User).where(User.email == email))
    if user is None or user.hashed_password is None:
        verify_password(password, _dummy_hash())
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    membership = await get_membership(session, user.id)
    if membership is None:
        return None
    return user, membership


async def get_membership(session: AsyncSession, user_id: uuid.UUID) -> Membership | None:
    """Kullanıcının (tek) üyeliğini döndürür (Phase 1: kullanıcı başına bir ofis)."""
    membership: Membership | None = await session.scalar(
        select(Membership).where(Membership.user_id == user_id)
    )
    return membership


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """E-postaya göre kullanıcı döndürür (parola sıfırlama akışı)."""
    user: User | None = await session.scalar(select(User).where(User.email == email))
    return user


async def set_password(session: AsyncSession, *, user_id: uuid.UUID, new_password: str) -> bool:
    """Kullanıcının parolasını değiştirir (parola sıfırlama akışı). Bulunamazsa False."""
    user: User | None = await session.get(User, user_id)
    if user is None:
        return False
    user.hashed_password = hash_password(new_password)
    await session.flush()
    return True
