"""Haftalık eşleşme kalitesi ölçümü (E3.6, ADR-0017): her kiracı için bir ``MatchEvalRun``.

Etiketi olmayan kiracıda da satır yazılır (sıfırlar): "bu hafta karar yok" da bir bilgidir ve
eğilim grafiğinde boşluk bırakmaz.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select

from aegis_core.config import get_settings
from aegis_core.db import create_engine, create_session_factory
from aegis_core.db.tenant import set_tenant_context
from aegis_core.logging import get_logger
from aegis_core.models import Organization
from aegis_core.quality import service as quality_service
from aegis_core.queueing import TASK_QUALITY_WEEKLY
from aegis_worker.celery_app import celery_app

logger = get_logger("aegis.worker.quality")


async def _run() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    done = failed = 0
    try:
        async with factory() as session:
            tenant_ids = list(await session.scalars(select(Organization.id)))
        for tenant_id in tenant_ids:
            try:
                async with factory() as session, session.begin():
                    await set_tenant_context(session, tenant_id)
                    await quality_service.snapshot(
                        session,
                        tenant_id=tenant_id,
                        reason="weekly",
                        actor_user_id=None,
                        actor_role="worker",
                    )
                done += 1
            except Exception:
                failed += 1
                logger.exception("kalite_olcum_hatasi", tenant_id=str(tenant_id))
        return {"tenants": done, "failed": failed}
    finally:
        await engine.dispose()


@celery_app.task(name=TASK_QUALITY_WEEKLY)
def weekly_quality() -> dict[str, Any]:
    """Her kiracının eşleşme kalitesini ölçer ve kayda geçirir."""
    return asyncio.run(_run())
