"""Belge çıkarım task'ı — PDF → metin → öneriler (E1.4, R2).

Yükleme isteğini bekletmemek için asenkrondur: Docling ağır bir motordur (ilk çağrıda
model yükler) ve kullanıcı ekran başında beklememelidir.

``asyncio.run`` gerekçesi E1.3'teki derin tarama task'ıyla aynıdır: denetim izi hash
zincirini yazan tek bir (async) uygulama vardır; worker için ikinci bir kopya yazmak
kanonik biçimin ayrışması riskini doğururdu.

**Motor yoksa görev başarısız sayılmaz.** Docling opsiyonel kurulumdur; yoksa belge
``skipped`` işaretlenir ve yükleme/saklama akışı bozulmaz — kullanıcı alanları elle
girer (Revizyon R1'in "manuel giriş" yolu zaten birincil yollardan biridir).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from aegis_core.config import get_settings
from aegis_core.db import create_engine, create_session_factory
from aegis_core.db.tenant import set_tenant_context
from aegis_core.documents import service as document_service
from aegis_core.documents.docling_adapter import (
    ExtractionEngineUnavailableError,
    convert,
)
from aegis_core.documents.extraction import extract_from_text
from aegis_core.documents.storage import StorageError, get_object
from aegis_core.logging import get_logger
from aegis_core.models import ExtractionStatus
from aegis_core.queueing import TASK_DOCUMENT_EXTRACT
from aegis_worker.celery_app import celery_app

logger = get_logger("aegis.worker.documents")


async def _extract_document(*, tenant_id: uuid.UUID, document_id: uuid.UUID) -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            await set_tenant_context(session, tenant_id)
            document = await document_service.get_document(session, document_id)
            if document is None:
                logger.warning("cikarim_belge_yok", document_id=str(document_id))
                return {"document_id": str(document_id), "status": "not_found"}
            if document.extraction_status != ExtractionStatus.PENDING.value:
                # İdempotanlık: görev yeniden teslim edildiyse ikinci kez koşmaz.
                return {"document_id": str(document_id), "status": document.extraction_status}

            try:
                data = await asyncio.to_thread(get_object, document.storage_key, settings)
            except StorageError as exc:
                await document_service.mark_extraction_failed(
                    session, document, error=f"Belge depodan okunamadı: {exc}"
                )
                return {"document_id": str(document_id), "status": "failed"}

            try:
                converted = await asyncio.to_thread(
                    convert,
                    data,
                    filename=document.filename,
                    content_type=document.content_type,
                )
            except ExtractionEngineUnavailableError as exc:
                await document_service.mark_extraction_failed(
                    session, document, error=str(exc), skipped=True
                )
                return {"document_id": str(document_id), "status": "skipped"}
            except Exception as exc:
                await document_service.mark_extraction_failed(
                    session, document, error=f"Belge metne çevrilemedi: {exc}"
                )
                return {"document_id": str(document_id), "status": "failed"}

            result = extract_from_text(converted.text, document.doc_type)
            proposals = await document_service.store_extraction_result(
                session,
                document,
                result,
                engine=converted.engine,
                page_count=converted.page_count,
            )
            return {
                "document_id": str(document_id),
                "status": ExtractionStatus.COMPLETED.value,
                "proposals": len(proposals),
                "engine": converted.engine,
            }
    finally:
        await engine.dispose()


@celery_app.task(name=TASK_DOCUMENT_EXTRACT, bind=True, max_retries=2, default_retry_delay=60)
def extract_document(
    self: Any, *, tenant_id: str, document_id: str, actor_role: str | None = None
) -> dict[str, Any]:
    """Bir belgeyi metne çevirip öneri satırlarını üretir (idempotent).

    Öneriler **insan onayı** bekler; bu görev kütüğe hiçbir şey yazmaz (Revizyon R2).
    """
    return asyncio.run(
        _extract_document(
            tenant_id=uuid.UUID(tenant_id),
            document_id=uuid.UUID(document_id),
        )
    )
