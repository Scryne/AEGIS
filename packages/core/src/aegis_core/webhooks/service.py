"""Webhook servisi (E3.4, ADR-0016): uç yönetimi, olay yayma, teslim + yeniden deneme.

Olay yayma (``emit``) iş işlemiyle **aynı transaction**'da teslim satırları yazar (giden kutusu):
iş geri alınırsa olay da yazılmaz, iş commit edilirse teslim kaybolmaz. Teslimi worker yapar
(``deliver_due``); ağ çağrısı hiçbir zaman iş isteğinin içinde değildir.

Yük kişisel veri taşımaz: olay adı, olay kimliği, zaman ve nesne kimlikleri/durumları. Alıcı
ayrıntıyı API'den kimliğiyle çeker (KVKK: veri bizim ortamımızdan yalnız müşterinin kendi
çağrısıyla çıkar).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.config import Settings
from aegis_core.logging import get_logger
from aegis_core.models import AuditAction, WebhookDelivery, WebhookEndpoint
from aegis_core.services import audit as audit_service
from aegis_core.webhooks import signing

logger = get_logger("aegis.webhooks")

MAX_ENDPOINTS = 10


class WebhookError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _check(url: str, settings: Settings) -> None:
    try:
        signing.check_url(
            url,
            allow_http=settings.webhook_allow_http,
            allow_private=settings.webhook_allow_private,
        )
    except signing.UnsafeUrlError as exc:
        raise WebhookError("invalid", str(exc)) from exc


def _events(events: Sequence[str]) -> list[str]:
    unknown = [e for e in events if e not in signing.EVENTS]
    if unknown or not events:
        raise WebhookError(
            "invalid", f"Olay listesi geçersiz. Seçenekler: {', '.join(signing.EVENTS)}"
        )
    return sorted(set(events))


async def create_endpoint(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    url: str,
    events: Sequence[str],
    description: str | None,
    settings: Settings,
    actor_user_id: uuid.UUID,
    actor_role: str,
) -> tuple[WebhookEndpoint, str]:
    _check(url, settings)
    count = len(list(await session.scalars(select(WebhookEndpoint.id))))
    if count >= MAX_ENDPOINTS:
        raise WebhookError("invalid", f"En çok {MAX_ENDPOINTS} webhook adresi tanımlanabilir.")
    secret = signing.new_secret()
    endpoint = WebhookEndpoint(
        tenant_id=tenant_id,
        url=url.strip(),
        description=(description or "").strip()[:200] or None,
        secret=secret,
        events=_events(events),
        created_by_user_id=actor_user_id,
    )
    session.add(endpoint)
    await session.flush()
    await _audit(session, endpoint, AuditAction.WEBHOOK_CREATE, actor_user_id, actor_role)
    return endpoint, secret


async def update_endpoint(
    session: AsyncSession,
    endpoint: WebhookEndpoint,
    *,
    url: str | None,
    events: Sequence[str] | None,
    active: bool | None,
    settings: Settings,
    actor_user_id: uuid.UUID,
    actor_role: str,
) -> WebhookEndpoint:
    if url is not None:
        _check(url, settings)
        endpoint.url = url.strip()
    if events is not None:
        endpoint.events = _events(events)
    if active is not None:
        endpoint.active = active
    await session.flush()
    await _audit(session, endpoint, AuditAction.WEBHOOK_UPDATE, actor_user_id, actor_role)
    return endpoint


async def rotate_secret(
    session: AsyncSession, endpoint: WebhookEndpoint, *, actor_user_id: uuid.UUID, actor_role: str
) -> str:
    secret = signing.new_secret()
    endpoint.secret = secret
    await session.flush()
    await _audit(
        session, endpoint, AuditAction.WEBHOOK_UPDATE, actor_user_id, actor_role, rotated=True
    )
    return secret


async def _audit(
    session: AsyncSession,
    endpoint: WebhookEndpoint,
    action: AuditAction,
    actor_user_id: uuid.UUID,
    actor_role: str,
    **extra: Any,
) -> None:
    await audit_service.record_event(
        session,
        tenant_id=endpoint.tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        object_type="webhook_endpoint",
        object_id=str(endpoint.id),
        payload={
            "url": endpoint.url,
            "events": endpoint.events,
            "active": endpoint.active,
            **extra,
        },
    )


def _body(event: str, event_id: uuid.UUID, data: dict[str, Any], at: datetime) -> dict[str, Any]:
    return {"id": str(event_id), "type": event, "created_at": at.isoformat(), "data": data}


async def emit(
    session: AsyncSession, *, tenant_id: uuid.UUID, event: str, data: dict[str, Any]
) -> int:
    """Olayı abone uçlar için teslim kuyruğuna yazar (aynı transaction). Yazılan satır sayısı."""
    endpoints = list(
        await session.scalars(
            select(WebhookEndpoint).where(
                WebhookEndpoint.tenant_id == tenant_id, WebhookEndpoint.active.is_(True)
            )
        )
    )
    targets = [e for e in endpoints if event in (e.events or [])]
    if not targets:
        return 0
    now = datetime.now(UTC)
    event_id = uuid.uuid4()
    payload = _body(event, event_id, data, now)
    for endpoint in targets:
        session.add(
            WebhookDelivery(
                tenant_id=tenant_id,
                endpoint_id=endpoint.id,
                event=event,
                event_id=event_id,
                payload=payload,
                status="pending",
                next_attempt_at=now,
            )
        )
    await session.flush()
    return len(targets)


async def send_test(session: AsyncSession, endpoint: WebhookEndpoint) -> WebhookDelivery:
    now = datetime.now(UTC)
    event_id = uuid.uuid4()
    delivery = WebhookDelivery(
        tenant_id=endpoint.tenant_id,
        endpoint_id=endpoint.id,
        event="ping",
        event_id=event_id,
        payload=_body("ping", event_id, {"endpoint_id": str(endpoint.id)}, now),
        status="pending",
        next_attempt_at=now,
    )
    session.add(delivery)
    await session.flush()
    return delivery


async def redeliver(session: AsyncSession, delivery: WebhookDelivery) -> WebhookDelivery:
    """Ölü ya da başarısız teslimi yeniden kuyruğa alır (deneme sayacı sıfırlanır)."""
    delivery.status = "pending"
    delivery.attempts = 0
    delivery.next_attempt_at = datetime.now(UTC)
    delivery.last_error = None
    await session.flush()
    return delivery


async def _attempt(
    client: httpx.AsyncClient,
    endpoint: WebhookEndpoint,
    delivery: WebhookDelivery,
    settings: Settings,
    now: datetime,
) -> tuple[int | None, str | None]:
    try:
        # Ad çözümlemesi engelleyicidir; olay döngüsünü tutmasın. DNS kayıttan sonra değişmiş
        # olabileceği için her teslimde yeniden denetlenir.
        await asyncio.to_thread(
            signing.check_url,
            endpoint.url,
            allow_http=settings.webhook_allow_http,
            allow_private=settings.webhook_allow_private,
        )
    except signing.UnsafeUrlError as exc:
        return None, str(exc)
    body = json.dumps(delivery.payload, ensure_ascii=False, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "AEGIS-Webhooks/1",
        signing.EVENT_HEADER: delivery.event,
        signing.DELIVERY_HEADER: str(delivery.id),
        signing.SIGNATURE_HEADER: signing.sign(endpoint.secret, body, int(now.timestamp())),
    }
    try:
        res = await client.post(endpoint.url, content=body, headers=headers, timeout=10.0)
    except httpx.HTTPError as exc:
        return None, f"Bağlantı hatası: {type(exc).__name__}"
    if 200 <= res.status_code < 300:
        return res.status_code, None
    return res.status_code, f"Alıcı {res.status_code} döndü."


async def deliver_due(
    session: AsyncSession,
    client: httpx.AsyncClient,
    *,
    settings: Settings,
    limit: int = 50,
    now: datetime | None = None,
) -> dict[str, int]:
    """Zamanı gelen teslimleri dener (RLS ile etkin kiracıya sınırlı)."""
    at = now or datetime.now(UTC)
    rows = list(
        await session.scalars(
            select(WebhookDelivery)
            .where(WebhookDelivery.status == "pending", WebhookDelivery.next_attempt_at <= at)
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    delivered = retried = dead = 0
    for delivery in rows:
        endpoint = await session.get(WebhookEndpoint, delivery.endpoint_id)
        if endpoint is None or not endpoint.active:
            delivery.status = "skipped"
            delivery.last_error = "Uç kapalı ya da silinmiş."
            continue
        code, error = await _attempt(client, endpoint, delivery, settings, at)
        delivery.attempts += 1
        delivery.last_status_code = code
        delivery.last_error = error
        if error is None:
            delivery.status = "delivered"
            delivery.delivered_at = at
            delivery.next_attempt_at = None
            delivered += 1
            continue
        nxt = signing.next_attempt(delivery.attempts, at)
        if nxt is None:
            delivery.status = "dead"
            delivery.next_attempt_at = None
            dead += 1
        else:
            delivery.next_attempt_at = nxt
            retried += 1
    await session.flush()
    return {"attempted": len(rows), "delivered": delivered, "retrying": retried, "dead": dead}
