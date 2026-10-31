"""/api/v1/reports/score — açıklanabilir risk puanı (E2.3).

- ``GET /reports/score/{entity_id}`` — **canlı** puan ve faktör dökümü + zaman çizelgesi. Okumadır:
  hiçbir şey yazmaz (denetçi de görür).
- ``POST /reports/score/{entity_id}/snapshot`` — canlı puanı kayda geçirir (owner ·
  compliance_officer · analyst). Döküm son kayıtla aynıysa yeni satır yazılmaz.

Puan kural bulgularının yerini almaz: seviye (ADR-0008) "neden bu kademe", puan "ne kadar ve
hangi faktörlerden" sorusunu cevaplar. Ağırlıklar ve bantlar ADR-0010'dadır.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from aegis_api.dependencies import (
    Principal,
    PrincipalDep,
    SettingsDep,
    TenantSessionDep,
    require_role,
)
from aegis_api.errors import NotFoundError
from aegis_core.entities import service as entity_service
from aegis_core.models import Entity, Role
from aegis_core.reports import score_service
from aegis_core.reports.score import BAND_LABELS, ScoreBand

router = APIRouter(prefix="/reports", tags=["reports"])

RequireScoreWrite = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.ANALYST))
]


class ScoreFactorResponse(BaseModel):
    code: str
    label: str
    points: int
    occurrences: int
    reason: str
    evidence: list[str]


class ScoreHistoryItem(BaseModel):
    id: uuid.UUID
    score: int
    band: str
    band_label: str
    reason: str
    weights_version: str
    created_at: datetime


class RiskScoreResponse(BaseModel):
    entity_id: uuid.UUID
    score: int
    band: str
    band_label: str
    complete: bool
    weights_version: str
    notes: list[str]
    factors: list[ScoreFactorResponse]
    recorded: bool
    """Canlı döküm son anlık görüntüyle aynı mı (kayda geçmiş mi)."""

    history: list[ScoreHistoryItem]


def _history_item(row: Any) -> ScoreHistoryItem:
    return ScoreHistoryItem(
        id=row.id,
        score=row.score,
        band=row.band,
        band_label=BAND_LABELS[ScoreBand(row.band)],
        reason=row.reason,
        weights_version=row.weights_version,
        created_at=row.created_at,
    )


async def _entity(session: TenantSessionDep, entity_id: uuid.UUID) -> Entity:
    entity = await entity_service.get_entity(session, entity_id)
    if entity is None:
        raise NotFoundError("Varlık bulunamadı.")
    return entity


async def _response(
    session: TenantSessionDep, entity: Entity, countries: list[str]
) -> RiskScoreResponse:
    score = await score_service.live_score(session, entity, high_risk_countries=countries)
    rows = await score_service.history(session, entity.id)
    digest = score_service.breakdown_digest(score)
    data = score.to_dict()
    return RiskScoreResponse(
        entity_id=entity.id,
        score=data["score"],
        band=data["band"],
        band_label=data["band_label"],
        complete=data["complete"],
        weights_version=data["weights_version"],
        notes=data["notes"],
        factors=[ScoreFactorResponse(**f) for f in data["factors"]],
        recorded=bool(rows) and rows[0].input_sha256 == digest,
        history=[_history_item(r) for r in rows],
    )


@router.get("/score/{entity_id}", response_model=RiskScoreResponse)
async def get_score(
    entity_id: uuid.UUID,
    _principal: PrincipalDep,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> RiskScoreResponse:
    """Canlı risk puanı, faktör dökümü ve kayıtlı puanların zaman çizelgesi."""
    entity = await _entity(session, entity_id)
    return await _response(session, entity, settings.high_risk_countries)


@router.post(
    "/score/{entity_id}/snapshot",
    response_model=RiskScoreResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_score(
    entity_id: uuid.UUID,
    principal: RequireScoreWrite,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> RiskScoreResponse:
    """Canlı puanı kayda geçirir (döküm değişmediyse mevcut kayıt döner)."""
    entity = await _entity(session, entity_id)
    await score_service.snapshot(
        session,
        tenant_id=principal.tenant_id,
        entity=entity,
        reason="manual",
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
        high_risk_countries=settings.high_risk_countries,
    )
    return await _response(session, entity, settings.high_risk_countries)
