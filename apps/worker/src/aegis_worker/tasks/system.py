"""Sistem/sağlık task'ları."""

from __future__ import annotations

from aegis_core.queueing import TASK_PING
from aegis_worker.celery_app import celery_app


@celery_app.task(name=TASK_PING)
def ping() -> str:
    """Basit sağlık task'ı — ``"pong"`` döner (worker canlılığı doğrulaması)."""
    return "pong"
