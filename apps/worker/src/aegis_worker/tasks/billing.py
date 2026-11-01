"""Ay sonu kullanım dökümü (E3.5, ADR-0018): her kiracının önceki dönemini dondurur.

Her gün 03:15 UTC'de koşar ve önceki dönem kapanmamışsa kapatır;
idempotenttir (dönem başına tek satır), kaçırılan bir koşu ertesi gün telafi edilir.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select

from aegis_core.billing import metering
from aegis_core.config import get_settings
from aegis_core.db import create_engine, create_session_factory
from aegis_core.db.tenant import set_tenant_context
from aegis_core.logging import get_logger
from aegis_core.models import Organization
from aegis_core.queueing import TASK_BILLING_CLOSE
from aegis_worker.celery_app import celery_app

logger = get_logger("aegis.worker.billing")


async def _run() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    closed = skipped = failed = 0
    try:
        async with factory() as session:
            tenant_ids = list(await session.scalars(select(Organization.id)))
        for tenant_id in tenant_ids:
            try:
                async with factory() as session, session.begin():
                    await set_tenant_context(session, tenant_id)
                    if await metering.close_previous_period(session, tenant_id):
                        closed += 1
                    else:
                        skipped += 1
            except Exception:
                failed += 1
                logger.exception("donem_kapanis_hatasi", tenant_id=str(tenant_id))
        return {"closed": closed, "skipped": skipped, "failed": failed}
    finally:
        await engine.dispose()


@celery_app.task(name=TASK_BILLING_CLOSE)
def close_period() -> dict[str, Any]:
    """Önceki dönemin kullanım dökümünü her kiracı için dondurur."""
    return asyncio.run(_run())
