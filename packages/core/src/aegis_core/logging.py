"""Yapılandırılmış (JSON) loglama + korelasyon kimlikleri (structlog).

Her log kaydı, aktif istekle ilişkili korelasyon kimliklerini taşır:
``request_id``, ``tenant_id``, ``job_id``. PII yerine yalnız kimlik/korelasyon.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import cast

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
tenant_id_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)

_CORRELATION_VARS: tuple[tuple[str, ContextVar[str | None]], ...] = (
    ("request_id", request_id_var),
    ("tenant_id", tenant_id_var),
    ("job_id", job_id_var),
)


def add_correlation_ids(
    _logger: WrappedLogger, _method_name: str, event_dict: EventDict
) -> EventDict:
    """Aktif contextvar korelasyon kimliklerini log kaydına ekler."""
    for key, var in _CORRELATION_VARS:
        value = var.get()
        if value is not None:
            event_dict[key] = value
    return event_dict


def configure_logging(*, json_logs: bool = True, level: str = "INFO") -> None:
    """structlog'u JSON (prod) veya renkli konsol (dev) çıktısına ayarlar."""
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_correlation_ids,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=True)
    )
    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.typing.FilteringBoundLogger:
    """İsimlendirilmiş bir yapılandırılmış logger döndürür."""
    return cast("structlog.typing.FilteringBoundLogger", structlog.get_logger(name))
