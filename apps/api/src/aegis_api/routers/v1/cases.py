"""/api/v1/cases — vaka yönetimi (E3.2, ADR-0014).

Yetkilendirme (kurallar ``cases/lifecycle.py``'de, burada yalnız ilk süzgeç):

- **Okuma** (liste, ayrıntı, tam geçmiş): tüm roller. Denetçi vaka geçmişinin tamamını görür
  ama hiçbir şeyi değiştiremez.
- **Açma, incelemeye alma, yükseltme (EDD), atama, EDD maddesi, yorum**: owner ·
  compliance_officer · analyst.
- **Onay, kapanış, yeniden açma, son tarih**: owner · compliance_officer.

Her mutasyon denetim izine bir olay yazar; ``GET /cases/{id}`` geçmişi oradan okur.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from aegis_api.dependencies import (
    Principal,
    PrincipalDep,
    SettingsDep,
    TenantSessionDep,
    require_role,
)
from aegis_api.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from aegis_core.cases import lifecycle
from aegis_core.cases import service as case_service
from aegis_core.cases.lifecycle import STATUS_LABELS, CaseSource, CaseStatus
from aegis_core.entities import service as entity_service
from aegis_core.models import ComplianceCase, Entity, Role, Screening
from aegis_core.monitoring.severity import SEVERITY_LABELS, Severity

router = APIRouter(prefix="/cases", tags=["cases"])

RequireCaseWrite = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.ANALYST))
]


class CaseSummary(BaseModel):
    new: int
    in_review: int
    escalated: int
    approved: int
    closed: int
    open: int
    overdue: int
    unassigned: int
    mine: int
    edd_open: int


class CaseResponse(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    entity_name: str | None
    title: str
    source: str
    source_alert_id: uuid.UUID | None
    source_screening_id: uuid.UUID | None
    severity: str
    severity_label: str
    status: str
    status_label: str
    edd: bool
    assignee_user_id: uuid.UUID | None
    due_at: datetime | None
    overdue: bool
    created_at: datetime
    first_review_at: datetime | None
    decided_at: datetime | None
    closed_at: datetime | None
    resolution: str | None


class CaseListResponse(BaseModel):
    items: list[CaseResponse]
    summary: CaseSummary


class ChecklistItem(BaseModel):
    key: str
    label: str
    done: bool
    note: str | None = None
    by: str | None = None
    at: str | None = None


class CommentResponse(BaseModel):
    id: uuid.UUID
    author_user_id: uuid.UUID | None
    author_role: str | None
    body: str
    created_at: datetime


class HistoryEvent(BaseModel):
    seq: int
    action: str
    actor_user_id: uuid.UUID | None
    actor_role: str | None
    occurred_at: datetime
    payload: dict[str, Any]


class CaseDetailResponse(CaseResponse):
    edd_template_version: str | None
    edd_checklist: list[ChecklistItem] | None
    edd_complete: bool
    allowed_actions: list[str]
    comments: list[CommentResponse]
    history: list[HistoryEvent]


class CaseCreateRequest(BaseModel):
    entity_id: uuid.UUID
    title: str = Field(min_length=3, max_length=200)
    severity: Severity = Severity.INFO
    edd: bool = False
    screening_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=4000)


class ActionRequest(BaseModel):
    action: str = Field(pattern="^(start_review|escalate|approve|close|reopen)$")
    reason: str | None = Field(default=None, max_length=4000)


class AssignRequest(BaseModel):
    user_id: uuid.UUID | None


class DueRequest(BaseModel):
    due_at: datetime


class EddItemRequest(BaseModel):
    done: bool
    note: str | None = Field(default=None, max_length=2000)


class CommentRequest(BaseModel):
    body: str = Field(min_length=2, max_length=4000)


def _raise(exc: case_service.CaseError) -> AppError:
    if exc.code == "forbidden":
        return ForbiddenError(exc.message)
    if exc.code == "not_found":
        return NotFoundError(exc.message)
    if exc.code in ("invalid_state", "checklist_open"):
        return ConflictError(exc.message)
    return ValidationFailedError(exc.message)


def _actor(principal: Principal) -> case_service.Actor:
    return case_service.Actor(principal.user_id, principal.role.value)


async def _case_response(session: Any, case: ComplianceCase) -> CaseResponse:
    entity = await entity_service.get_entity(session, case.entity_id)
    return CaseResponse(**_fields(case, entity))


def _fields(case: ComplianceCase, entity: Entity | None) -> dict[str, Any]:
    sev = Severity(case.severity)
    st = CaseStatus(case.status)
    return {
        "id": case.id,
        "entity_id": case.entity_id,
        "entity_name": entity.name if entity else None,
        "title": case.title,
        "source": case.source,
        "source_alert_id": case.source_alert_id,
        "source_screening_id": case.source_screening_id,
        "severity": sev.value,
        "severity_label": SEVERITY_LABELS[sev],
        "status": st.value,
        "status_label": STATUS_LABELS[st],
        "edd": case.edd,
        "assignee_user_id": case.assignee_user_id,
        "due_at": case.due_at,
        "overdue": lifecycle.is_overdue(case.status, case.due_at, datetime.now(UTC)),
        "created_at": case.created_at,
        "first_review_at": case.first_review_at,
        "decided_at": case.decided_at,
        "closed_at": case.closed_at,
        "resolution": case.resolution,
    }


async def _detail(session: Any, case: ComplianceCase, principal: Principal) -> CaseDetailResponse:
    entity = await entity_service.get_entity(session, case.entity_id)
    comments = await case_service.comments(session, case.id)
    events = await case_service.history(session, case.id)
    return CaseDetailResponse(
        **_fields(case, entity),
        edd_template_version=case.edd_template_version,
        edd_checklist=[ChecklistItem(**i) for i in case.edd_checklist]
        if case.edd_checklist
        else None,
        edd_complete=lifecycle.checklist_complete(case.edd_checklist),
        allowed_actions=lifecycle.allowed_actions(case.status, role=principal.role.value),
        comments=[
            CommentResponse(
                id=c.id,
                author_user_id=c.author_user_id,
                author_role=c.author_role,
                body=c.body,
                created_at=c.created_at,
            )
            for c in comments
        ],
        history=[
            HistoryEvent(
                seq=e.seq,
                action=e.action,
                actor_user_id=e.actor_user_id,
                actor_role=e.actor_role,
                occurred_at=e.occurred_at,
                payload=e.payload,
            )
            for e in events
        ],
    )


async def _load(session: Any, case_id: uuid.UUID) -> ComplianceCase:
    case: ComplianceCase | None = await session.get(ComplianceCase, case_id)  # RLS
    if case is None:
        raise NotFoundError("Vaka bulunamadı.")
    return case


async def _entity(session: Any, entity_id: uuid.UUID) -> Entity:
    entity = await entity_service.get_entity(session, entity_id)
    if entity is None:
        raise NotFoundError("Varlık bulunamadı.")
    return entity


STATUS_FILTERS = {
    "open": [s.value for s in lifecycle.OPEN_STATUSES],
    "decided": [CaseStatus.APPROVED.value, CaseStatus.CLOSED.value],
    "all": None,
    **{s.value: [s.value] for s in CaseStatus},
}


@router.get("", response_model=CaseListResponse)
async def list_cases(
    principal: PrincipalDep,
    session: TenantSessionDep,
    status_filter: Annotated[
        str,
        Query(
            alias="status",
            pattern="^(open|decided|all|new|in_review|escalated|approved|closed)$",
        ),
    ] = "open",
    mine: bool = False,
    overdue: bool = False,
    entity_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> CaseListResponse:
    """Vaka kuyruğu: son tarihe göre (en acil üstte) ve rol başına özet sayılar."""
    rows = await case_service.list_cases(
        session,
        statuses=STATUS_FILTERS[status_filter],
        assignee=principal.user_id if mine else None,
        entity_id=entity_id,
        overdue_only=overdue,
        limit=limit,
    )
    summary = await case_service.summary(session, user_id=principal.user_id)
    return CaseListResponse(
        items=[await _case_response(session, r) for r in rows],
        summary=CaseSummary(**summary),
    )


@router.post("", response_model=CaseDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    body: CaseCreateRequest, principal: RequireCaseWrite, session: TenantSessionDep
) -> CaseDetailResponse:
    """Elle vaka açar; ``screening_id`` verilirse kaynak o tarama incelemesidir."""
    entity = await _entity(session, body.entity_id)
    source = CaseSource.MANUAL
    if body.screening_id is not None:
        screening = await session.get(Screening, body.screening_id)
        if screening is None or screening.entity_id not in (None, entity.id):
            raise ValidationFailedError("Tarama bu varlığa ait değil.")
        source = CaseSource.SCREENING
    actor = _actor(principal)
    case = await case_service.open_case(
        session,
        tenant_id=principal.tenant_id,
        entity=entity,
        title=body.title.strip(),
        source=source,
        severity=body.severity.value,
        edd=body.edd,
        actor=actor,
        source_screening_id=body.screening_id,
    )
    if body.note and body.note.strip():
        await case_service.add_comment(session, case, body.note, actor=actor)
    return await _detail(session, case, principal)


@router.get("/{case_id}", response_model=CaseDetailResponse)
async def get_case(
    case_id: uuid.UUID, principal: PrincipalDep, session: TenantSessionDep
) -> CaseDetailResponse:
    """Vaka ayrıntısı: EDD listesi, yorumlar ve denetim izinden tam geçmiş."""
    return await _detail(session, await _load(session, case_id), principal)


@router.post("/{case_id}/actions", response_model=CaseDetailResponse)
async def case_action(
    case_id: uuid.UUID,
    body: ActionRequest,
    principal: PrincipalDep,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> CaseDetailResponse:
    """Durum geçişi. Rol, durum, gerekçe ve EDD koşulları ``lifecycle``'da denetlenir."""
    case = await _load(session, case_id)
    entity = await _entity(session, case.entity_id)
    try:
        await case_service.apply_action(
            session,
            case,
            body.action,
            reason=body.reason,
            actor=_actor(principal),
            entity=entity,
            high_risk_countries=settings.high_risk_countries,
            retention_years=settings.document_retention_years,
        )
    except case_service.CaseError as exc:
        raise _raise(exc) from exc
    return await _detail(session, case, principal)


