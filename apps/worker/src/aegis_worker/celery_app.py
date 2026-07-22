"""Celery uygulaması — broker/backend Redis (ayarlardan).

Task'lar idempotent tasarlanır (Ürün Planı §9: yeniden deneme + idempotent job).
E1.3'te günlük OpenSanctions senkron job'ı beat programına eklenir.
"""

from __future__ import annotations

from celery import Celery

from aegis_core.config import get_settings
from aegis_core.observability import init_sentry
from aegis_core.queueing import QUEUE_DEFAULT


def create_celery_app() -> Celery:
    """Yapılandırılmış bir Celery uygulaması üretir."""
    settings = get_settings()
    init_sentry(settings)  # DSN yoksa no-op; CeleryIntegration task hatalarını yakalar
    app = Celery(
        "aegis",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["aegis_worker.tasks.system"],
    )
    app.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_track_started=True,
        worker_prefetch_multiplier=1,
        task_default_queue=QUEUE_DEFAULT,
        result_expires=3600,
        timezone="UTC",
        enable_utc=True,
        # E1.3'te günlük yaptırım-veri senkron job'ı buraya eklenir.
        beat_schedule={},
    )
    return app


celery_app = create_celery_app()
