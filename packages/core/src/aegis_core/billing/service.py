"""Kullanım ve kota (E2.6, ADR-0012): ölçüm altyapısı yok, sayım mevcut kayıtlardan yapılır.

Ayın kullanımı = bu takvim ayında (Türkiye saati; fatura dönemi müşterinin ayıdır)
kullanıcı tarafından başlatılmış taramalardaki özne sayısı (``requested_by_user_id`` dolu; gece
izlemesi hariç). Başarısız koşular da sayılır: sorgu listeye gitti, maliyet oluştu. Tam ölçüm
altyapısı (olay tabanlı sayaç, fatura) E3.5'tedir.

Kota kapısı yeni taramadan **önce** çalışır ve kiracının ``organization`` satırını kilitler:
aynı kiracıdan eşzamanlı iki istek son birkaç sorguyu ikişer kez harcayamaz.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.billing.plans import Plan, get_plan
from aegis_core.models import Entity, Organization, Screening


class QuotaExceededError(Exception):
    """Dahil kota doldu ve plan aşıma izin vermiyor."""

    def __init__(self, message: str, *, used: int, included: int) -> None:
        super().__init__(message)
        self.used = used
        self.included = included


class MonitoringLimitError(Exception):
    """Planın izleme varlık sınırı doldu."""


@dataclass(frozen=True)
class Usage:
    plan: Plan
    period_start: datetime
    period_end: datetime
    used_queries: int
    overage_queries: int
    monitored_entities: int


DONEM_SAAT_DILIMI = ZoneInfo("Europe/Istanbul")


def _period(now: datetime) -> tuple[datetime, datetime]:
    """İstanbul takvim ayının başı ve sonu (zamana duyarlı; karşılaştırma UTC'de doğru çalışır)."""
    start = now.astimezone(DONEM_SAAT_DILIMI).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, end


async def _plan_for(session: AsyncSession, tenant_id: uuid.UUID, *, lock: bool = False) -> Plan:
    stmt = select(Organization.plan_code).where(Organization.id == tenant_id)
    if lock:
        stmt = stmt.with_for_update()
    return get_plan(await session.scalar(stmt))


async def used_queries(session: AsyncSession, tenant_id: uuid.UUID, now: datetime) -> int:
    start, end = _period(now)
    total = await session.scalar(
        select(func.coalesce(func.sum(func.jsonb_array_length(Screening.subjects)), 0)).where(
            Screening.tenant_id == tenant_id,
            Screening.requested_by_user_id.is_not(None),
            Screening.created_at >= start,
            Screening.created_at < end,
        )
    )
    return int(total or 0)


async def monitored_count(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Entity)
            .where(Entity.tenant_id == tenant_id, Entity.monitored.is_(True))
        )
        or 0
    )


async def usage(session: AsyncSession, tenant_id: uuid.UUID, now: datetime | None = None) -> Usage:
    now = now or datetime.now(UTC)
    plan = await _plan_for(session, tenant_id)
    used = await used_queries(session, tenant_id, now)
    start, end = _period(now)
    return Usage(
        plan=plan,
        period_start=start,
        period_end=end,
        used_queries=used,
        overage_queries=max(used - plan.included_queries, 0),
        monitored_entities=await monitored_count(session, tenant_id),
    )


async def require_screening_quota(
    session: AsyncSession, tenant_id: uuid.UUID, subject_count: int
) -> None:
    """Yeni taramadan önce: aşım izni yoksa kotayı aşacak istek reddedilir."""
    plan = await _plan_for(session, tenant_id, lock=True)
    if plan.overage_allowed:
        return
    used = await used_queries(session, tenant_id, datetime.now(UTC))
    if used + subject_count > plan.included_queries:
        raise QuotaExceededError(
            f"{plan.name} planının aylık {plan.included_queries} sorgu hakkı doldu "
            f"(kullanılan {used}, bu istek {subject_count}). Plan yükseltmek için hesap "
            "yöneticinizle görüşün.",
            used=used,
            included=plan.included_queries,
        )


async def require_monitoring_slot(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Bir varlığı izlemeye almadan önce plan sınırı denetlenir (çıkarmak her zaman serbest)."""
    plan = await _plan_for(session, tenant_id, lock=True)
    current = await monitored_count(session, tenant_id)
    if current >= plan.monitored_entity_limit:
        raise MonitoringLimitError(
            f"{plan.name} planı en fazla {plan.monitored_entity_limit} varlığı izleyebilir "
            f"(şu an {current})."
        )
