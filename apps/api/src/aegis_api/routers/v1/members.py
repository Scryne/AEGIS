"""/api/v1/members — kiracının kullanıcıları ve ekip yönetimi (kimlik/kontrol düzlemi).

membership/user_account RLS'siz kimlik tablolarıdır; bu uçlar kiracıyı **uygulama
katmanında** ``principal.tenant_id`` ile sınırlar (bkz. ADR-0002). Kiracılar-arası
izolasyon testi bu sınırlamanın sızdırmadığını doğrular.

Ekip yönetimi yalnız sahibindir (``Role.OWNER``, Ürün Planı §6.3 "kullanıcı yönetimi dahil"):

- **Davet:** parolasız kullanıcı + üyelik açılır, kiracı açma CLI'ıyla aynı mekanizmayla
  süreli parola belirleme bağlantısı üretilir. SMTP yapılandırılmışsa bağlantı e-postayla
  gider; değilse (ya da gönderim düşerse) yanıtta döner ve sahip kendisi iletir. Denetim
  olayına e-posta adresi yazılmaz (yalnız rol, kanal, teslim durumu).
- **Rol değişikliği:** eski → yeni rol denetim izine düşer. Son sahip düşürülemez (kiracı
  yönetilemez hâle gelirdi). Erişim jetonu rolü taşır; yeni rol, üyenin bir sonraki jeton
  yenilemesinde (``/auth/refresh`` rolü veritabanından okur) geçerli olur.

- **Çıkarma:** üyelik silinir, hesap kalır (denetim izi ve kararlar kişiye bağlı); elindeki
  jetonlar hemen geçersiz olur. Son sahip çıkarılamaz. Çıkarılan kişi yeniden davet edilebilir.

Phase 1: kullanıcı başına tek kurum. Başka kurumda hesabı olan adres davet edilemez.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from aegis_api.dependencies import (
    Principal,
    PrincipalDep,
    RedisDep,
    SessionDep,
    SettingsDep,
    TenantSessionDep,
    require_role,
)
from aegis_api.errors import ConflictError, NotFoundError, UnauthorizedError, ValidationFailedError
from aegis_core.logging import get_logger
from aegis_core.models import AuditAction, Membership, Role, User
from aegis_core.notifications.email import EmailSendError, OutgoingEmail, default_sender
from aegis_core.provisioning import create_invite_link
from aegis_core.services import audit as audit_service
from aegis_core.services.session_revocation import revoke_user_sessions

logger = get_logger("aegis.api.members")
router = APIRouter(prefix="/members", tags=["members"])

RequireOwner = Annotated[Principal, Depends(require_role(Role.OWNER))]

INVITE_VALID_HOURS = 72


class MemberResponse(BaseModel):
    """Kiracıdaki bir üye (kullanıcı + rol)."""

    user_id: uuid.UUID
    email: EmailStr
    full_name: str | None
    role: Role
    # Parola henüz belirlenmemiş (davet bekliyor): giriş yapamaz.
    pending: bool = False


class MemberInviteRequest(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)
    role: Role


class MemberInviteResponse(BaseModel):
    member: MemberResponse
    channel: str  # "smtp" | "manual"
    delivered: bool
    valid_hours: int
    # Yalnız e-postayla teslim edilmediyse döner: sahip bağlantıyı kendisi iletir.
    invite_link: str | None = None


class MemberRoleUpdate(BaseModel):
    role: Role


def _member(user: User, role: Role) -> MemberResponse:
    return MemberResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=role,
        pending=user.hashed_password is None,
    )


@router.get("", response_model=list[MemberResponse])
async def list_members(principal: PrincipalDep, session: SessionDep) -> list[MemberResponse]:
    """Çağıran kullanıcının kiracısındaki üyeleri listeler (yalnız kendi kiracısı)."""
    rows = await session.execute(
        select(User, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == principal.tenant_id)
        .order_by(User.email)
    )
    return [_member(user, role) for user, role in rows.tuples()]


async def _deliver_invite(
    settings: SettingsDep, *, user: User, link: str, inviter_email: str | None
) -> tuple[str, bool]:
    sender = default_sender(settings)
    if not sender.configured:
        return "manual", False
    try:
        await sender.send(
            OutgoingEmail(
                to=(user.email,),
                subject="AEGIS ekibine davet edildiniz",
                body=(
                    "AEGIS'te bir uyum ekibine eklendiniz"
                    + (f" (davet eden: {inviter_email})" if inviter_email else "")
                    + ".\n\nParolanızı belirleyip giriş yapmak için bağlantıyı açın:\n\n"
                    f"{link}\n\nBağlantı {INVITE_VALID_HOURS} saat geçerlidir."
                ),
            )
        )
    except EmailSendError as exc:
        logger.error("uye_davet_epostasi_gitmedi", error=str(exc))
        return "smtp", False
    return "smtp", True


async def _issue_invite(
    session: TenantSessionDep,
    settings: SettingsDep,
    principal: Principal,
    *,
    user: User,
    role: Role,
) -> MemberInviteResponse:
    if settings.auth_secret is None:
        raise UnauthorizedError("Sunucu kimlik doğrulaması yapılandırılmamış (AUTH_SECRET).")
    link = create_invite_link(
        user_id=user.id,
        secret=settings.auth_secret,
        web_base_url=settings.web_base_url,
        valid_hours=INVITE_VALID_HOURS,
    )
    inviter = await session.get(User, principal.user_id)
    channel, delivered = await _deliver_invite(
        settings, user=user, link=link, inviter_email=inviter.email if inviter else None
    )
    await audit_service.record_event(
        session,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
        action=AuditAction.MEMBER_INVITE,
        object_type="user_account",
        object_id=str(user.id),
        payload={
            "role": role.value,
            "channel": channel,
            "delivered": delivered,
            "valid_hours": INVITE_VALID_HOURS,
        },
    )
    return MemberInviteResponse(
        member=_member(user, role),
        channel=channel,
        delivered=delivered,
        valid_hours=INVITE_VALID_HOURS,
        invite_link=None if delivered else link,
    )


@router.post("", response_model=MemberInviteResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    body: MemberInviteRequest,
    principal: RequireOwner,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> MemberInviteResponse:
    """Ekibe yeni üye davet eder (yalnız sahip). Üyelik, davet ve denetim olayı atomiktir."""
    email = str(body.email)
    user = await session.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if user is not None:
        if await session.scalar(select(Membership.id).where(Membership.user_id == user.id)):
            raise ConflictError(
                "Bu e-postayla bir hesap zaten var. Ekibinizdeyse rolünü listeden değiştirin; "
                "başka bir kurumdaysa farklı bir adres kullanın."
            )
        # Daha önce ekipten çıkarılmış (üyeliksiz) hesap: yeniden bağlanır. Eski parola
        # geçmez; kişi yeni davet bağlantısıyla parola belirler.
        user.hashed_password = None
        if body.full_name and body.full_name.strip():
            user.full_name = body.full_name.strip()
    else:
        user = User(
            email=email, full_name=(body.full_name or "").strip() or None, hashed_password=None
        )
        session.add(user)
    await session.flush()
    session.add(Membership(user_id=user.id, organization_id=principal.tenant_id, role=body.role))
    await session.flush()
    return await _issue_invite(session, settings, principal, user=user, role=body.role)


async def _tenant_membership(
    session: TenantSessionDep, principal: Principal, user_id: uuid.UUID
) -> tuple[Membership, User]:
    row = (
        await session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.user_id == user_id,
                Membership.organization_id == principal.tenant_id,
            )
        )
    ).first()
    if row is None:
        # Başka kiracının üyesi de "yok" görünür: varlığı sızdırılmaz.
        raise NotFoundError("Üye bulunamadı.")
    return row[0], row[1]


@router.post("/{user_id}/invite", response_model=MemberInviteResponse)
async def resend_invite(
    user_id: uuid.UUID,
    principal: RequireOwner,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> MemberInviteResponse:
    """Daveti yeniden üretir (bağlantı kaybolduysa / süresi dolduysa). Yalnız parolası
    henüz belirlenmemiş üye için; etkin hesabın parolası bu yolla sıfırlanamaz."""
    membership, user = await _tenant_membership(session, principal, user_id)
    if user.hashed_password is not None:
        raise ConflictError("Bu üye hesabını etkinleştirmiş; davet yeniden gönderilemez.")
    return await _issue_invite(session, settings, principal, user=user, role=membership.role)


@router.patch("/{user_id}", response_model=MemberResponse)
async def change_member_role(
    user_id: uuid.UUID,
    body: MemberRoleUpdate,
    principal: RequireOwner,
    session: TenantSessionDep,
) -> MemberResponse:
    """Üyenin rolünü değiştirir (yalnız sahip). Son sahip düşürülemez."""
    membership, user = await _tenant_membership(session, principal, user_id)
    old = membership.role
    if old == body.role:
        return _member(user, old)
    if old == Role.OWNER:
        owners = await session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.organization_id == principal.tenant_id,
                Membership.role == Role.OWNER,
            )
        )
        if (owners or 0) <= 1:
            raise ValidationFailedError("Kurumun tek sahibi bu üye; önce başka birini sahip yapın.")
    membership.role = body.role
    await session.flush()
    await audit_service.record_event(
        session,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
        action=AuditAction.MEMBER_ROLE_CHANGE,
        object_type="user_account",
        object_id=str(user.id),
        payload={"from": old.value, "to": body.role.value},
    )
    return _member(user, body.role)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    user_id: uuid.UUID,
    principal: RequireOwner,
    session: TenantSessionDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> None:
    """Üyeyi kurumdan çıkarır (yalnız sahip). Son sahip çıkarılamaz.

    Hesap silinmez: denetim izi, vaka ve karar kayıtları kişiye bağlı kalır. Üyelik silinir,
    kişinin elindeki erişim/yenileme jetonları hemen geçersiz olur (``session_revocation``).
    """
    membership, user = await _tenant_membership(session, principal, user_id)
    if membership.role == Role.OWNER:
        owners = await session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.organization_id == principal.tenant_id,
                Membership.role == Role.OWNER,
            )
        )
        if (owners or 0) <= 1:
            raise ValidationFailedError(
                "Kurumun tek sahibi çıkarılamaz; önce başka birini sahip yapın."
            )
    role = membership.role
    await session.delete(membership)
    await session.flush()
    await audit_service.record_event(
        session,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
        action=AuditAction.MEMBER_REMOVE,
        object_type="user_account",
        object_id=str(user.id),
        payload={"role": role.value, "sessions_revoked": True},
    )
    await revoke_user_sessions(
        redis, user.id, ttl_seconds=settings.refresh_token_expire_days * 24 * 3600
    )
