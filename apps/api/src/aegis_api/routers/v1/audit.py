"""/api/v1/audit — denetim izi görüntüleyici + bütünlük doğrulaması (E1.2 + E1.5).

İki uç vardır:

- ``GET /audit/events`` — **salt-okunur** denetim görüntüleyici (E1.5): kim, ne, ne
  zaman, neye dayanarak. Zincir sırasına (``seq``) göre en yeniden eskiye gelir.
- ``GET /audit/verify`` — Invariant 2'nin verifier'ı: kiracının hash zincirinin
  kurcalanmadığını doğrular.

Oturum ``get_tenant_session`` ile açılır → RLS yalnız çağıranın kiracısının izini
gösterir. Uyumdan sorumlu roller (owner/compliance_officer) ve salt-okunur denetçi
(auditor) erişebilir; analist erişemez.

**Aktörün adı izde tutulmaz**, yalnız kimliği (``actor_user_id``): denetim izi
append-only'dir ve kullanıcı sonradan silinse bile durur (bkz. ``AuditEvent``
docstring'i). Ad, görüntüleme anında kimlik düzleminden çözülür; çözülemezse
kimliğin kendisi gösterilir — olay asla gizlenmez.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_api.dependencies import Principal, SessionDep, TenantSessionDep, require_role
from aegis_core.models import AuditEvent, Membership, Role, User
from aegis_core.services import audit as audit_service

router = APIRouter(prefix="/audit", tags=["audit"])

RequireAuditRead = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.AUDITOR))
]


class ChainVerificationResponse(BaseModel):
    """Hash zinciri doğrulama sonucu."""

    ok: bool
    events_checked: int
    broken_seq: int | None = None
    reason: str | None = None


class AuditEventResponse(BaseModel):
    """Denetim izindeki tek bir olay."""

    id: uuid.UUID
    seq: int
    """Kiracı içindeki zincir sırası — olayların kesin sıralaması budur."""

    action: str
    object_type: str
    object_id: str | None
    source_ref: str | None
    """Neye dayanarak: kanıt bağlantısı, veri kümesi sürümü, dosya özeti (Invariant 4)."""

    actor_user_id: uuid.UUID | None
    actor_label: str | None
    actor_role: str | None
    payload: dict[str, Any]
    occurred_at: datetime
    row_hash: str


class AuditEventPage(BaseModel):
    """Sayfalanmış denetim izi."""

    items: list[AuditEventResponse]
    total: int
    limit: int
    offset: int


async def _actor_labels(session: AsyncSession, tenant_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """Kiracının üyeleri için kullanıcı kimliği → görünen ad eşlemesi.

    Tek sorguyla çekilir (olay başına sorgu N+1 üretirdi). ``user_account``/``membership``
    RLS'siz kimlik tablolarıdır; kiracı sınırı burada uygulama katmanında çizilir
    (ADR-0002).
    """
    rows = await session.execute(
        select(User.id, User.full_name, User.email)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == tenant_id)
    )
    return {row.id: (row.full_name or row.email) for row in rows}


@router.get("/events", response_model=AuditEventPage)
async def list_audit_events(
    principal: RequireAuditRead,
    session: TenantSessionDep,
    identity_session: SessionDep,
    action: Annotated[str | None, Query(max_length=64)] = None,
    object_type: Annotated[str | None, Query(max_length=64)] = None,
    object_id: Annotated[str | None, Query(max_length=255)] = None,
    actor_user_id: Annotated[uuid.UUID | None, Query()] = None,
    occurred_from: Annotated[datetime | None, Query()] = None,
    occurred_to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventPage:
    """Aktif kiracının denetim izini listeler (salt-okunur; hiçbir rol yazamaz)."""
    filters: dict[str, Any] = {
        "action": action,
        "object_type": object_type,
        "object_id": object_id,
        "actor_user_id": actor_user_id,
        "occurred_from": occurred_from,
        "occurred_to": occurred_to,
    }
    events = await audit_service.list_events(session, limit=limit, offset=offset, **filters)
    total = await audit_service.count_events(session, **filters)
    labels = await _actor_labels(identity_session, principal.tenant_id)
    return AuditEventPage(
        items=[_event_response(event, labels) for event in events],
        total=total,
        limit=limit,
        offset=offset,
    )


def _event_response(event: AuditEvent, labels: dict[uuid.UUID, str]) -> AuditEventResponse:
    return AuditEventResponse(
        id=event.id,
        seq=event.seq,
        action=event.action,
        object_type=event.object_type,
        object_id=event.object_id,
        source_ref=event.source_ref,
        actor_user_id=event.actor_user_id,
        actor_label=labels.get(event.actor_user_id) if event.actor_user_id else None,
        actor_role=event.actor_role,
        payload=dict(event.payload),
        occurred_at=event.occurred_at,
        row_hash=event.row_hash,
    )


@router.get("/verify", response_model=ChainVerificationResponse)
async def verify_audit_chain(
    _principal: RequireAuditRead, session: TenantSessionDep
) -> ChainVerificationResponse:
    """Aktif kiracının denetim izi hash zincirini doğrular (kurcalama tespiti)."""
    result = await audit_service.verify_chain(session)
    return ChainVerificationResponse(
        ok=result.ok,
        events_checked=result.events_checked,
        broken_seq=result.broken_seq,
        reason=result.reason,
    )
