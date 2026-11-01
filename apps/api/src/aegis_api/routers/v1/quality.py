"""/api/v1/quality — eşleşme kalitesi programı (E3.6, ADR-0017).

- ``GET /quality/matching`` — canlı ölçüm (insan kararlarından), eşik taraması, öneri, olumsuz haber
  isabeti ve kayıtlı ölçüm geçmişi. owner · compliance_officer · auditor.
- ``POST /quality/matching/snapshot`` — ölçümü kayda geçirir (ör. eşik ayarından önce/sonra).
  owner · compliance_officer.

Eşiği bu uç değiştirmez; öneriyi uyum uzmanı ``/settings/screening.thresholds`` ile uygular ve o
değişiklik kendi denetim olayını yazar.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from aegis_api.dependencies import Principal, TenantSessionDep, require_role
from aegis_core.models import Role
from aegis_core.quality import service as quality_service

router = APIRouter(prefix="/quality", tags=["quality"])

RequireRead = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.AUDITOR))
]
RequireWrite = Annotated[Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER))]


class EvalRunResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    reason: str
    thresholds: dict[str, Any]
    label_count: int
    metrics: dict[str, Any]


class QualityResponse(BaseModel):
    thresholds: dict[str, Any]
    matching: dict[str, Any]
    adverse_media: dict[str, Any]
    history: list[EvalRunResponse]


def _run(r: Any) -> EvalRunResponse:
    return EvalRunResponse(
        id=r.id,
        created_at=r.created_at,
        reason=r.reason,
        thresholds=r.thresholds,
        label_count=r.label_count,
        metrics=r.metrics,
    )


@router.get("/matching", response_model=QualityResponse)
async def matching_quality(_principal: RequireRead, session: TenantSessionDep) -> QualityResponse:
    data = await quality_service.measure(session)
    return QualityResponse(
        **data, history=[_run(r) for r in await quality_service.history(session)]
    )


@router.post(
    "/matching/snapshot", response_model=EvalRunResponse, status_code=status.HTTP_201_CREATED
)
async def snapshot(principal: RequireWrite, session: TenantSessionDep) -> EvalRunResponse:
    run = await quality_service.snapshot(
        session,
        tenant_id=principal.tenant_id,
        reason="manual",
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
    )
    return _run(run)
