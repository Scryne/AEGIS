"""Vaka servisi (E3.2): açma, geçiş, atama, son tarih, EDD maddesi, yorum, geçmiş.

Kurallar ``cases/lifecycle.py``'dedir; bu modül yalnız uygular ve iz bırakır. Her mutasyon
denetim izine tam bir olay yazar (Invariant 2); vaka geçmişi de bu olaylardan okunur.

Karar geçişlerinde (onay, kapanış) varlığın risk puanı yeniden kayda geçirilir: vaka içinde
eşleşme onaylanmışsa dosya yeni puanla kapanır ("re-scored dossier", Faz 3 çıkış ölçütü).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.cases import lifecycle
from aegis_core.cases.lifecycle import CaseAction, CaseSource, CaseStatus
from aegis_core.models import (
    AuditAction,
    AuditEvent,
    CaseComment,
    ComplianceCase,
    Entity,
    Membership,
    MonitoringAlert,
)
from aegis_core.reports import score_service
from aegis_core.services import audit as audit_service

OBJECT_TYPE = "compliance_case"


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID | None
    role: str


class CaseError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> datetime:
    return datetime.now(UTC)


async def _audit(
    session: AsyncSession,
    case: ComplianceCase,
    action: AuditAction,
    actor: Actor,
    payload: dict[str, Any],
) -> None:
    await audit_service.record_event(
        session,
        tenant_id=case.tenant_id,
        actor_user_id=actor.user_id,
        actor_role=actor.role,
        action=action,
        object_type=OBJECT_TYPE,
        object_id=str(case.id),
        payload={"entity_id": str(case.entity_id), **payload},
    )


async def open_case(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity: Entity,
    title: str,
    source: CaseSource,
    severity: str,
    edd: bool,
    actor: Actor,
    source_alert_id: uuid.UUID | None = None,
    source_screening_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> ComplianceCase:
    opened = now or _now()
    case = ComplianceCase(
        tenant_id=tenant_id,
        entity_id=entity.id,
        title=title[:200],
        source=source.value,
        source_alert_id=source_alert_id,
        source_screening_id=source_screening_id,
        severity=severity,
        status=CaseStatus.NEW.value,
        edd=edd,
        edd_template_version=lifecycle.EDD_TEMPLATE_VERSION if edd else None,
        edd_checklist=lifecycle.new_checklist() if edd else None,
        opened_by_user_id=actor.user_id,
        due_at=lifecycle.due_at_for(severity, opened),
    )
    session.add(case)
    await session.flush()
    await _audit(
        session,
        case,
        AuditAction.CASE_OPEN,
        actor,
        {
            "source": source.value,
            "severity": severity,
            "edd": edd,
            "source_alert_id": str(source_alert_id) if source_alert_id else None,
            "source_screening_id": str(source_screening_id) if source_screening_id else None,
        },
    )
    return case


async def case_for_alert(session: AsyncSession, alert_id: uuid.UUID) -> ComplianceCase | None:
    row: ComplianceCase | None = await session.scalar(
        select(ComplianceCase).where(ComplianceCase.source_alert_id == alert_id)
    )
    return row


async def open_from_alert(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    alert: MonitoringAlert,
    entity: Entity,
    severity: str,
) -> ComplianceCase:
    """Alarmdan vaka açar; aynı alarm için ikinci kez çağrılırsa mevcut vakayı döner."""
    existing = await case_for_alert(session, alert.id)
    if existing is not None:
        return existing
    edd = severity == "critical"
    title = ("Yaptırım alarmı" if edd else "İzleme alarmı") + f": {entity.name}"
    return await open_case(
        session,
        tenant_id=tenant_id,
        entity=entity,
        title=title,
        source=CaseSource.MONITORING_ALERT,
        severity=severity,
        edd=edd,
        actor=Actor(None, "monitoring"),
        source_alert_id=alert.id,
        source_screening_id=alert.screening_id,
    )


async def apply_action(
    session: AsyncSession,
    case: ComplianceCase,
    action: str,
    *,
    reason: str | None,
    actor: Actor,
    entity: Entity,
    high_risk_countries: list[str],
    retention_years: int,
) -> ComplianceCase:
    before = case.status
    try:
        target = lifecycle.transition(
            case.status,
            action,
            role=actor.role,
            edd=case.edd,
            checklist_complete=lifecycle.checklist_complete(case.edd_checklist),
            reason=reason,
        )
    except lifecycle.TransitionError as exc:
        raise CaseError(exc.code, exc.message) from exc

    now = _now()
    act = CaseAction(action)
    case.status = target.value
    if act == CaseAction.START_REVIEW and case.first_review_at is None:
        case.first_review_at = now
    if act == CaseAction.ESCALATE:
        case.escalated_at = now
        if not case.edd:
            case.edd = True
            case.edd_template_version = lifecycle.EDD_TEMPLATE_VERSION
            case.edd_checklist = lifecycle.new_checklist()
        if case.first_review_at is None:
            case.first_review_at = now
    if act in (CaseAction.APPROVE, CaseAction.CLOSE):
        case.resolution = (reason or "").strip()
        if act == CaseAction.APPROVE or case.decided_at is None:
            case.decided_at = now
        if act == CaseAction.CLOSE:
            case.closed_at = now
    if act == CaseAction.REOPEN:
        case.closed_at = None
    await session.flush()

    snapshot_id: str | None = None
    if act in (CaseAction.APPROVE, CaseAction.CLOSE):
        snap, _ = await score_service.snapshot(
            session,
            tenant_id=case.tenant_id,
            entity=entity,
            reason="case_decision",
            actor_user_id=actor.user_id,
            actor_role=actor.role,
            high_risk_countries=high_risk_countries,
            retention_years=retention_years,
        )
        snapshot_id = str(snap.id)

    await _audit(
        session,
        case,
        AuditAction.CASE_TRANSITION,
        actor,
        {
            "action": act.value,
            "from": before,
            "to": target.value,
            "reason": (reason or "").strip() or None,
            "risk_score_snapshot_id": snapshot_id,
        },
    )
    return case


async def _is_member(session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(func.count())
        .select_from(Membership)
        .where(Membership.organization_id == tenant_id, Membership.user_id == user_id)
    )
    return bool(found)


def _require_open(case: ComplianceCase) -> None:
    if CaseStatus(case.status) not in lifecycle.OPEN_STATUSES:
        raise CaseError("invalid_state", "Kapanmış ya da karara bağlanmış vaka değiştirilemez.")


def _require_writer(actor: Actor) -> None:
    if actor.role not in lifecycle.WRITER_ROLES:
        raise CaseError("forbidden", "Bu işlem için yetkiniz yok.")


async def assign(
    session: AsyncSession, case: ComplianceCase, assignee: uuid.UUID | None, *, actor: Actor
) -> ComplianceCase:
    _require_writer(actor)
    _require_open(case)
    if assignee is not None and not await _is_member(session, case.tenant_id, assignee):
        raise CaseError("invalid_assignee", "Atanan kişi bu kurumun üyesi değil.")
    if case.assignee_user_id == assignee:
        return case
    previous = case.assignee_user_id
    case.assignee_user_id = assignee
    await session.flush()
    await _audit(
        session,
        case,
        AuditAction.CASE_ASSIGN,
        actor,
        {"from": str(previous) if previous else None, "to": str(assignee) if assignee else None},
    )
    return case


async def set_due(
    session: AsyncSession, case: ComplianceCase, due_at: datetime, *, actor: Actor
) -> ComplianceCase:
    if actor.role not in lifecycle.DECIDER_ROLES:
        raise CaseError("forbidden", "Son tarihi yalnız uyum görevlisi değiştirebilir.")
    _require_open(case)
    previous = case.due_at
    case.due_at = due_at
    await session.flush()
    await _audit(
        session,
        case,
        AuditAction.CASE_DUE,
        actor,
        {"from": previous.isoformat() if previous else None, "to": due_at.isoformat()},
    )
    return case


async def set_edd_item(
    session: AsyncSession,
    case: ComplianceCase,
    key: str,
    *,
    done: bool,
    note: str | None,
    actor: Actor,
) -> ComplianceCase:
    _require_writer(actor)
    _require_open(case)
    if not case.edd or not case.edd_checklist:
        raise CaseError("invalid_state", "Bu vakada EDD kontrol listesi yok.")
    items = [dict(i) for i in case.edd_checklist]
    match = next((i for i in items if i["key"] == key), None)
    if match is None:
        raise CaseError("not_found", "Kontrol listesi maddesi bulunamadı.")
    clean_note = (note or "").strip() or None
    if done and clean_note is None:
        raise CaseError("reason_required", "Tamamlanan madde için ne yapıldığını yazın.")
    match["done"] = done
    match["note"] = clean_note
    match["by"] = str(actor.user_id) if actor.user_id else None
    match["at"] = _now().isoformat()
    case.edd_checklist = items  # JSONB: yeni liste ata ki değişiklik algılansın
    await session.flush()
    await _audit(
        session,
        case,
        AuditAction.CASE_EDD_ITEM,
        actor,
        {"key": key, "done": done, "note": clean_note},
    )
    return case


async def add_comment(
    session: AsyncSession, case: ComplianceCase, body: str, *, actor: Actor
) -> CaseComment:
    _require_writer(actor)
    comment = CaseComment(
        tenant_id=case.tenant_id,
        case_id=case.id,
        author_user_id=actor.user_id,
        author_role=actor.role,
        body=body.strip(),
    )
    session.add(comment)
    await session.flush()
    await _audit(
        session,
        case,
        AuditAction.CASE_COMMENT,
        actor,
        {"comment_id": str(comment.id), "length": len(comment.body)},
    )
    return comment


async def list_cases(
    session: AsyncSession,
    *,
    statuses: list[str] | None,
    assignee: uuid.UUID | None,
    entity_id: uuid.UUID | None,
    overdue_only: bool,
    limit: int,
    now: datetime | None = None,
) -> list[ComplianceCase]:
    query = select(ComplianceCase)
    if statuses:
        query = query.where(ComplianceCase.status.in_(statuses))
    if assignee is not None:
        query = query.where(ComplianceCase.assignee_user_id == assignee)
    if entity_id is not None:
        query = query.where(ComplianceCase.entity_id == entity_id)
    if overdue_only:
        query = query.where(
            ComplianceCase.status.in_([s.value for s in lifecycle.OPEN_STATUSES]),
            ComplianceCase.due_at < (now or _now()),
        )
    query = query.order_by(ComplianceCase.due_at.asc().nulls_last(), ComplianceCase.created_at)
    return list(await session.scalars(query.limit(limit)))


async def summary(
    session: AsyncSession, *, user_id: uuid.UUID | None, now: datetime | None = None
) -> dict[str, int]:
    at = now or _now()
    open_values = [s.value for s in lifecycle.OPEN_STATUSES]
    rows = await session.execute(
        select(ComplianceCase.status, func.count()).group_by(ComplianceCase.status)
    )
    by_status = {s.value: 0 for s in CaseStatus}
    for st, n in rows:
        by_status[st] = int(n)

    async def _count(*conds: Any) -> int:
        return int(
            await session.scalar(select(func.count()).select_from(ComplianceCase).where(*conds))
            or 0
        )

    open_cond = ComplianceCase.status.in_(open_values)
    return {
        **by_status,
        "open": sum(by_status[s] for s in open_values),
        "overdue": await _count(open_cond, ComplianceCase.due_at < at),
        "unassigned": await _count(open_cond, ComplianceCase.assignee_user_id.is_(None)),
        "mine": await _count(open_cond, ComplianceCase.assignee_user_id == user_id)
        if user_id
        else 0,
        "edd_open": await _count(open_cond, ComplianceCase.edd.is_(True)),
    }


async def comments(session: AsyncSession, case_id: uuid.UUID) -> list[CaseComment]:
    rows = await session.scalars(
        select(CaseComment)
        .where(CaseComment.case_id == case_id)
        .order_by(CaseComment.created_at, CaseComment.id)
    )
    return list(rows)


async def history(session: AsyncSession, case_id: uuid.UUID) -> list[AuditEvent]:
    """Vakanın tam geçmişi, denetim izinden (eskiden yeniye, ``seq`` sırasıyla)."""
    events = await audit_service.list_events(
        session, object_type=OBJECT_TYPE, object_id=str(case_id), limit=500
    )
    return list(reversed(events))
