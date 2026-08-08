"""Günlük yaptırım verisi senkronu + tazelik metriği + bayatlık alarmı (E1.3).

Koşu sırası:

1. **MASAK yenileme** — dondurma listesi kaynağı yapılandırılmışsa FtM dosyası
   yeniden üretilir (``aegis_core.screening.masak``).
2. **Reindex tetikleme** — ``YENTE_UPDATE_TOKEN`` varsa yente'ye delta senkron
   tetiklenir; yoksa yente'nin kendi zamanlayıcısına güvenilir.
3. **Tazelik ölçümü** — katalog okunur, ``sanctions_dataset`` tablosu güncellenir.
4. **Bayatlık alarmı** — herhangi bir küme ``sanctions_staleness_hours``dan eskiyse
   hata seviyesinde loglanır ve Sentry'ye olay gönderilir.

**Neden alarm kritik:** bayat veriyle yapılan tarama "temiz" döner ve kullanıcı bunu
"yaptırım yok" diye okur. Sessiz bayatlık, bu üründeki en pahalı hata biçimidir; bu
yüzden tazelik hem alarma hem de ``/api/v1/screenings/datasets`` üzerinden arayüze
bağlanır.

Task idempotenttir: aynı gün iki kez koşarsa aynı satırları yeniden yazar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import sentry_sdk

from aegis_core.config import Settings, get_settings
from aegis_core.logging import get_logger
from aegis_core.models import SanctionsDataset
from aegis_core.queueing import TASK_SANCTIONS_SYNC
from aegis_core.screening import masak
from aegis_core.screening.service import refresh_dataset_state_sync
from aegis_core.screening.yente import SyncYenteClient, YenteError
from aegis_worker.celery_app import celery_app
from aegis_worker.db import get_session_factory

logger = get_logger("aegis.worker.sanctions")


def _load_masak_source(settings: Settings) -> str | None:
    """MASAK kaynak içeriğini okur (önce yerel dosya, sonra URL); yoksa ``None``."""
    if settings.masak_source_path:
        path = Path(settings.masak_source_path)
        if path.exists():
            return path.read_text(encoding="utf-8-sig")
        logger.warning("masak_kaynak_dosyasi_yok", path=str(path))
    if settings.masak_source_url:
        try:
            response = httpx.get(settings.masak_source_url, timeout=60.0, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("masak_kaynak_indirilemedi", error=str(exc))
            return None
        return response.text
    return None


def _refresh_masak_dataset(settings: Settings) -> int | None:
    """MASAK FtM dosyasını yeniden üretir; kaynak yoksa ``None`` döner (job düşmez)."""
    content = _load_masak_source(settings)
    if content is None:
        logger.info("masak_kaynak_yapilandirilmamis")
        return None
    try:
        return masak.build_dataset_file(
            content,
            Path(settings.masak_entities_path),
            dataset_name=settings.masak_dataset_name,
            source_url=settings.masak_source_url,
        )
    except (OSError, ValueError) as exc:
        # MASAK adımının çökmesi, OpenSanctions tazelik ölçümünü de durdurmamalı.
        logger.error("masak_veri_kumesi_uretilemedi", error=str(exc))
        return None


def _report_staleness(datasets: list[SanctionsDataset], threshold_hours: int) -> list[str]:
    """Bayat veri kümelerini bulur, loglar ve Sentry'ye bildirir."""
    stale: list[str] = []
    for row in datasets:
        last_export = row.last_export_at
        if last_export is None:
            stale.append(f"{row.name} (dışa aktarım zamanı bilinmiyor)")
            continue
        age_hours = (row.checked_at - last_export).total_seconds() / 3600
        if age_hours > threshold_hours:
            stale.append(f"{row.name} ({age_hours:.1f} saat)")
    if stale:
        message = "Yaptırım verisi bayat: " + ", ".join(stale)
        logger.error("yaptirim_verisi_bayat", datasets=stale, threshold_hours=threshold_hours)
        sentry_sdk.capture_message(message, level="error")
    return stale


@celery_app.task(name=TASK_SANCTIONS_SYNC)
def sync_sanctions_data() -> dict[str, Any]:
    """Yaptırım verisini yeniler ve tazeliği ölçer (günlük, beat ile programlı)."""
    settings = get_settings()
    masak_entities = _refresh_masak_dataset(settings)

    client = SyncYenteClient(
        settings.yente_url,
        dataset=settings.yente_dataset,
        algorithm=settings.yente_algorithm,
        timeout_seconds=settings.yente_worker_timeout_seconds,
    )
    reindexed = False
    try:
        if settings.yente_update_token:
            reindexed = client.trigger_reindex(settings.yente_update_token)
        try:
            with get_session_factory()() as session, session.begin():
                rows = refresh_dataset_state_sync(session, client)
                stale = _report_staleness(list(rows), settings.sanctions_staleness_hours)
                dataset_count = len(rows)
        except YenteError as exc:
            # Motor erişilemiyor: tazelik ölçülemedi — bu da alarm konusudur.
            logger.error("yaptirim_senkron_basarisiz", error=str(exc))
            sentry_sdk.capture_message(f"Yaptırım senkronu başarısız: {exc}", level="error")
            return {
                "ok": False,
                "error": str(exc),
                "masak_entities": masak_entities,
                "reindex_triggered": reindexed,
            }
    finally:
        client.close()

    logger.info(
        "yaptirim_senkron_tamam",
        datasets=dataset_count,
        stale=len(stale),
        masak_entities=masak_entities,
        reindex_triggered=reindexed,
    )
    return {
        "ok": True,
        "datasets": dataset_count,
        "stale": stale,
        "masak_entities": masak_entities,
        "reindex_triggered": reindexed,
    }