@router.put("/{case_id}/assignee", response_model=CaseDetailResponse)
async def assign_case(
    case_id: uuid.UUID, body: AssignRequest, principal: RequireCaseWrite, session: TenantSessionDep
) -> CaseDetailResponse:
    case = await _load(session, case_id)
    try:
        await case_service.assign(session, case, body.user_id, actor=_actor(principal))
    except case_service.CaseError as exc:
        raise _raise(exc) from exc
    return await _detail(session, case, principal)


@router.put("/{case_id}/due", response_model=CaseDetailResponse)
async def set_due(
    case_id: uuid.UUID, body: DueRequest, principal: RequireCaseWrite, session: TenantSessionDep
) -> CaseDetailResponse:
    case = await _load(session, case_id)
    due = body.due_at if body.due_at.tzinfo else body.due_at.replace(tzinfo=UTC)
    try:
        await case_service.set_due(session, case, due, actor=_actor(principal))
    except case_service.CaseError as exc:
        raise _raise(exc) from exc
    return await _detail(session, case, principal)


@router.put("/{case_id}/edd/{key}", response_model=CaseDetailResponse)
async def set_edd_item(
    case_id: uuid.UUID,
    key: str,
    body: EddItemRequest,
    principal: RequireCaseWrite,
    session: TenantSessionDep,
) -> CaseDetailResponse:
    case = await _load(session, case_id)
    try:
        await case_service.set_edd_item(
            session, case, key, done=body.done, note=body.note, actor=_actor(principal)
        )
    except case_service.CaseError as exc:
        raise _raise(exc) from exc
    return await _detail(session, case, principal)


@router.post(
    "/{case_id}/comments", response_model=CaseDetailResponse, status_code=status.HTTP_201_CREATED
)
async def add_comment(
    case_id: uuid.UUID, body: CommentRequest, principal: RequireCaseWrite, session: TenantSessionDep
) -> CaseDetailResponse:
    case = await _load(session, case_id)
    try:
        await case_service.add_comment(session, case, body.body, actor=_actor(principal))
    except case_service.CaseError as exc:
        raise _raise(exc) from exc
    return await _detail(session, case, principal)
