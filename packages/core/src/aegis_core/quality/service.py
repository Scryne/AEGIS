"""Eşleşme kalitesi servisi (E3.6, ADR-0017): etiketleri topla, ölç, kayda geçir, geçmişi oku.

Etiket deposu ayrı bir tablo değildir: insan kararları zaten ``match_candidate``da duruyor ve her
yeni karar (özellikle elenen yanlış pozitif) bir sonraki ölçüme kendiliğinden girer: geri besleme
döngüsü budur. Kayıt (``MatchEvalRun``) yalnız eğilim için metriklerin donmuş kopyasıdır.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.models import AdverseMediaItem, AuditAction, MatchCandidate, MatchEvalRun
from aegis_core.quality.metrics import Label, MediaLabel, adverse_media_precision, evaluate
from aegis_core.screening.entity_run import load_thresholds
from aegis_core.services import audit as audit_service


async def labels(session: AsyncSession) -> list[Label]:
    rows = await session.execute(
        select(MatchCandidate.score, MatchCandidate.decision, MatchCandidate.decided_automatically)
    )
    return [Label(float(s), str(d), bool(a)) for s, d, a in rows]


async def media_labels(session: AsyncSession) -> list[MediaLabel]:
    rows = await session.execute(select(AdverseMediaItem.status, AdverseMediaItem.negative_terms))
    return [MediaLabel(str(st), bool(terms)) for st, terms in rows]


async def measure(session: AsyncSession) -> dict[str, Any]:
    thresholds = await load_thresholds(session)
    quality = evaluate(
        await labels(session),
        auto_dismiss_below=thresholds.auto_dismiss_below,
        auto_flag_at=thresholds.auto_flag_at,
    )
    return {
        "thresholds": {
            "auto_dismiss_below": thresholds.auto_dismiss_below,
            "auto_flag_at": thresholds.auto_flag_at,
            "candidate_cutoff": thresholds.candidate_cutoff,
        },
        "matching": quality.to_dict(),
        "adverse_media": adverse_media_precision(await media_labels(session)),
    }


async def snapshot(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    reason: str,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
) -> MatchEvalRun:
    data = await measure(session)
    m = data["matching"]
    run = MatchEvalRun(
        tenant_id=tenant_id,
        reason=reason,
        thresholds=data["thresholds"],
        label_count=int(m["confirmed"]) + int(m["dismissed"]),
        metrics={k: v for k, v in m.items() if k != "sweep"}
        | {"adverse_media": data["adverse_media"]},
        created_by_user_id=actor_user_id,
    )
    session.add(run)
    await session.flush()
    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.QUALITY_SNAPSHOT,
        object_type="match_eval_run",
        object_id=str(run.id),
        payload={
            "reason": reason,
            "labels": run.label_count,
            "false_positive_rate": m["false_positive_rate"],
            "review_rate": m["review_rate"],
            "thresholds": data["thresholds"],
        },
    )
    return run


async def history(session: AsyncSession, *, limit: int = 52) -> list[MatchEvalRun]:
    rows = await session.scalars(
        select(MatchEvalRun).order_by(MatchEvalRun.created_at.desc()).limit(limit)
    )
    return list(reversed(list(rows)))
