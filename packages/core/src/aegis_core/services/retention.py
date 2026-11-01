"""Saklama süresi raporu (E3.7) — KURU ÇALIŞMA: sayar ve kayda geçirir, hiçbir şey silmez.

Invariant 4: belge ve kayıt tabloları ``retention_until`` taşır (``RetentionMixin``). Yol haritası
gerçek silmeden önce rapor modunu ister: her gün, süresi geçmiş adaylar kiracı ve tablo başına
sayılır ve ``retention.dry_run`` denetim olayı olarak yazılır. Böylece silme açılmadan önce
"neler silinecekti" geçmişi birikir ve kontrol edilir.

Gerçek silme bilinçli olarak yok: hangi kaydın ne zaman "ilişki bitti" sayılacağı, nesne deposundaki
dosyanın satırdan önce mi sonra mı silineceği ve yasal saklama istisnaları (inceleme, dava) ayrı bir
karardır (ADR gerektirir). Silme etkinleşene kadar bu rapor tek yetkili çıktıdır.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.models import (
    AuditAction,
    Document,
    Entity,
    Report,
    RiskScoreSnapshot,
    Screening,
    ScreeningBatch,
    SibDraft,
    UboComputation,
)
from aegis_core.services import audit as audit_service

TABLES: tuple[Any, ...] = (
    Document,
    Entity,
    Report,
    RiskScoreSnapshot,
    Screening,
    ScreeningBatch,
    SibDraft,
    UboComputation,
)


async def candidates(session: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """Etkin kiracıda (RLS) süresi geçmiş kayıt sayısı, tablo başına."""
    at = now or datetime.now(UTC)
    out: dict[str, int] = {}
    for model in TABLES:
        n = await session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.retention_until.is_not(None), model.retention_until < at)
        )
        out[model.__tablename__] = int(n or 0)
    return out


async def dry_run(
    session: AsyncSession, *, tenant_id: uuid.UUID, now: datetime | None = None
) -> dict[str, int]:
    """Adayları sayar ve denetim izine yazar (aday yoksa da yazar: "kontrol edildi" kanıtı)."""
    counts = await candidates(session, now=now)
    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        actor_role="worker",
        action=AuditAction.RETENTION_DRY_RUN,
        object_type="retention",
        object_id=None,
        payload={"mode": "dry_run", "candidates": counts, "total": sum(counts.values())},
    )
    return counts
