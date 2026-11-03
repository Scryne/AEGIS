"""Kiracı açma servisi — bkz. paket belgesi (``aegis_core.provisioning``)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from urllib.parse import quote

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.billing.plans import PLANS
from aegis_core.db.tenant import set_tenant_context
from aegis_core.models import AuditAction, Membership, Organization, Role, User
from aegis_core.security.tokens import create_password_reset_token
from aegis_core.services.audit import record_event

_EMAIL = TypeAdapter(EmailStr)
SLUG_PATTERN = re.compile(r"^[a-z0-9-]+$")
# Denetim izinde operatör eylemi: bir kullanıcı değil, sunucuda komut çalıştıran işletmeci.
OPERATOR_ROLE = "operator"
SOURCE_REF = "cli:scripts/kiraci_ac.py"


class ProvisionError(Exception):
    """Kiracı açılamadı; mesaj operatöre aynen gösterilir."""


@dataclass(frozen=True)
class ProvisionResult:
    tenant_id: uuid.UUID
    owner_user_id: uuid.UUID
    slug: str
    plan_code: str


@dataclass(frozen=True)
class InviteResult:
    channel: str  # "smtp" | "manual"
    delivered: bool
    error: str | None = None


def normalize_email(value: str) -> str:
    """Kayıt ucuyla (``EmailStr``) aynı biçim: girişte aynı adres eşleşsin."""
    try:
        return str(_EMAIL.validate_python(value.strip()))
    except ValidationError as exc:
        raise ProvisionError("Sahip e-postası geçerli değil.") from exc


def _validate(*, org_name: str, org_slug: str, plan_code: str) -> None:
    if not org_name.strip() or len(org_name) > 255:
        raise ProvisionError("Kurum adı boş olamaz (en çok 255 karakter).")
    if not SLUG_PATTERN.fullmatch(org_slug) or len(org_slug) > 255:
        raise ProvisionError(
            "Kısa ad yalnız küçük harf, rakam ve tire içerebilir (ör. ornek-ofis)."
        )
    if plan_code not in PLANS:
        secenekler = ", ".join(sorted(PLANS))
        raise ProvisionError(f"Bilinmeyen plan: {plan_code} (seçenekler: {secenekler}).")


async def provision_tenant(
    session: AsyncSession,
    *,
    org_name: str,
    org_slug: str,
    owner_email: str,
    owner_full_name: str | None,
    plan_code: str,
    today: date,
) -> ProvisionResult:
    """Kurum + parolasız sahip + üyelik + ``tenant.provision`` olayı (tek transaction).

    Çağıran transaction'ı açar (``async with session.begin()``); hata hâlinde hiçbir satır
    kalmaz.
    """
    _validate(org_name=org_name, org_slug=org_slug, plan_code=plan_code)
    email = normalize_email(owner_email)

    if await session.scalar(select(Organization.id).where(Organization.slug == org_slug)):
        raise ProvisionError(f"Bu kısa adla bir kurum zaten var: {org_slug}")
    if await session.scalar(select(User.id).where(User.email == email)):
        # Phase 1: kullanıcı başına tek kurum (auth.get_membership). Var olan hesabı başka
        # kuruma bağlamak, o kişinin eski kurumdaki erişimini belirsizleştirirdi.
        raise ProvisionError("Bu e-postayla bir kullanıcı zaten var; başka bir adres verin.")

    organization = Organization(
        name=org_name.strip(), slug=org_slug, plan_code=plan_code, plan_started_on=today
    )
    session.add(organization)
    await session.flush()

    # Parola yok: hesap, sahip davet bağlantısıyla parola belirleyene kadar giriş yapamaz
    # (``authenticate`` parolasız kullanıcıyı reddeder).
    owner = User(email=email, full_name=owner_full_name, hashed_password=None)
    session.add(owner)
    await session.flush()

    session.add(Membership(user_id=owner.id, organization_id=organization.id, role=Role.OWNER))
    await session.flush()

    # Olay yeni kiracının zincirine yazılır: bağlam olmadan RLS ``WITH CHECK`` reddederdi.
    await set_tenant_context(session, organization.id)
    await record_event(
        session,
        tenant_id=organization.id,
        action=AuditAction.TENANT_PROVISION,
        object_type="organization",
        object_id=str(organization.id),
        actor_role=OPERATOR_ROLE,
        source_ref=SOURCE_REF,
        payload={
            "slug": org_slug,
            "plan": plan_code,
            "owner_user_id": str(owner.id),
            "owner_role": Role.OWNER.value,
        },
    )
    return ProvisionResult(
        tenant_id=organization.id, owner_user_id=owner.id, slug=org_slug, plan_code=plan_code
    )


async def find_owner(session: AsyncSession, org_slug: str) -> tuple[Organization, User]:
    """Kurumun (ilk) sahibini bulur — davetin yeniden gönderimi için."""
    row = (
        await session.execute(
            select(Organization, User)
            .join(Membership, Membership.organization_id == Organization.id)
            .join(User, User.id == Membership.user_id)
            .where(Organization.slug == org_slug, Membership.role == Role.OWNER)
            .order_by(Membership.created_at)
            .limit(1)
        )
    ).first()
    if row is None:
        raise ProvisionError(f"Kurum ya da sahibi bulunamadı: {org_slug}")
    return row[0], row[1]


MAX_INVITE_HOURS = 24 * 7


def validate_invite_hours(valid_hours: int) -> None:
    if valid_hours < 1 or valid_hours > MAX_INVITE_HOURS:
        raise ProvisionError("Davet geçerliliği 1 saat ile 7 gün arasında olmalı.")


def create_invite_link(
    *, user_id: uuid.UUID, secret: str, web_base_url: str, valid_hours: int
) -> str:
    """Sahibin parola belirleyeceği bağlantı (parola sıfırlama jetonu, süreli)."""
    validate_invite_hours(valid_hours)
    token = create_password_reset_token(
        user_id=user_id, secret=secret, expires_in_minutes=valid_hours * 60
    )
    return f"{web_base_url.rstrip('/')}/reset-password?token={quote(token)}"


async def record_invite(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    result: InviteResult,
    valid_hours: int,
) -> None:
    """Davetin kendisi ayrı bir olaydır: hangi kanalla, teslim edildi mi, kaç saat geçerli."""
    await set_tenant_context(session, tenant_id)
    await record_event(
        session,
        tenant_id=tenant_id,
        action=AuditAction.TENANT_INVITE,
        object_type="user_account",
        object_id=str(owner_user_id),
        actor_role=OPERATOR_ROLE,
        source_ref=SOURCE_REF,
        payload={
            "channel": result.channel,
            "delivered": result.delivered,
            "error": result.error,
            "valid_hours": valid_hours,
        },
    )
