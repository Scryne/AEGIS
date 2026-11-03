"""Risk puanının veritabanı tarafı (E2.3): canlı hesap, anlık görüntü, zaman çizelgesi.

* **Canlı puan** ``build_dossier`` ile aynı girdilerden (kural bulguları) + son UBO hesabından
  üretilir; hiçbir şey yazmaz.
* **Anlık görüntü** puan dökümünün kanonik JSON'unun özetini taşır. Son anlık görüntüyle aynı
  özet yeni satır üretmez: zaman çizelgesi yalnız değişimleri gösterir.
* Anlık görüntü bir denetim olayıdır (``risk_score.snapshot``): "bu dosyaya bu puan verildi"
  kararı kimin, ne zaman ve hangi dökümle verdiğiyle izde durur.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.models import AuditAction, Entity, EntitySchema
from aegis_core.models.risk_score import RiskScoreSnapshot
from aegis_core.reports.dossier import DossierData, build_dossier
from aegis_core.reports.score import RiskScore, UboView, score_risk
from aegis_core.services import audit as audit_service
from aegis_core.ubo import service as ubo_service


def breakdown_digest(score: RiskScore) -> str:
    blob = json.dumps(score.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


async def live_score(
    session: AsyncSession, entity: Entity, *, high_risk_countries: list[str]
) -> RiskScore:
    data = await build_dossier(session, entity)
    return await score_for_dossier(session, entity, data, high_risk_countries=high_risk_countries)


async def score_for_dossier(
    session: AsyncSession, entity: Entity, data: DossierData, *, high_risk_countries: list[str]
) -> RiskScore:
    """Hazır dosya içeriğinden puan: dosya ile puan aynı veri anından çıkar."""
    ubo_view: UboView | None = None
    if entity.schema_type == EntitySchema.COMPANY.value:
        row = await ubo_service.latest(session, entity.id)
        if row is not None:
            ubo_view = UboView(
                computation_id=str(row.id),
                status=row.status,
                cycles=len(row.result.get("cycles", [])),
                unresolved=len(row.result.get("unresolved", [])),
            )
    return score_risk(
        data.risk,
        entity_id=str(entity.id),
        schema_type=entity.schema_type,
        country=entity.country,
        ubo=ubo_view,
        high_risk_countries=high_risk_countries,
    )


async def latest_snapshot(session: AsyncSession, entity_id: uuid.UUID) -> RiskScoreSnapshot | None:
    row: RiskScoreSnapshot | None = await session.scalar(
        select(RiskScoreSnapshot)
        .where(RiskScoreSnapshot.entity_id == entity_id)
        .order_by(RiskScoreSnapshot.created_at.desc(), RiskScoreSnapshot.id.desc())
        .limit(1)
    )
    return row


async def history(
    session: AsyncSession, entity_id: uuid.UUID, limit: int = 30
) -> list[RiskScoreSnapshot]:
    rows = await session.scalars(
        select(RiskScoreSnapshot)
        .where(RiskScoreSnapshot.entity_id == entity_id)
        .order_by(RiskScoreSnapshot.created_at.desc(), RiskScoreSnapshot.id.desc())
        .limit(limit)
    )
    return list(rows)


async def snapshot(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity: Entity,
    reason: str,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
    high_risk_countries: list[str],
    retention_years: int = 5,
) -> tuple[RiskScoreSnapshot, bool]:
    """Canlı puanı kayda geçirir; dökümü son kayıtla aynıysa yeni satır yazmaz."""
    score = await live_score(session, entity, high_risk_countries=high_risk_countries)
    digest = breakdown_digest(score)
    last = await latest_snapshot(session, entity.id)
    if last is not None and last.input_sha256 == digest:
        return last, False
    row = RiskScoreSnapshot(
        tenant_id=tenant_id,
        entity_id=entity.id,
        score=score.score,
        band=score.band.value,
        weights_version=score.weights_version,
        breakdown=score.to_dict(),
        input_sha256=digest,
        reason=reason,
        created_by_user_id=actor_user_id,
        retention_until=datetime.now(UTC) + timedelta(days=365 * retention_years),
    )
    session.add(row)
    await session.flush()
    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.RISK_SCORE_SNAPSHOT,
        object_type="risk_score_snapshot",
        object_id=str(row.id),
        payload={
            "entity_id": str(entity.id),
            "score": score.score,
            "band": score.band.value,
            "weights_version": score.weights_version,
            "reason": reason,
            "previous_score": last.score if last is not None else None,
        },
    )
    return row, True
