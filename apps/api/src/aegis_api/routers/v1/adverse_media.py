"""/api/v1 — olumsuz haber betası (E2.5, ADR-0013): bayrak, tarama, aday listesi, insan kararı.

Beta kiracı başına açılır (sahip). Adaylar risk puanına girmez; "ilgili" kararı gerekçe ister ve
denetim izine yazılır. Haber metni saklanmaz, yalnız başlık/kaynak/bağlantı/tarih.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from aegis_api.dependencies import (
    NewsProviderDep,
    Principal,
    PrincipalDep,
    TenantSessionDep,
    require_role,
)
from aegis_api.errors import ConflictError, NotFoundError, RateLimitedError
from aegis_core.adverse_media import service as am_service
from aegis_core.entities import service as entity_service
from aegis_core.models import AdverseMediaItem, AdverseMediaStatus, Role

router = APIRouter(tags=["adverse-media"])

RequireOwner = Annotated[Principal, Depends(require_role(Role.OWNER))]
RequireReview = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.ANALYST))
]


class BetaState(BaseModel):
    enabled: bool


class AdverseMediaItemResponse(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    title: str
    url: str
    source_name: str
    published_at: datetime | None
    query: str
    provider: str
    negative_terms: list[str]
    status: str
    review_note: str | None
    reviewed_at: datetime | None


class AdverseMediaListResponse(BaseModel):
    enabled: bool
    items: list[AdverseMediaItemResponse]
    counts: dict[str, int]


class ScanResponse(BaseModel):
    queries: list[str]
    fetched: int
    new: int
    failed_queries: list[str]


class ReviewRequest(BaseModel):
    decision: Literal["ilgili", "ilgisiz"]
    note: str = Field(min_length=10, max_length=2000)


def _item(i: AdverseMediaItem) -> AdverseMediaItemResponse:
    return AdverseMediaItemResponse(
        id=i.id,
        entity_id=i.entity_id,
        title=i.title,
        url=i.url,
        source_name=i.source_name,
        published_at=i.published_at,
        query=i.query,
        provider=i.provider,
        negative_terms=list(i.negative_terms),
        status=i.status,
        review_note=i.review_note,
        reviewed_at=i.reviewed_at,
    )


@router.get("/adverse-media/beta", response_model=BetaState)
async def get_beta(principal: PrincipalDep, session: TenantSessionDep) -> BetaState:
    return BetaState(enabled=await am_service.beta_enabled(session, principal.tenant_id))


@router.put("/adverse-media/beta", response_model=BetaState)
async def put_beta(
    body: BetaState, principal: RequireOwner, session: TenantSessionDep
) -> BetaState:
    """Betayı kiracı adına açar/kapatır (sahip). Kapatmak var olan adayları silmez."""
    await am_service.set_beta(
        session,
        tenant_id=principal.tenant_id,
        enabled=body.enabled,
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
    )
    return body


@router.get("/entities/{entity_id}/adverse-media", response_model=AdverseMediaListResponse)
async def list_items(
    entity_id: uuid.UUID,
    principal: PrincipalDep,
    session: TenantSessionDep,
    status: Annotated[Literal["aday", "ilgili", "ilgisiz"] | None, Query()] = None,
) -> AdverseMediaListResponse:
    if await entity_service.get_entity(session, entity_id) is None:
        raise NotFoundError("Varlık bulunamadı.")
    items = await am_service.list_items(session, entity_id, status)
    hepsi = items if status is None else await am_service.list_items(session, entity_id)
    counts = {s.value: 0 for s in AdverseMediaStatus}
    for i in hepsi:
        counts[i.status] = counts.get(i.status, 0) + 1
    return AdverseMediaListResponse(
        enabled=await am_service.beta_enabled(session, principal.tenant_id),
        items=[_item(i) for i in items],
        counts=counts,
    )


@router.post("/entities/{entity_id}/adverse-media/scan", response_model=ScanResponse)
async def scan(
    entity_id: uuid.UUID,
    principal: RequireReview,
    session: TenantSessionDep,
    provider: NewsProviderDep,
) -> ScanResponse:
    entity = await entity_service.get_entity(session, entity_id)
    if entity is None:
        raise NotFoundError("Varlık bulunamadı.")
    try:
        r = await am_service.scan(
            session,
            provider,
            entity,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
        )
    except am_service.BetaDisabledError as exc:
        raise ConflictError(
            "Olumsuz haber betası bu hesapta kapalı. Sahip, Plan ve kullanım sayfasından açabilir."
        ) from exc
    except am_service.ScanTooSoonError as exc:
        raise RateLimitedError(str(exc), headers={"Retry-After": str(exc.retry_after)}) from exc
    return ScanResponse(
        queries=r.queries, fetched=r.fetched, new=r.new, failed_queries=r.failed_queries
    )


@router.post("/adverse-media/{item_id}/review", response_model=AdverseMediaItemResponse)
async def review(
    item_id: uuid.UUID,
    body: ReviewRequest,
    principal: RequireReview,
    session: TenantSessionDep,
) -> AdverseMediaItemResponse:
    """İnsan kararı: ilgili (dosyaya bağlanır) ya da ilgisiz (başka kişi/olay). Gerekçe zorunlu."""
    item = await session.get(AdverseMediaItem, item_id)
    if item is None:
        raise NotFoundError("Haber adayı bulunamadı.")
    await am_service.review(
        session,
        item,
        decision=AdverseMediaStatus(body.decision),
        note=body.note.strip(),
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
    )
    return _item(item)
