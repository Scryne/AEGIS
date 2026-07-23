"""Saklama süresi imha task'ı — E1.2 iskele (KURU ÇALIŞMA).

Invariant 4 (KVKK ≥5 yıl): belge/dosya tabloları ``retention_until`` taşır
(``RetentionMixin``). Bu task, süresi geçmiş kayıtları temizlemek için beat'e günlük
programlanır — ama **şimdilik hiçbir şey silmez**. Gerçek silme, önce kuru-çalışma
rapor modu ile E3.7'de etkinleşir; ayrıca imha edilecek belge tabloları E1.4/E1.5'te gelir.
Şimdiden programlanmasının nedeni: operasyonel yol (beat girdisi + idempotent task) faz
sınırında yeniden inşa edilmesin.
"""

from __future__ import annotations

from aegis_core.logging import get_logger
from aegis_core.queueing import TASK_RETENTION_DISPOSE
from aegis_worker.celery_app import celery_app

logger = get_logger("aegis.worker.retention")


@celery_app.task(name=TASK_RETENTION_DISPOSE)
def dispose_expired() -> dict[str, int]:
    """Süresi geçmiş kayıtları imha eder — iskele: yalnız kuru çalışma, 0 döner.

    Silme mantığı ve aday sayımı, belge tabloları var olduğunda (E1.4/E1.5) ve imha
    E3.7'de etkinleştiğinde eklenir. İdempotenttir: tekrar çağrılması güvenlidir.
    """
    logger.info("retention_dispose_dry_run", candidates=0, disposed=0)
    return {"candidates": 0, "disposed": 0}
