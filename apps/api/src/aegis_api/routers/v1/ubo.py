"""/api/v1/entities/{id}/ubo — gerçek faydalanıcı hesabı (E2.1).

Yetkilendirme:

- **Okuma** (son hesap, geçmiş, graf): tüm roller (denetçi dahil).
- **Hesaplama**: owner · compliance_officer · analyst — kütüğü hazırlayan rol hesabı da
  yeniden çalıştırabilir. Hesap kütüğü değiştirmez; yeni bir anlık görüntü yazar.

Yanıt yalnız sonucu değil, kararın dayanağını taşır: kimlerin hangi yollardan, hangi etkin
payla; belirlenemiyorsa nerede ve neden; döngüler; ve hangi eşik yorumu kullanıldı.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from aegis_api.dependencies import (
    Principal,
    PrincipalDep,
    SettingsDep,
    TenantSessionDep,
    require_role,
)
from aegis_api.errors import NotFoundError, ValidationFailedError
from aegis_core.entities import service as entity_service
from aegis_core.models import Entity, EntitySchema, Role
from aegis_core.models.ubo import UboComputation
from aegis_core.reports import score_service
from aegis_core.ubo import service as ubo_service

router = APIRouter(prefix="/entities", tags=["ubo"])

RequireRegistryWrite = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.ANALYST))
]


class UboComputeRequest(BaseModel):
    """Eşik ve yorumu. Varsayılan: %25'ten fazla (MASAK ifadesi "yüzde yirmi beşinden fazla")."""

    threshold_percent: Decimal = Field(default=Decimal(25), gt=0, le=100)
    inclusive: bool = False


class UboPersonResponse(BaseModel):
    entity_id: str
    name: str
    basis: str
    effective_percent: str
    paths: list[list[str]]


class UboUnresolvedResponse(BaseModel):
    entity_id: str
    name: str
    reason: str
    share_percent: str | None


class GraphNodeResponse(BaseModel):
    id: str
    schema_type: str = Field(alias="schema")
    name: str
    country: str | None

    model_config = {"populate_by_name": True}


class GraphEdgeResponse(BaseModel):
    owner: str
    owned: str
    kind: str
    percent: str | None
    relationship_id: str | None


class UboComputationResponse(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    status: str
    threshold_percent: str
    inclusive: bool
    ubos: list[UboPersonResponse]
    unresolved: list[UboUnresolvedResponse]
    cycles: list[list[str]]
    unattributed_percent: str
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
    input_sha256: str
    created_at: datetime
    unscreened_ubo_ids: list[str] = Field(
        default_factory=list,
        description="Hiç taranmamış UBO'lar; tarama ucu ile tek tıkla taranır.",
    )


class UboHistoryItem(BaseModel):
    id: uuid.UUID
    status: str
    ubo_count: int
    input_sha256: str
    created_at: datetime


async def _response(session: Any, row: UboComputation) -> UboComputationResponse:
    result = row.result
    ubo_ids = [u["entity_id"] for u in result["ubos"]]
    return UboComputationResponse(
        id=row.id,
        entity_id=row.entity_id,
        status=row.status,
        threshold_percent=result["threshold"],
        inclusive=row.threshold_inclusive,
        ubos=[UboPersonResponse(**u) for u in result["ubos"]],
        unresolved=[UboUnresolvedResponse(**u) for u in result["unresolved"]],
        cycles=result["cycles"],
        unattributed_percent=result["unattributed_percent"],
        nodes=[GraphNodeResponse(**n) for n in row.inputs["nodes"]],
        edges=[GraphEdgeResponse(**e) for e in row.inputs["edges"]],
        input_sha256=row.input_sha256,
        created_at=row.created_at,
        unscreened_ubo_ids=await ubo_service.unscreened(session, ubo_ids),
    )


async def _require_company(session: TenantSessionDep, entity_id: uuid.UUID) -> Entity:
    entity = await entity_service.get_entity(session, entity_id)
    if entity is None:
        raise NotFoundError("Varlık bulunamadı.")
    if entity.schema_type != EntitySchema.COMPANY.value:
        raise ValidationFailedError("Gerçek faydalanıcı yalnız tüzel kişi için hesaplanır.")
    return entity


@router.post(
    "/{entity_id}/ubo",
    response_model=UboComputationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def compute(
    entity_id: uuid.UUID,
    principal: RequireRegistryWrite,
    session: TenantSessionDep,
    settings: SettingsDep,
    body: UboComputeRequest | None = None,
) -> UboComputationResponse:
    """Sahiplik zincirinden UBO'yu hesaplar ve anlık görüntü olarak saklar."""
    entity = await _require_company(session, entity_id)
    body = body or UboComputeRequest()
    row, _ = await ubo_service.compute_and_store(
        session,
        tenant_id=principal.tenant_id,
        entity=entity,
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
        threshold=body.threshold_percent,
        inclusive=body.inclusive,
    )
    # UBO sonucu risk puanının girdisidir (E2.3): değişen puan zaman çizelgesine düşer.
    await score_service.snapshot(
        session,
        tenant_id=principal.tenant_id,
        entity=entity,
        reason="ubo_compute",
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
        high_risk_countries=settings.high_risk_countries,
    )
    return await _response(session, row)


@router.get("/{entity_id}/ubo", response_model=UboComputationResponse)
async def latest(
    entity_id: uuid.UUID, _principal: PrincipalDep, session: TenantSessionDep
) -> UboComputationResponse:
    """Son UBO hesabı (graf, yollar, gerekçe)."""
    await _require_company(session, entity_id)
    row = await ubo_service.latest(session, entity_id)
    if row is None:
        raise NotFoundError("Bu şirket için henüz UBO hesabı yapılmadı.")
    return await _response(session, row)


@router.get("/{entity_id}/ubo/history", response_model=list[UboHistoryItem])
async def history(
    entity_id: uuid.UUID,
    _principal: PrincipalDep,
    session: TenantSessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[UboHistoryItem]:
    """Geçmiş hesaplar — "o gün ne biliyorduk" sorusunun cevabı."""
    await _require_company(session, entity_id)
    rows = await ubo_service.history(session, entity_id, limit)
    return [
        UboHistoryItem(
            id=r.id,
            status=r.status,
            ubo_count=len(r.result["ubos"]),
            input_sha256=r.input_sha256,
            created_at=r.created_at,
        )
        for r in rows
    ]
