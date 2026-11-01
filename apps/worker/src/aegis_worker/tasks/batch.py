"""Toplu tarama görevi (E3.3, ADR-0015): bir toplu işin bekleyen satırlarını parça parça işler.

Her parça (``CHUNK`` satır) kendi transaction'ında ve kiracının RLS bağlamında işlenir; parça
commit edildikten sonra bir sonrakine geçilir. Süreç yarıda ölürse işlenmiş parçalar kalıcıdır,
kalan ``pending`` satırlar görev yeniden çalıştırıldığında (ya da "şimdi işle" ile) devam eder.
İptal edilen toplu iş bir sonraki parçada durur.

API görevi kendi transaction'ı commit edilmeden kuyruğa bırakır; görev toplu işi henüz göremezse
(ya da hâlâ taslak görürse) kısa aralıkla yeniden denenir.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from aegis_core.batch import service as batch_service
from aegis_core.config import get_settings
from aegis_core.db import create_engine, create_session_factory
from aegis_core.db.tenant import set_tenant_context
from aegis_core.logging import get_logger
from aegis_core.models import BatchStatus, ScreeningBatch
from aegis_core.queueing import TASK_BATCH_PROCESS
from aegis_core.screening.yente import YenteClient
from aegis_worker.celery_app import celery_app

logger = get_logger("aegis.worker.batch")

CHUNK = 25


async def _run(tenant_id: uuid.UUID, batch_id: uuid.UUID) -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    client = YenteClient(
        settings.yente_url,
        dataset=settings.yente_dataset,
        algorithm=settings.yente_algorithm,
        timeout_seconds=settings.yente_worker_timeout_seconds,
    )
    totals: dict[str, Any] = {
        "processed": 0,
        "done": 0,
        "needs_review": 0,
        "failed": 0,
        "remaining": -1,
        "not_visible": False,
    }
    first = True
    try:
        while True:
            async with factory() as session, session.begin():
                await set_tenant_context(session, tenant_id)
                batch = await session.get(ScreeningBatch, batch_id, with_for_update=True)
                if first and (batch is None or batch.status == BatchStatus.DRAFT.value):
                    totals["not_visible"] = True
                    break
                first = False
                if batch is None or batch.status not in (
                    BatchStatus.QUEUED.value,
                    BatchStatus.RUNNING.value,
                ):
                    break
                result = await batch_service.process_rows(
                    session, client, batch, settings=settings, limit=CHUNK
                )
            for key in ("processed", "done", "needs_review", "failed"):
                totals[key] += result[key]
            totals["remaining"] = result["remaining"]
            if result["remaining"] == 0 or result["processed"] == 0:
                break
        logger.info("toplu_tarama_parcasi_bitti", batch_id=str(batch_id), **totals)
        return totals
    finally:
        await client.aclose()
        await engine.dispose()


@celery_app.task(name=TASK_BATCH_PROCESS, bind=True, max_retries=5)
def process_batch(self: Any, tenant_id: str, batch_id: str) -> dict[str, Any]:
    """Toplu işin bekleyen satırlarını bitene (ya da iptal edilene) kadar işler."""
    result = asyncio.run(_run(uuid.UUID(tenant_id), uuid.UUID(batch_id)))
    if result["not_visible"]:
        raise self.retry(countdown=2)
    return result
