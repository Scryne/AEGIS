"""Webhook teslim görevi (E3.4, ADR-0016): her 30 sn zamanı gelen teslimleri dener.

Kiracı başına ayrı transaction ve RLS bağlamı (izleme gece göreviyle aynı desen); teslimler
``FOR UPDATE SKIP LOCKED`` ile alındığı için iki worker aynı teslimi iki kez göndermez.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from sqlalchemy import select

from aegis_core.config import get_settings
from aegis_core.db import create_engine, create_session_factory
from aegis_core.db.tenant import set_tenant_context
from aegis_core.logging import get_logger
from aegis_core.models import Organization
from aegis_core.queueing import TASK_WEBHOOKS_DELIVER
from aegis_core.webhooks import service as webhook_service
from aegis_worker.celery_app import celery_app

logger = get_logger("aegis.worker.webhooks")


async def _run(client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    own = client is None
    http = client or httpx.AsyncClient(follow_redirects=False)
    totals = {"attempted": 0, "delivered": 0, "retrying": 0, "dead": 0}
    try:
        async with factory() as session:
            tenant_ids = list(await session.scalars(select(Organization.id)))
        for tenant_id in tenant_ids:
            try:
                async with factory() as session, session.begin():
                    await set_tenant_context(session, tenant_id)
                    result = await webhook_service.deliver_due(session, http, settings=settings)
                for k in totals:
                    totals[k] += result[k]
            except Exception:
                logger.exception("webhook_kiraci_hatasi", tenant_id=str(tenant_id))
        if totals["attempted"]:
            logger.info("webhook_teslim_turu", **totals)
        return totals
    finally:
        if own:
            await http.aclose()
        await engine.dispose()


@celery_app.task(name=TASK_WEBHOOKS_DELIVER)
def deliver_webhooks() -> dict[str, Any]:
    """Zamanı gelen webhook teslimlerini dener."""
    return asyncio.run(_run())
