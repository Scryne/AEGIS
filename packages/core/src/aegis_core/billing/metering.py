"""Kullanım ölçümü ve ay sonu dökümü (E3.5, ADR-0018) — fiyatsız iskelet.

Faturalamanın kod tarafı: **ne kadar iş yapıldı**. Ne kadar tutar (fiyat), nasıl tahsil edilir
(ödeme kanalı), sözleşme ve tahsilat takibi ticari kararlardır ve burada yoktur (ADR-0012).

Bir dönemin dökümü:

* **Sorgu** (taranan özne) kaynağa göre: ekran (kişi oturumu), API anahtarı, toplu tarama.
  Gece izlemesinin koşuları izleme eklentisinin parçasıdır, sorguya girmez (ADR-0012).
* **Aşım** = dahil kotayı aşan sorgu (aşım izni olmayan planda hep 0: tarama durur).
* **İzleme**: dönem kapanışında izlenen varlık sayısı ve plan sınırı.
* **Toplu tarama satırı**: dönemde taranan satır sayısı (bilgi; sorgu zaten sayıldı).

Dönem İstanbul takvim ayıdır (``service._period``). Ay sonu dökümü ``usage_statement`` satırına
dondurulur; aynı dönem ikinci kez kapanmaz (tekillik kısıtı), geçmiş döküm sonradan değişmez.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.billing.service import _period, _plan_for, monitored_count
from aegis_core.models import (
    ApiKey,
    RowStatus,
    Screening,
    ScreeningBatchRow,
    ScreeningStatus,
    UsageStatement,
)

WARN_AT = 0.8
"""Dahil kotanın bu payı kullanılınca uyarı (sert durdurma yalnız aşım izni olmayan planda)."""


def warning_level(used: int, included: int, overage_allowed: bool) -> str:
    if included <= 0:
        return "ok"
    if used >= included:
        return "overage" if overage_allowed else "exhausted"
    if used >= included * WARN_AT:
        return "near"
    return "ok"


async def breakdown(
    session: AsyncSession, tenant_id: uuid.UUID, start: datetime, end: datetime
) -> dict[str, Any]:
    subjects = func.coalesce(func.sum(func.jsonb_array_length(Screening.subjects)), 0)
    base = (
        Screening.tenant_id == tenant_id,
        Screening.requested_by_user_id.is_not(None),
        Screening.status != ScreeningStatus.FAILED.value,  # yapılamayan tarama sayılmaz
        Screening.created_at >= start,
        Screening.created_at < end,
    )
    total = int(await session.scalar(select(subjects).where(*base)) or 0)
    key_ids = select(ApiKey.id).where(ApiKey.tenant_id == tenant_id)
    via_api = int(
        await session.scalar(
            select(subjects).where(*base, Screening.requested_by_user_id.in_(key_ids))
        )
        or 0
    )
    batch_screenings = select(ScreeningBatchRow.screening_id).where(
        ScreeningBatchRow.screening_id.is_not(None)
    )
    via_batch = int(
        await session.scalar(select(subjects).where(*base, Screening.id.in_(batch_screenings))) or 0
    )
    batch_rows = int(
        await session.scalar(
            select(func.count())
            .select_from(ScreeningBatchRow)
            .where(
                ScreeningBatchRow.tenant_id == tenant_id,
                ScreeningBatchRow.status == RowStatus.DONE.value,
                ScreeningBatchRow.processed_at >= start,
                ScreeningBatchRow.processed_at < end,
            )
        )
        or 0
    )
    return {
        "queries_total": total,
        "queries_screen": max(total - via_api - via_batch, 0),
        "queries_api": via_api,
        "queries_batch": via_batch,
        "batch_rows": batch_rows,
    }


async def statement(
    session: AsyncSession, tenant_id: uuid.UUID, *, now: datetime | None = None
) -> dict[str, Any]:
    """İçinde bulunulan (ya da ``now``un) dönemin canlı dökümü."""
    at = now or datetime.now(UTC)
    start, end = _period(at)
    plan = await _plan_for(session, tenant_id)
    b = await breakdown(session, tenant_id, start, end)
    used = b["queries_total"]
    return {
        "period_start": start,
        "period_end": end,
        "plan_code": plan.code,
        "plan_name": plan.name,
        "included_queries": plan.included_queries,
        "overage_allowed": plan.overage_allowed,
        "used_queries": used,
        "overage_queries": max(used - plan.included_queries, 0) if plan.overage_allowed else 0,
        "monitored_entities": await monitored_count(session, tenant_id),
        "monitored_entity_limit": plan.monitored_entity_limit,
        "warning": warning_level(used, plan.included_queries, plan.overage_allowed),
        "breakdown": b,
    }


async def close_previous_period(
    session: AsyncSession, tenant_id: uuid.UUID, *, now: datetime | None = None
) -> UsageStatement | None:
    """Bir önceki dönemi dondurur; zaten kapanmışsa ``None`` (idempotent)."""
    at = now or datetime.now(UTC)
    current_start, _ = _period(at)
    prev_start, prev_end = _period(current_start - timedelta(seconds=1))
    exists = await session.scalar(
        select(UsageStatement.id).where(
            UsageStatement.tenant_id == tenant_id, UsageStatement.period_start == prev_start
        )
    )
    if exists is not None:
        return None
    data = await statement(session, tenant_id, now=prev_start)
    row = UsageStatement(
        tenant_id=tenant_id,
        period_start=prev_start,
        period_end=prev_end,
        plan_code=data["plan_code"],
        included_queries=data["included_queries"],
        used_queries=data["used_queries"],
        overage_queries=data["overage_queries"],
        monitored_entities=data["monitored_entities"],
        breakdown=data["breakdown"],
    )
    session.add(row)
    await session.flush()
    return row


async def statements(session: AsyncSession, *, limit: int = 24) -> list[UsageStatement]:
    rows = await session.scalars(
        select(UsageStatement).order_by(UsageStatement.period_start.desc()).limit(limit)
    )
    return list(rows)
