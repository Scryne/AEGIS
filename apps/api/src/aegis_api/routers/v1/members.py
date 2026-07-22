"""/api/v1/members — kiracının kullanıcıları (kimlik/kontrol düzlemi).

membership/user_account RLS'siz kimlik tablolarıdır; bu uç kiracıyı **uygulama
katmanında** ``principal.tenant_id`` ile sınırlar (bkz. ADR-0002). Kiracılar-arası
izolasyon testi bu sınırlamanın sızdırmadığını doğrular.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from aegis_api.dependencies import PrincipalDep, SessionDep
from aegis_core.models import Membership, Role, User

router = APIRouter(prefix="/members", tags=["members"])


class MemberResponse(BaseModel):
    """Kiracıdaki bir üye (kullanıcı + rol)."""

    user_id: uuid.UUID
    email: EmailStr
    full_name: str | None
    role: Role


@router.get("", response_model=list[MemberResponse])
async def list_members(principal: PrincipalDep, session: SessionDep) -> list[MemberResponse]:
    """Çağıran kullanıcının kiracısındaki üyeleri listeler (yalnız kendi kiracısı)."""
    rows = await session.execute(
        select(User.id, User.email, User.full_name, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == principal.tenant_id)
        .order_by(User.email)
    )
    return [
        MemberResponse(user_id=row.id, email=row.email, full_name=row.full_name, role=row.role)
        for row in rows
    ]
