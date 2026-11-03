"""/api/v1 — izleme-lite (E2.4): izleme bayrağı, alarm listesi, onay, elle koşu.

Yetkilendirme:

- **Okuma** (alarm listesi): tüm roller.
- **İzlemeye alma / çıkarma**, **alarm onayı**: owner · compliance_officer · analyst.
- **Elle koşu** (``POST /monitoring/run``): owner · compliance_officer — gece görevini beklemeden
  aynı koşuyu başlatır (canlı yente çağrıları yapar).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from aegis_api.dependencies import (
    Principal,
    PrincipalDep,
    SettingsDep,
    TenantSessionDep,
    YenteClientDep,
    require_role,
)
from aegis_api.errors import NotFoundError, PlanLimitError
from aegis_core.billing import service as billing_service
from aegis_core.cases import service as case_service
from aegis_core.entities import service as entity_service
from aegis_core.models import AuditAction, MonitoringAlert, Role
from aegis_core.monitoring import notify as monitoring_notify
from aegis_core.monitoring import service as monitoring_service
from aegis_core.monitoring.severity import SEVERITY_LABELS
from aegis_core.notifications.email import default_sender
from aegis_core.services import audit as audit_service

router = APIRouter(tags=["monitoring"])

RequireWatchWrite = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.ANALYST))
]
RequireRunNow = Annotated[Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER))]


class MonitoringToggleRequest(BaseModel):
    monitored: bool


class MonitoringToggleResponse(BaseModel):
    entity_id: uuid.UUID
    monitored: bool


class AlertResponse(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    entity_name: str | None
    screening_id: uuid.UUID
    previous_screening_id: uuid.UUID | None
    items: list[dict[str, Any]]
    status: str
    severity: str
    severity_label: str
    reassessment: dict[str, Any] | None
    """Alarm anında kayda geçen risk puanı: önceki ve sonraki (E3.1)."""

    case_id: uuid.UUID | None
    """Bu alarmın açtığı vaka (yalnız ``critical``/``high``)."""

    created_at: datetime
    acknowledged_at: datetime | None
    acknowledge_note: str | None


class AlertListResponse(BaseModel):
    items: list[AlertResponse]
    open_count: int


class AcknowledgeRequest(BaseModel):
    note: str = Field(min_length=3, max_length=2000)


class RunResponse(BaseModel):
    checked: int
    alerts: int
    failed: int


async def _alert_response(session: Any, alert: MonitoringAlert) -> AlertResponse:
    entity = await entity_service.get_entity(session, alert.entity_id)
    severity = monitoring_service.severity_of(alert)
    case = await case_service.case_for_alert(session, alert.id)
    return AlertResponse(
        id=alert.id,
        entity_id=alert.entity_id,
        entity_name=entity.name if entity else None,
        screening_id=alert.screening_id,
        previous_screening_id=alert.previous_screening_id,
        items=list(alert.diff.get("items", [])),
        status=alert.status,
        severity=severity.value,
        severity_label=SEVERITY_LABELS[severity],
        reassessment=alert.reassessment,
        case_id=case.id if case else None,
        created_at=alert.created_at,
        acknowledged_at=alert.acknowledged_at,
        acknowledge_note=alert.acknowledge_note,
    )


@router.put("/entities/{entity_id}/monitoring", response_model=MonitoringToggleResponse)
async def toggle(
    entity_id: uuid.UUID,
    body: MonitoringToggleRequest,
    principal: RequireWatchWrite,
    session: TenantSessionDep,
) -> MonitoringToggleResponse:
    """Varlığı gece izlemeye alır ya da çıkarır (denetim izine yazılır)."""
    entity = await entity_service.get_entity(session, entity_id)
    if entity is None:
        raise NotFoundError("Varlık bulunamadı.")
    if body.monitored and not entity.monitored:
        try:
            await billing_service.require_monitoring_slot(session, principal.tenant_id)
        except billing_service.MonitoringLimitError as exc:
            raise PlanLimitError(str(exc)) from exc
    await monitoring_service.set_monitored(
        session,
        entity,
        body.monitored,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
    )
    return MonitoringToggleResponse(entity_id=entity.id, monitored=entity.monitored)


@router.get("/monitoring/alerts", response_model=AlertListResponse)
async def alerts(
    _principal: PrincipalDep,
    session: TenantSessionDep,
    status_filter: Annotated[
        str | None, Query(alias="status", pattern="^(open|acknowledged)$")
    ] = None,
    entity_id: uuid.UUID | None = None,
    severity: Annotated[str | None, Query(pattern="^(critical|high|info)$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AlertListResponse:
    """İzleme alarmları (en yeni üstte); derece ve vaka bağlantısıyla."""
    rows = await monitoring_service.list_alerts(
        session, status=status_filter, entity_id=entity_id, limit=limit, severity=severity
    )
    return AlertListResponse(
        items=[await _alert_response(session, r) for r in rows],
        open_count=await monitoring_service.count_open(session),
    )


@router.post("/monitoring/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge(
    alert_id: uuid.UUID,
    body: AcknowledgeRequest,
    principal: RequireWatchWrite,
    session: TenantSessionDep,
) -> AlertResponse:
    """Alarmı gerekçeyle "görüldü" yapar; alarm silinmez."""
    alert = await session.get(MonitoringAlert, alert_id)  # RLS: yalnız kendi kiracısının satırı
    if alert is None:
        raise NotFoundError("Alarm bulunamadı.")
    await monitoring_service.acknowledge(
        session,
        alert,
        tenant_id=principal.tenant_id,
        note=body.note,
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
    )
    return await _alert_response(session, alert)


class RunRow(BaseModel):
    id: uuid.UUID
    trigger: str
    started_at: datetime
    duration_ms: int
    checked: int
    skipped: int
    alerts: int
    failed: int
    retried: int
    failures: list[dict[str, str]]


class RunListResponse(BaseModel):
    items: list[RunRow]


@router.get("/monitoring/runs", response_model=RunListResponse)
async def runs(
    _principal: PrincipalDep,
    session: TenantSessionDep,
    limit: Annotated[int, Query(ge=1, le=30)] = 7,
) -> RunListResponse:
    """Son koşular. Taranamayan varlıklar burada görünür: sonuç YOK, temiz değil."""
    rows = await monitoring_service.latest_runs(session, limit=limit)
    return RunListResponse(items=[RunRow.model_validate(r, from_attributes=True) for r in rows])


class NotificationPreferences(BaseModel):
    critical: Literal["immediate", "digest"]
    high: Literal["immediate", "digest"]
    info: Literal["immediate", "digest"]
    roles: list[Literal["owner", "compliance_officer", "analyst", "auditor"]] = Field(min_length=1)


class NotificationPreferencesResponse(NotificationPreferences):
    email_configured: bool


@router.get("/monitoring/notifications", response_model=NotificationPreferencesResponse)
async def get_notifications(
    principal: PrincipalDep, session: TenantSessionDep, settings: SettingsDep
) -> NotificationPreferencesResponse:
    prefs = await monitoring_notify.load_preferences(session, principal.tenant_id)
    return NotificationPreferencesResponse(
        **prefs.as_dict(), email_configured=default_sender(settings).configured
    )


@router.put("/monitoring/notifications", response_model=NotificationPreferencesResponse)
async def put_notifications(
    body: NotificationPreferences,
    principal: RequireRunNow,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> NotificationPreferencesResponse:
    """Yönlendirme tercihini kaydeder; değişiklik denetim izine yazılır."""
    prefs = monitoring_notify.Preferences(
        critical=body.critical, high=body.high, info=body.info, roles=tuple(body.roles)
    )
    await monitoring_notify.save_preferences(session, principal.tenant_id, prefs)
    await audit_service.record_event(
        session,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
        action=AuditAction.TENANT_SETTING_UPDATE,
        object_type="tenant_setting",
        object_id=monitoring_notify.SETTING_KEY,
        payload=prefs.as_dict(),
    )
    return NotificationPreferencesResponse(
        **prefs.as_dict(), email_configured=default_sender(settings).configured
    )


@router.post("/monitoring/run", response_model=RunResponse, status_code=status.HTTP_200_OK)
async def run_now(
    principal: RequireRunNow,
    session: TenantSessionDep,
    settings: SettingsDep,
    yente: YenteClientDep,
) -> RunResponse:
    """İzlenen tüm varlıkları şimdi yeniden tarar (gece görevinin aynısı)."""
    result = await monitoring_service.run_for_tenant(
        session, yente, tenant_id=principal.tenant_id, settings=settings
    )
    return RunResponse(**result)
