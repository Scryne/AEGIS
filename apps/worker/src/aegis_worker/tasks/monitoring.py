"""İzleme-lite gece görevi (E2.4): her kiracının izlenen varlıklarını yeniden tarar.

Yaptırım senkronundan (02:00 UTC) sonra 02:45'te koşar: yeni veri kümesiyle tarama yapılır ve
önceki koşuyla fark alarm olur. Her kiracı kendi transaction'ında ve kendi RLS bağlamında işlenir;
bir kiracının hatası diğerlerini durdurmaz. Asenkron çekirdek ``asyncio.run`` ile çağrılır (derin
tarama göreviyle aynı gerekçe: denetim izinin hash zincirini yazan tek kod yolu).
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
from aegis_core.monitoring import notify as monitoring_notify
from aegis_core.monitoring import service as monitoring_service
from aegis_core.notifications.email import default_sender
from aegis_core.queueing import TASK_MONITORING_DIGEST, TASK_MONITORING_NIGHTLY
from aegis_core.screening.yente import YenteClient
from aegis_worker.celery_app import celery_app

logger = get_logger("aegis.worker.monitoring")


async def _run_all() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    client = YenteClient(
        settings.yente_url,
        dataset=settings.yente_dataset,
        algorithm=settings.yente_algorithm,
        timeout_seconds=settings.yente_worker_timeout_seconds,
    )
    sender = default_sender(settings)
    totals = {"tenants": 0, "checked": 0, "alerts": 0, "failed": 0, "skipped": 0, "notified": 0}
    try:
        async with factory() as session:
            tenant_ids = list(await session.scalars(select(Organization.id)))
        for tenant_id in tenant_ids:
            totals["tenants"] += 1
            try:
                async with factory() as session, session.begin():
                    await set_tenant_context(session, tenant_id)
                    result = await monitoring_service.run_for_tenant(
                        session, client, tenant_id=tenant_id, settings=settings, trigger="nightly"
                    )
                    runs = await monitoring_service.latest_runs(session, limit=1)
                    sent = await monitoring_notify.deliver(
                        session,
                        tenant_id=tenant_id,
                        settings=settings,
                        sender=sender,
                        mode="immediate",
                        run=runs[0] if runs else None,
                    )
                totals["notified"] += sent["alerts"] if sent["status"] == "sent" else 0
                for key in ("checked", "alerts", "failed", "skipped"):
                    totals[key] += result[key]
            except Exception:
                totals["failed"] += 1
                logger.exception("izleme_kiraci_hatasi", tenant_id=str(tenant_id))
        logger.info("izleme_gece_kosusu", **totals)
        return totals
    finally:
        await client.aclose()
        await engine.dispose()


async def _digest_all() -> dict[str, int]:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    sender = default_sender(settings)
    totals = {"tenants": 0, "sent": 0, "skipped": 0, "failed": 0}
    try:
        async with factory() as session:
            tenant_ids = list(await session.scalars(select(Organization.id)))
        for tenant_id in tenant_ids:
            totals["tenants"] += 1
            try:
                async with factory() as session, session.begin():
                    await set_tenant_context(session, tenant_id)
                    result = await monitoring_notify.deliver(
                        session,
                        tenant_id=tenant_id,
                        settings=settings,
                        sender=sender,
                        mode="digest",
                    )
                totals["sent" if result["status"] == "sent" else "skipped"] += 1
            except Exception:
                totals["failed"] += 1
                logger.exception("izleme_ozet_hatasi", tenant_id=str(tenant_id))
        logger.info("izleme_gunluk_ozet", **totals)
        return totals
    finally:
        await engine.dispose()


@celery_app.task(name=TASK_MONITORING_DIGEST)
def send_monitoring_digest() -> dict[str, int]:
    """Bekleyen alarmların günlük özetini gönderir; gidemeyenler dahil."""
    return asyncio.run(_digest_all())


@celery_app.task(name=TASK_MONITORING_NIGHTLY)
def run_nightly_monitoring() -> dict[str, Any]:
    """İzlenen varlıkları yeniden tarar ve önemli farkları alarm olarak yazar."""
    return asyncio.run(_run_all())
