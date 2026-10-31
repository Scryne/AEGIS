"""/api/v1/billing — plan ve bu ayın kullanımı (E2.6, ADR-0012).

Salt okunur: plan elle atanır (``scripts/plan_ata.py``), fiyat sözleşmede yaşar. Ekran kiracıya
kotanın nerede olduğunu gösterir; aşım izni olmayan planda kota dolunca tarama uçları 402 döner.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from aegis_api.dependencies import PrincipalDep, TenantSessionDep
from aegis_core.billing import service as billing_service

router = APIRouter(prefix="/billing", tags=["billing"])


class PlanResponse(BaseModel):
    code: str
    name: str
    included_queries: int
    monitored_entity_limit: int
    overage_allowed: bool


class UsageResponse(BaseModel):
    plan: PlanResponse
    period_start: datetime
    period_end: datetime
    used_queries: int
    remaining_queries: int
    overage_queries: int
    monitored_entities: int
    blocked: bool
    """Aşım izni yok ve kota doldu: yeni tarama reddedilir."""


@router.get("/usage", response_model=UsageResponse)
async def usage(principal: PrincipalDep, session: TenantSessionDep) -> UsageResponse:
    """Kiracının planı ve bu takvim ayındaki (UTC) sorgu ve izleme kullanımı."""
    u = await billing_service.usage(session, principal.tenant_id)
    p = u.plan
    return UsageResponse(
        plan=PlanResponse(
            code=p.code,
            name=p.name,
            included_queries=p.included_queries,
            monitored_entity_limit=p.monitored_entity_limit,
            overage_allowed=p.overage_allowed,
        ),
        period_start=u.period_start,
        period_end=u.period_end,
        used_queries=u.used_queries,
        remaining_queries=max(p.included_queries - u.used_queries, 0),
        overage_queries=u.overage_queries,
        monitored_entities=u.monitored_entities,
        blocked=not p.overage_allowed and u.used_queries >= p.included_queries,
    )
