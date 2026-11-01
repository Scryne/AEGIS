"""/api/v1/api-keys ve /api/v1/webhooks — entegrasyon yönetimi (E3.4, ADR-0016).

Yetkilendirme:

- **API anahtarı**: oluşturma ve iptal yalnız ``owner``; liste owner · compliance_officer ·
  auditor. Tam anahtar yalnız oluşturma yanıtında döner.
- **Webhook**: yönetim (oluştur, güncelle, sır yenile, test, yeniden gönder) owner ·
  compliance_officer; teslim kaydı okuma owner · compliance_officer · auditor.
- API anahtarıyla gelen istek bu uçların hiçbirini kullanamaz (anahtar rolleri analist/denetçi;
  ayrıca açık kontrol): bir anahtar başka anahtar açamaz, webhook yönlendiremez.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from aegis_api.dependencies import (
    Principal,
    SettingsDep,
    TenantSessionDep,
    require_role,
)
from aegis_api.errors import AppError, ForbiddenError, NotFoundError, ValidationFailedError
from aegis_core.integrations import api_keys as api_key_service
from aegis_core.models import ApiKey, Role, WebhookDelivery, WebhookEndpoint
from aegis_core.webhooks import service as webhook_service
from aegis_core.webhooks.signing import EVENTS

router = APIRouter(tags=["integrations"])


def _human(principal: Principal) -> Principal:
    if principal.api_key_id is not None:
        raise ForbiddenError("Entegrasyon ayarları API anahtarıyla değiştirilemez.")
    return principal


async def _owner(
    principal: Annotated[Principal, Depends(require_role(Role.OWNER))],
) -> Principal:
    return _human(principal)


async def _manager(
    principal: Annotated[Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER))],
) -> Principal:
    return _human(principal)


async def _reader(
    principal: Annotated[
        Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.AUDITOR))
    ],
) -> Principal:
    return _human(principal)


OwnerDep = Annotated[Principal, Depends(_owner)]
ManagerDep = Annotated[Principal, Depends(_manager)]
ReaderDep = Annotated[Principal, Depends(_reader)]


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    role: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    role: str = Field(pattern="^(analyst|auditor)$")
    expires_in_days: int | None = Field(default=None, ge=1, le=730)


class ApiKeyCreatedResponse(ApiKeyResponse):
    key: str
    """Tam anahtar — yalnız bu yanıtta gösterilir, saklanmaz."""


class WebhookResponse(BaseModel):
    id: uuid.UUID
    url: str
    description: str | None
    events: list[str]
    active: bool
    created_at: datetime


class WebhookCreateRequest(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    events: list[str] = Field(min_length=1)
    description: str | None = Field(default=None, max_length=200)


class WebhookCreatedResponse(WebhookResponse):
    secret: str
    """İmza sırrı — yalnız oluşturma/yenileme yanıtında gösterilir."""


class WebhookUpdateRequest(BaseModel):
    url: str | None = Field(default=None, min_length=8, max_length=500)
    events: list[str] | None = None
    active: bool | None = None


class DeliveryResponse(BaseModel):
    id: uuid.UUID
    endpoint_id: uuid.UUID
    event: str
    event_id: uuid.UUID
    status: str
    attempts: int
    next_attempt_at: datetime | None
    last_status_code: int | None
    last_error: str | None
    delivered_at: datetime | None
    created_at: datetime
    payload: dict[str, Any]


class EventCatalogResponse(BaseModel):
    events: list[str]


def _key(k: ApiKey) -> dict[str, Any]:
    return {
        "id": k.id,
        "name": k.name,
        "prefix": k.prefix,
        "role": k.role,
        "created_at": k.created_at,
        "expires_at": k.expires_at,
        "last_used_at": k.last_used_at,
        "revoked_at": k.revoked_at,
    }


def _hook(e: WebhookEndpoint) -> dict[str, Any]:
    return {
        "id": e.id,
        "url": e.url,
        "description": e.description,
        "events": list(e.events or []),
        "active": e.active,
        "created_at": e.created_at,
    }


def _delivery(d: WebhookDelivery) -> DeliveryResponse:
    return DeliveryResponse(
        id=d.id,
        endpoint_id=d.endpoint_id,
        event=d.event,
        event_id=d.event_id,
        status=d.status,
        attempts=d.attempts,
        next_attempt_at=d.next_attempt_at,
        last_status_code=d.last_status_code,
        last_error=d.last_error,
        delivered_at=d.delivered_at,
        created_at=d.created_at,
        payload=d.payload,
    )


def _raise(exc: Exception) -> AppError:
    code = getattr(exc, "code", "invalid")
    message = getattr(exc, "message", str(exc))
    return NotFoundError(message) if code == "not_found" else ValidationFailedError(message)


# --- API anahtarları -----------------------------------------------------------------------


@router.get("/api-keys", response_model=list[ApiKeyResponse], tags=["integrations"])
async def list_keys(principal: ReaderDep, session: TenantSessionDep) -> list[ApiKeyResponse]:
    keys = await api_key_service.list_keys(session, tenant_id=principal.tenant_id)
    return [ApiKeyResponse(**_key(k)) for k in keys]


@router.post("/api-keys", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_key(
    body: ApiKeyCreateRequest, principal: OwnerDep, session: TenantSessionDep
) -> ApiKeyCreatedResponse:
    try:
        key, full = await api_key_service.create_key(
            session,
            tenant_id=principal.tenant_id,
            name=body.name,
            role=body.role,
            expires_in_days=body.expires_in_days,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
        )
    except api_key_service.ApiKeyError as exc:
        raise _raise(exc) from exc
    return ApiKeyCreatedResponse(**_key(key), key=full)


@router.delete("/api-keys/{key_id}", response_model=ApiKeyResponse)
async def revoke_key(
    key_id: uuid.UUID, principal: OwnerDep, session: TenantSessionDep
) -> ApiKeyResponse:
    try:
        key = await api_key_service.revoke_key(
            session,
            tenant_id=principal.tenant_id,
            key_id=key_id,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
        )
    except api_key_service.ApiKeyError as exc:
        raise _raise(exc) from exc
    return ApiKeyResponse(**_key(key))


# --- Webhook'lar ---------------------------------------------------------------------------


@router.get("/webhooks/events", response_model=EventCatalogResponse)
async def event_catalog(_principal: ReaderDep) -> EventCatalogResponse:
    return EventCatalogResponse(events=list(EVENTS))


@router.get("/webhooks", response_model=list[WebhookResponse])
async def list_webhooks(_principal: ReaderDep, session: TenantSessionDep) -> list[WebhookResponse]:
    from sqlalchemy import select

    rows = await session.scalars(select(WebhookEndpoint).order_by(WebhookEndpoint.created_at))
    return [WebhookResponse(**_hook(e)) for e in rows]


@router.post(
    "/webhooks", response_model=WebhookCreatedResponse, status_code=status.HTTP_201_CREATED
)
async def create_webhook(
    body: WebhookCreateRequest,
    principal: ManagerDep,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> WebhookCreatedResponse:
    try:
        endpoint, secret = await webhook_service.create_endpoint(
            session,
            tenant_id=principal.tenant_id,
            url=body.url,
            events=body.events,
            description=body.description,
            settings=settings,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
        )
    except webhook_service.WebhookError as exc:
        raise _raise(exc) from exc
    return WebhookCreatedResponse(**_hook(endpoint), secret=secret)


async def _endpoint(session: Any, endpoint_id: uuid.UUID) -> WebhookEndpoint:
    endpoint: WebhookEndpoint | None = await session.get(WebhookEndpoint, endpoint_id)  # RLS
    if endpoint is None:
        raise NotFoundError("Webhook bulunamadı.")
    return endpoint


@router.patch("/webhooks/{endpoint_id}", response_model=WebhookResponse)
async def update_webhook(
    endpoint_id: uuid.UUID,
    body: WebhookUpdateRequest,
    principal: ManagerDep,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> WebhookResponse:
    endpoint = await _endpoint(session, endpoint_id)
    try:
        await webhook_service.update_endpoint(
            session,
            endpoint,
            url=body.url,
            events=body.events,
            active=body.active,
            settings=settings,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
        )
    except webhook_service.WebhookError as exc:
        raise _raise(exc) from exc
    return WebhookResponse(**_hook(endpoint))


@router.post("/webhooks/{endpoint_id}/rotate-secret", response_model=WebhookCreatedResponse)
async def rotate_secret(
    endpoint_id: uuid.UUID, principal: ManagerDep, session: TenantSessionDep
) -> WebhookCreatedResponse:
    endpoint = await _endpoint(session, endpoint_id)
    secret = await webhook_service.rotate_secret(
        session, endpoint, actor_user_id=principal.user_id, actor_role=principal.role.value
    )
    return WebhookCreatedResponse(**_hook(endpoint), secret=secret)


@router.post(
    "/webhooks/{endpoint_id}/test",
    response_model=DeliveryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_test_ping(
    endpoint_id: uuid.UUID, _principal: ManagerDep, session: TenantSessionDep
) -> DeliveryResponse:
    """``ping`` olayını kuyruğa alır; teslim worker'ın bir sonraki turunda denenir."""
    delivery = await webhook_service.send_test(session, await _endpoint(session, endpoint_id))
    return _delivery(delivery)


@router.get("/webhooks/{endpoint_id}/deliveries", response_model=list[DeliveryResponse])
async def deliveries(
    endpoint_id: uuid.UUID,
    _principal: ReaderDep,
    session: TenantSessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[DeliveryResponse]:
    from sqlalchemy import select

    await _endpoint(session, endpoint_id)
    rows = await session.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.endpoint_id == endpoint_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )
    return [_delivery(d) for d in rows]


@router.post("/webhooks/deliveries/{delivery_id}/redeliver", response_model=DeliveryResponse)
async def redeliver(
    delivery_id: uuid.UUID, _principal: ManagerDep, session: TenantSessionDep
) -> DeliveryResponse:
    delivery = await session.get(WebhookDelivery, delivery_id)
    if delivery is None:
        raise NotFoundError("Teslim bulunamadı.")
    return _delivery(await webhook_service.redeliver(session, delivery))
