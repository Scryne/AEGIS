"""Saklama süresi görevi (E1.2 iskelesi → E3.7 rapor modu) — KURU ÇALIŞMA.

Her gün her kiracı için süresi geçmiş kayıtları tablo başına sayar ve ``retention.dry_run``
denetim olayı yazar (``aegis_core.services.retention``). **Hiçbir şey silmez.** Gerçek silme,
rapor geçmişi incelendikten ve silme kuralları (ilişki bitişi, nesne deposu sırası, yasal saklama
istisnaları) ayrı bir kararla yazıldıktan sonra açılır. İdempotenttir.
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
from aegis_core.queueing import TASK_RETENTION_DISPOSE
from aegis_core.services import retention as retention_service
from aegis_worker.celery_app import celery_app

logger = get_logger("aegis.worker.retention")


async def _run() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    total = tenants = failed = 0
    try:
        async with factory() as session:
            tenant_ids = list(await session.scalars(select(Organization.id)))
        for tenant_id in tenant_ids:
            try:
                async with factory() as session, session.begin():
                    await set_tenant_context(session, tenant_id)
                    counts = await retention_service.dry_run(session, tenant_id=tenant_id)
                total += sum(counts.values())
                tenants += 1
            except Exception:
                failed += 1
                logger.exception("saklama_raporu_hatasi", tenant_id=str(tenant_id))
        logger.info("retention_dry_run", tenants=tenants, candidates=total, disposed=0)
        return {"tenants": tenants, "candidates": total, "disposed": 0, "failed": failed}
    finally:
        await engine.dispose()


@celery_app.task(name=TASK_RETENTION_DISPOSE)
def dispose_expired() -> dict[str, Any]:
    """Süresi geçmiş kayıtları sayar ve raporlar (kuru çalışma; silme yok)."""
    return asyncio.run(_run())
