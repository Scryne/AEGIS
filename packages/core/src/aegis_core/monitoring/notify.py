"""İzleme bildirimleri (E3.1): kiracı başına yönlendirme ve özet tercihi.

Tercih ``tenant_setting`` içinde durur. Derece başına iki kip: ``immediate`` gece koşusunun hemen
ardından, ``digest`` günlük özetle. ``off`` yoktur: alarm ekranda her zaman görünür, kipler yalnız
e-postayı yönetir.

E-posta **kişisel veri taşımaz** (ADR-0016'daki webhook ilkesiyle aynı): yalnız sayı, derece ve
panele bağlantı. Bir alarm ancak sunucu iletiyi kabul ettikten sonra "bildirildi" sayılır; SMTP
düşerse sonraki turda yeniden denenir.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.config import Settings
from aegis_core.logging import get_logger
from aegis_core.models import (
    AlertStatus,
    Membership,
    MonitoringAlert,
    MonitoringRun,
    Role,
    TenantSetting,
    User,
)
from aegis_core.monitoring.severity import SEVERITY_LABELS, Severity
from aegis_core.notifications.email import (
    EmailNotConfiguredError,
    EmailSender,
    EmailSendError,
    OutgoingEmail,
)

logger = get_logger("aegis.monitoring.notify")

SETTING_KEY = "monitoring_notifications"
Mode = Literal["immediate", "digest"]
ROUTABLE_ROLES = (Role.OWNER, Role.COMPLIANCE_OFFICER, Role.ANALYST, Role.AUDITOR)


@dataclass(frozen=True)
class Preferences:
    critical: Mode = "immediate"
    high: Mode = "immediate"
    info: Mode = "digest"
    roles: tuple[str, ...] = (Role.OWNER.value, Role.COMPLIANCE_OFFICER.value)

    def mode_for(self, severity: str | None) -> Mode:
        if severity == Severity.CRITICAL.value:
            return self.critical
        if severity == Severity.HIGH.value:
            return self.high
        return self.info

    def as_dict(self) -> dict[str, Any]:
        return {
            "critical": self.critical,
            "high": self.high,
            "info": self.info,
            "roles": list(self.roles),
        }


def _parse(value: dict[str, Any] | None) -> Preferences:
    if not value:
        return Preferences()
    default = Preferences()
    valid_roles = {r.value for r in ROUTABLE_ROLES}
    roles = tuple(r for r in value.get("roles", default.roles) if r in valid_roles)

    def mode(key: str, fallback: Mode) -> Mode:
        raw = value.get(key)
        return raw if raw in ("immediate", "digest") else fallback

    return Preferences(
        critical=mode("critical", default.critical),
        high=mode("high", default.high),
        info=mode("info", default.info),
        roles=roles or default.roles,
    )


async def load_preferences(session: AsyncSession, tenant_id: uuid.UUID) -> Preferences:
    row = await session.scalar(
        select(TenantSetting).where(
            TenantSetting.tenant_id == tenant_id, TenantSetting.key == SETTING_KEY
        )
    )
    return _parse(row.value if row else None)


async def save_preferences(
    session: AsyncSession, tenant_id: uuid.UUID, preferences: Preferences
) -> None:
    row = await session.scalar(
        select(TenantSetting).where(
            TenantSetting.tenant_id == tenant_id, TenantSetting.key == SETTING_KEY
        )
    )
    if row is None:
        session.add(
            TenantSetting(tenant_id=tenant_id, key=SETTING_KEY, value=preferences.as_dict())
        )
    else:
        row.value = preferences.as_dict()
    await session.flush()


async def _recipients(
    session: AsyncSession, tenant_id: uuid.UUID, preferences: Preferences
) -> tuple[str, ...]:
    rows = await session.scalars(
        select(User.email)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.organization_id == tenant_id,
            Membership.role.in_([Role(r) for r in preferences.roles]),
            User.is_active.is_(True),
        )
        .order_by(User.email)
    )
    return tuple(rows)


def _body(
    *,
    alerts: list[MonitoringAlert],
    unreachable: int,
    settings: Settings,
) -> tuple[str, str]:
    counts = {s.value: 0 for s in Severity}
    for alert in alerts:
        counts[alert.severity or Severity.INFO.value] = (
            counts.get(alert.severity or Severity.INFO.value, 0) + 1
        )
    lines: list[str] = []
    for severity in (Severity.CRITICAL, Severity.HIGH, Severity.INFO):
        if counts.get(severity.value):
            lines.append(f"- {SEVERITY_LABELS[severity]}: {counts[severity.value]} alarm")
    if unreachable:
        lines.append(
            f"- Taranamayan varlık: {unreachable}. Bu varlıklar için sonuç YOK, temiz değil."
        )
    critical = counts.get(Severity.CRITICAL.value, 0)
    subject = (
        f"AEGIS: {critical} kritik izleme alarmı"
        if critical
        else f"AEGIS: {len(alerts)} izleme alarmı"
        if alerts
        else f"AEGIS: {unreachable} varlık taranamadı"
    )
    link = f"{settings.web_base_url.rstrip('/')}/monitoring"
    body = "\n".join(
        [
            "İzleme koşusunda inceleme gerektiren sonuçlar var:",
            "",
            *lines,
            "",
            f"Ayrıntı için panele girin: {link}",
            "",
            "Bu e-posta kişisel veri içermez. Kararlar denetim izine panelden yazılır.",
        ]
    )
    return subject, body


async def deliver(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    settings: Settings,
    sender: EmailSender,
    mode: Mode,
    run: MonitoringRun | None = None,
) -> dict[str, Any]:
    """Bekleyen alarmları bildirir.

    ``mode="immediate"``: yalnız "hemen" tercihli dereceler. ``mode="digest"``: kalan her şey,
    "hemen" olup önceki turda SMTP yüzünden gidememiş alarmlar dahil.
    """
    preferences = await load_preferences(session, tenant_id)
    rows = await session.scalars(
        select(MonitoringAlert).where(
            MonitoringAlert.status == AlertStatus.OPEN.value,
            MonitoringAlert.notified_at.is_(None),
        )
    )
    alerts = [
        a for a in rows if mode == "digest" or preferences.mode_for(a.severity) == "immediate"
    ]
    unreachable = run.failed if run is not None else 0
    if not alerts and not unreachable:
        return {"status": "nothing", "alerts": 0}
    if not sender.configured:
        logger.warning("izleme_bildirimi_smtp_yok", tenant_id=str(tenant_id), alerts=len(alerts))
        return {"status": "not_configured", "alerts": len(alerts)}
    recipients = await _recipients(session, tenant_id, preferences)
    if not recipients:
        logger.warning("izleme_bildirimi_alici_yok", tenant_id=str(tenant_id))
        return {"status": "no_recipients", "alerts": len(alerts)}
    subject, body = _body(alerts=alerts, unreachable=unreachable, settings=settings)
    try:
        await sender.send(OutgoingEmail(to=recipients, subject=subject, body=body))
    except (EmailNotConfiguredError, EmailSendError) as exc:
        logger.error("izleme_bildirimi_gonderilemedi", tenant_id=str(tenant_id), error=str(exc))
        return {"status": "failed", "alerts": len(alerts)}
    now = datetime.now(UTC)
    for alert in alerts:
        alert.notified_at = now
    await session.flush()
    return {"status": "sent", "alerts": len(alerts)}
