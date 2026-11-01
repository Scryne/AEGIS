"""/api/v1/billing — plan ve bu ayın kullanımı (E2.6, ADR-0012).

Salt okunur: plan elle atanır (``scripts/plan_ata.py``), fiyat sözleşmede yaşar. Ekran kiracıya
kotanın nerede olduğunu gösterir; aşım izni olmayan planda kota dolunca tarama uçları 402 döner.

E3.5 (ADR-0018): kullanım kaynağa göre dökülür (ekran / API / toplu), %80'de uyarı düzeyi döner,
ay sonu dökümleri ``/billing/statements``ta (fiyatsız; tutar ve tahsilat sözleşmede).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from aegis_api.dependencies import Principal, PrincipalDep, TenantSessionDep, require_role
from aegis_core.billing import metering
from aegis_core.billing import service as billing_service
from aegis_core.models import Role

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

    warning: str = "ok"
    """``ok`` · ``near`` (dahil kotanın %80'i) · ``exhausted`` (durdu) · ``overage`` (aşımda)."""

    breakdown: dict[str, int] = {}
    """Sorgu kaynağa göre: ekran, API anahtarı, toplu tarama; ayrıca taranan toplu satır."""


class StatementResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    plan_code: str
    included_queries: int
    used_queries: int
    overage_queries: int
    monitored_entities: int
    breakdown: dict[str, Any]
    closed_at: datetime


RequireStatements = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.AUDITOR))
]


@router.get("/usage", response_model=UsageResponse)
async def usage(principal: PrincipalDep, session: TenantSessionDep) -> UsageResponse:
    """Kiracının planı ve bu takvim ayındaki (UTC) sorgu ve izleme kullanımı."""
    u = await billing_service.usage(session, principal.tenant_id)
    live = await metering.statement(session, principal.tenant_id)
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
        warning=live["warning"],
        breakdown=live["breakdown"],
    )


@router.get("/statements", response_model=list[StatementResponse])
async def statements(
    _principal: RequireStatements, session: TenantSessionDep
) -> list[StatementResponse]:
    """Kapanmış dönemlerin dökümü (en yeni üstte); dönem kapandıktan sonra değişmez."""
    return [
        StatementResponse(
            period_start=r.period_start,
            period_end=r.period_end,
            plan_code=r.plan_code,
            included_queries=r.included_queries,
            used_queries=r.used_queries,
            overage_queries=r.overage_queries,
            monitored_entities=r.monitored_entities,
            breakdown=r.breakdown,
            closed_at=r.closed_at,
        )
        for r in await metering.statements(session)
    ]
