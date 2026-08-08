"""Kuyruk üreticisi — API, işleri **ada göre** yayınlar (worker kodunu import etmez).

``aegis_core.queueing`` yalnız task adlarını tanımlar; burada o adlara Celery'nin
``send_task``ı ile mesaj bırakılır. Bu ayrım sayesinde API imajı worker'ın bağımlılık
ağacını (Docling, tarama kütüphaneleri …) taşımak zorunda kalmaz.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from celery import Celery

from aegis_core.logging import get_logger
from aegis_core.queueing import QUEUE_DEFAULT

logger = get_logger("aegis.api.queue")


@lru_cache(maxsize=4)
def get_producer(broker_url: str) -> Celery:
    """Broker başına tek (önbelleğe alınmış) üretici istemci döndürür."""
    return Celery("aegis-producer", broker=broker_url)


def dispatch(
    task_name: str,
    *,
    kwargs: dict[str, Any],
    redis_url: str,
    queue: str = QUEUE_DEFAULT,
) -> str:
    """Bir işi kuyruğa bırakır ve task kimliğini döndürür.

    Mesaj gövdesi, veritabanına maskeli yazdığımız kimlik numaralarını taşıyabilir
    (bkz. derin tarama ucu): broker kendi ortamımızdadır ve mesaj işlendiğinde silinir.
    """
    result = get_producer(redis_url).send_task(task_name, kwargs=kwargs, queue=queue)
    task_id = str(result.id)
    logger.info("kuyruga_alindi", task=task_name, task_id=task_id, queue=queue)
    return task_id
