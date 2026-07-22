"""Sentry entegrasyonu: DSN-kapılı init + kiracı bağlamı + PII maskeleme.

- ``init_sentry``: ``SENTRY_DSN`` boşsa tamamen no-op — dev/test Sentry gerektirmez.
- **PII maskeleme:** ``send_default_pii=False`` + ``before_send`` scrub'ı; istek
  gövdesi/cookie/hassas başlıklar/sorgu dizesi gönderilmez, kullanıcı yalnız ID taşır.
"""

from __future__ import annotations

import uuid

import sentry_sdk
from sentry_sdk.types import Event, Hint

from aegis_core.config import Settings

# İzin verilen istek başlıkları (küçük harf) — geri kalanı maskelenir.
_SAFE_REQUEST_HEADERS = frozenset(
    {"accept", "content-length", "content-type", "user-agent", "x-request-id"}
)


def init_sentry(settings: Settings) -> bool:
    """Sentry'yi başlatır; DSN yapılandırılmamışsa ``False`` döner (no-op)."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment.value,
        send_default_pii=False,
        before_send=scrub_event,
        traces_sample_rate=0.0,
    )
    return True


def scrub_event(event: Event, _hint: Hint | None = None) -> Event:
    """Sentry olayından PII sızabilecek alanları temizler (before_send)."""
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("cookies", None)
        request.pop("data", None)  # istek gövdesi (yüklenen içerik/parola) asla gitmez
        request.pop("env", None)
        request.pop("query_string", None)
        url = request.get("url")
        if isinstance(url, str) and "?" in url:
            request["url"] = url.split("?", 1)[0]
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                key: value for key, value in headers.items() if key.lower() in _SAFE_REQUEST_HEADERS
            }
    user = event.get("user")
    if isinstance(user, dict):
        event["user"] = {"id": user["id"]} if "id" in user else {}
    return event


def bind_sentry_tags(**tags: uuid.UUID | str | None) -> None:
    """Korelasyon tag'lerini (tenant_id, job_id, ...) mevcut Sentry scope'una bağlar."""
    for key, value in tags.items():
        if value is not None:
            sentry_sdk.set_tag(key, str(value))
