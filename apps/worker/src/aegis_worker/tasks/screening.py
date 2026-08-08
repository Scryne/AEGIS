"""Derin tarama task'ı — çok özneli koşular (E1.3).

Senkron API yolu tek varlık için < 30 sn NFR'sini korumak zorundadır; şirket + tüm
yöneticiler/UBO'lar taranacaksa iş buraya devredilir (``POST /screenings/deep``).

**Neden ``asyncio.run``?** Denetim izi hash zincirini (Invariant 2) yazan tek bir
uygulama vardır ve o async'tir. Worker için ikinci, senkron bir kopya yazmak zincirin
kanonik biçiminin iki yerde ayrışması riskini doğururdu — kurcalama tespitini sessizce
bozacak türden bir hata. Bu yüzden worker, aynı async servisi kendi event loop'unda
çalıştırır. Engine görev başına açılıp kapatılır: ``asyncio.run`` her çağrıda yeni bir
loop kurar, önceki loop'a bağlı bir havuz yeniden kullanılamaz.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from aegis_core.config import get_settings
from aegis_core.db import create_engine, create_session_factory
from aegis_core.db.tenant import set_tenant_context
from aegis_core.logging import get_logger
from aegis_core.models import ScreeningStatus
from aegis_core.queueing import TASK_SCREENING_RUN
from aegis_core.screening import service as screening_service
from aegis_core.screening.yente import YenteClient
from aegis_worker.celery_app import celery_app

logger = get_logger("aegis.worker.screening")


async def _run_deep_screening(
    *,
    tenant_id: uuid.UUID,
    screening_id: uuid.UUID,
    identifiers: dict[str, dict[str, str]],
    actor_role: str | None,
) -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    client = YenteClient(
        settings.yente_url,
        dataset=settings.yente_dataset,
        algorithm=settings.yente_algorithm,
        timeout_seconds=settings.yente_worker_timeout_seconds,
    )
    try:
        async with factory() as session, session.begin():
            await set_tenant_context(session, tenant_id)
            screening = await screening_service.get_screening(session, screening_id)
            if screening is None:
                # RLS altında bulunamadı: yanlış kiracı ya da kayıt silinmiş.
                logger.warning("derin_tarama_kayit_yok", screening_id=str(screening_id))
                return {"screening_id": str(screening_id), "status": "not_found"}
            if screening.status != ScreeningStatus.QUEUED.value:
                # İdempotanlık: görev yeniden teslim edildiyse ikinci kez koşmaz.
                logger.info(
                    "derin_tarama_atlandi",
                    screening_id=str(screening_id),
                    status=screening.status,
                )
                return {"screening_id": str(screening_id), "status": screening.status}
            result = await screening_service.run_existing_screening(
                session,
                client,
                screening,
                identifiers=identifiers,
                actor_role=actor_role,
                limit=settings.screening_candidate_limit,
            )
            return {
                "screening_id": str(result.id),
                "status": result.status,
                "candidates": result.candidate_count,
            }
    finally:
        await client.aclose()
        await engine.dispose()


@celery_app.task(name=TASK_SCREENING_RUN, bind=True, max_retries=3, default_retry_delay=30)
def run_deep_screening(
    self: Any,
    *,
    tenant_id: str,
    screening_id: str,
    identifiers: dict[str, dict[str, str]] | None = None,
    actor_role: str | None = None,
) -> dict[str, Any]:
    """Kuyruğa alınmış bir taramayı çalıştırır.

    İdempotenttir: yalnız ``queued`` durumundaki kayıt işlenir. Motor hatası koşuyu
    ``failed`` yapar ve **yeniden denenmez** — kayıt zaten hatayı taşır ve kullanıcı
    yeniden başlatabilir; sessiz tekrar denemeler denetim izini şişirirdi.
    """
    return asyncio.run(
        _run_deep_screening(
            tenant_id=uuid.UUID(tenant_id),
            screening_id=uuid.UUID(screening_id),
            identifiers=identifiers or {},
            actor_role=actor_role,
        )
    )
