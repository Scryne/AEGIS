"""Celery uygulaması — broker/backend Redis (ayarlardan).

Task'lar idempotent tasarlanır (Ürün Planı §9: yeniden deneme + idempotent job).
E1.3'te günlük OpenSanctions senkron job'ı beat programına eklenir.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from aegis_core.config import get_settings
from aegis_core.observability import init_sentry
from aegis_core.queueing import QUEUE_DEFAULT, TASK_RETENTION_DISPOSE, TASK_SANCTIONS_SYNC


def create_celery_app() -> Celery:
    """Yapılandırılmış bir Celery uygulaması üretir."""
    settings = get_settings()
    init_sentry(settings)  # DSN yoksa no-op; CeleryIntegration task hatalarını yakalar
    app = Celery(
        "aegis",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=[
            "aegis_worker.tasks.system",
            "aegis_worker.tasks.retention",
            "aegis_worker.tasks.sanctions",
            "aegis_worker.tasks.screening",
            "aegis_worker.tasks.documents",
        ],
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
        beat_schedule={
            # E1.2 saklama süresi imhası (şimdilik kuru çalışma).
            "retention-dispose-daily": {
                "task": TASK_RETENTION_DISPOSE,
                "schedule": crontab(hour=3, minute=30),
            },
            # E1.3 yaptırım verisi senkronu + tazelik metriği + bayatlık alarmı.
            # Saat 02:00 UTC: OpenSanctions günlük dışa aktarımından sonra, imha
            # job'ından önce koşar; böylece tazelik alarmı sabah ilk iş görülür.
            "sanctions-sync-daily": {
                "task": TASK_SANCTIONS_SYNC,
                "schedule": crontab(hour=2, minute=0),
            },
        },
    )
    return app


celery_app = create_celery_app()
