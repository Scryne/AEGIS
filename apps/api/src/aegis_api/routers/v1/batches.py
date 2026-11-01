"""/api/v1/batches — toplu tarama (E3.3, ADR-0015).

Yetkilendirme:

- **Okuma** (liste, ayrıntı, satırlar, CSV özet): tüm roller.
- **Önizleme, oluşturma, başlatma, belirsiz satıra karar, toplu işlem, iptal, yeniden deneme**:
  owner · compliance_officer · analyst (tarama çalıştırma yetkisiyle aynı küme).
- **Şimdi işle** (``POST /batches/{id}/process``): owner · compliance_officer — worker'ı
  beklemeden bir parçayı bu istekte işler (izlemedeki "şimdi koş" ile aynı gerekçe).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from aegis_api.dependencies import (
    Principal,
    PrincipalDep,
    SettingsDep,
    TenantSessionDep,
    YenteClientDep,
    require_role,
)
from aegis_api.errors import (
    AppError,
    ConflictError,
    NotFoundError,
    PlanLimitError,
    QuotaExceededAppError,
    ValidationFailedError,
)
from aegis_api.queue import dispatch
from aegis_core.batch import csv_import
from aegis_core.batch import service as batch_service
from aegis_core.logging import get_logger
from aegis_core.models import Role, ScreeningBatch, ScreeningBatchRow
from aegis_core.queueing import TASK_BATCH_PROCESS

router = APIRouter(prefix="/batches", tags=["batches"])
logger = get_logger("aegis.api.batches")

RequireBatchWrite = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.ANALYST))
]
RequireRunNow = Annotated[Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER))]


class BatchResponse(BaseModel):
    id: uuid.UUID
    file_name: str
    status: str
    total_rows: int
    counts: dict[str, int]
    risk: dict[str, int]
    column_map: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class BatchListResponse(BaseModel):
    items: list[BatchResponse]


class RowResponse(BaseModel):
    id: uuid.UUID
    row_no: int
    data: dict[str, Any]
    errors: list[str]
    warnings: list[str]
    status: str
    duplicate_of: int | None
    resolution: str | None
    resolution_candidates: list[dict[str, Any]] | None
    entity_id: uuid.UUID | None
    screening_id: uuid.UUID | None
    candidate_count: int | None
    flagged_count: int | None
    sanction_hits: int | None
    pep_hits: int | None
    top_score: float | None
    attempts: int
    error: str | None


class RowListResponse(BaseModel):
    items: list[RowResponse]
    total: int


class ProcessResponse(BaseModel):
    processed: int
    done: int
    needs_review: int
    failed: int
    remaining: int


class ResolveRequest(BaseModel):
    entity_id: uuid.UUID | None = None
    """Mevcut varlık; boşsa satır için yeni varlık açılır."""


class BulkRequest(BaseModel):
    action: str = Field(pattern="^(monitor|open_case)$")
    row_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)


class BulkResponse(BaseModel):
    applied: int
    skipped: int


def _raise(exc: batch_service.BatchError) -> AppError:
    if exc.code == "not_found":
        return NotFoundError(exc.message)
    if exc.code == "invalid_state":
        return ConflictError(exc.message)
    if exc.code == "quota":
        return QuotaExceededAppError(exc.message)
    if exc.code == "plan_limit":
        return PlanLimitError(exc.message)
    return ValidationFailedError(exc.message)


def _actor(principal: Principal) -> batch_service.Actor:
    return batch_service.Actor(principal.user_id, principal.role.value)


async def _response(session: Any, batch: ScreeningBatch) -> BatchResponse:
    return BatchResponse(
        id=batch.id,
        file_name=batch.file_name,
        status=batch.status,
        total_rows=batch.total_rows,
        counts=await batch_service.row_counts(session, batch.id),
        risk=await batch_service.risk_counts(session, batch.id),
        column_map=batch.column_map,
        created_at=batch.created_at,
        started_at=batch.started_at,
        finished_at=batch.finished_at,
    )


def _row(r: ScreeningBatchRow) -> RowResponse:
    return RowResponse(
        id=r.id,
        row_no=r.row_no,
        data=r.data,
        errors=list(r.errors or []),
        warnings=list(r.warnings or []),
        status=r.status,
        duplicate_of=r.duplicate_of,
        resolution=r.resolution,
        resolution_candidates=r.resolution_candidates,
        entity_id=r.entity_id,
        screening_id=r.screening_id,
        candidate_count=r.candidate_count,
        flagged_count=r.flagged_count,
        sanction_hits=r.sanction_hits,
        pep_hits=r.pep_hits,
        top_score=r.top_score,
        attempts=r.attempts,
        error=r.error,
    )


async def _load(session: Any, batch_id: uuid.UUID) -> ScreeningBatch:
    batch: ScreeningBatch | None = await session.get(ScreeningBatch, batch_id)  # RLS
    if batch is None:
        raise NotFoundError("Toplu iş bulunamadı.")
    return batch


async def _read(file: UploadFile) -> bytes:
    data = await file.read(csv_import.MAX_BYTES + 1)
    if len(data) > csv_import.MAX_BYTES:
        raise ValidationFailedError(
            f"Dosya {csv_import.MAX_BYTES // 1_000_000} MB sınırını aşıyor."
        )
    return data


def _mapping(raw: str | None) -> dict[str, str | None] | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationFailedError("Sütun eşlemesi okunamadı.") from exc
    if not isinstance(value, dict):
        raise ValidationFailedError("Sütun eşlemesi alan → başlık sözlüğü olmalı.")
    return {str(k): (str(v) if v else None) for k, v in value.items()}


@router.post("/preview")
async def preview(
    _principal: RequireBatchWrite,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    """Dosyayı kaydetmeden okur: başlıklar, önerilen eşleme, ilk 20 satırın doğrulaması."""
    data = await _read(file)
    try:
        return batch_service.preview(data, _mapping(mapping))
    except csv_import.CsvImportError as exc:
        raise ValidationFailedError(str(exc)) from exc


@router.post("", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
async def create_batch(
    principal: RequireBatchWrite,
    session: TenantSessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str, Form()],
) -> BatchResponse:
    """Toplu işi taslak olarak kaydeder (yalnız eşlenen alanlar saklanır, TCKN alınmaz)."""
    data = await _read(file)
    parsed_mapping = _mapping(mapping) or {}
    try:
        batch = await batch_service.create_batch(
            session,
            tenant_id=principal.tenant_id,
            file_name=file.filename or "toplu.csv",
            data=data,
            mapping=parsed_mapping,
            actor=_actor(principal),
            retention_years=settings.document_retention_years,
        )
    except csv_import.CsvImportError as exc:
        raise ValidationFailedError(str(exc)) from exc
    return await _response(session, batch)


@router.get("", response_model=BatchListResponse)
async def list_batches(
    _principal: PrincipalDep,
    session: TenantSessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> BatchListResponse:
    from sqlalchemy import select

    rows = await session.scalars(
        select(ScreeningBatch).order_by(ScreeningBatch.created_at.desc()).limit(limit)
    )
    return BatchListResponse(items=[await _response(session, b) for b in rows])


@router.get("/{batch_id}", response_model=BatchResponse)
async def get_batch(
    batch_id: uuid.UUID, _principal: PrincipalDep, session: TenantSessionDep
) -> BatchResponse:
    return await _response(session, await _load(session, batch_id))


@router.post("/{batch_id}/start", response_model=BatchResponse)
async def start_batch(
    batch_id: uuid.UUID,
    principal: RequireBatchWrite,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> BatchResponse:
    """Kota denetimiyle başlatır ve worker'a bırakır. Kuyruğa ulaşılamazsa iş ``queued``
    kalır; "şimdi işle" ile ya da worker ayağa kalkınca devam eder."""
    batch = await _load(session, batch_id)
    try:
        await batch_service.start_batch(session, batch, actor=_actor(principal))
    except batch_service.BatchError as exc:
        raise _raise(exc) from exc
    try:
        batch.task_id = dispatch(
            TASK_BATCH_PROCESS,
            kwargs={"tenant_id": str(principal.tenant_id), "batch_id": str(batch.id)},
            redis_url=settings.redis_url,
        )
    except Exception:  # kuyruk yoksa iş kaybolmaz: queued kalır
        logger.exception("toplu_is_kuyruga_alinamadi", batch_id=str(batch.id))
    await session.flush()
    return await _response(session, batch)


@router.post("/{batch_id}/process", response_model=ProcessResponse)
async def process_now(
    batch_id: uuid.UUID,
    _principal: RequireRunNow,
    session: TenantSessionDep,
    settings: SettingsDep,
    yente: YenteClientDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ProcessResponse:
    batch = await _load(session, batch_id)
    try:
        result = await batch_service.process_rows(
            session, yente, batch, settings=settings, limit=limit
        )
    except batch_service.BatchError as exc:
        raise _raise(exc) from exc
    return ProcessResponse(**result)


@router.post("/{batch_id}/retry", response_model=BatchResponse)
async def retry_failed(
    batch_id: uuid.UUID,
    principal: RequireBatchWrite,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> BatchResponse:
    batch = await _load(session, batch_id)
    try:
        count = await batch_service.retry_failed(session, batch, actor=_actor(principal))
    except batch_service.BatchError as exc:
        raise _raise(exc) from exc
    if count:
        try:
            dispatch(
                TASK_BATCH_PROCESS,
                kwargs={"tenant_id": str(principal.tenant_id), "batch_id": str(batch.id)},
                redis_url=settings.redis_url,
            )
        except Exception:
            logger.exception("toplu_is_kuyruga_alinamadi", batch_id=str(batch.id))
    return await _response(session, batch)


@router.post("/{batch_id}/cancel", response_model=BatchResponse)
async def cancel_batch(
    batch_id: uuid.UUID, principal: RequireBatchWrite, session: TenantSessionDep
) -> BatchResponse:
    batch = await _load(session, batch_id)
    try:
        await batch_service.cancel_batch(session, batch, actor=_actor(principal))
    except batch_service.BatchError as exc:
        raise _raise(exc) from exc
    return await _response(session, batch)


@router.get("/{batch_id}/rows", response_model=RowListResponse)
async def list_rows(
    batch_id: uuid.UUID,
    _principal: PrincipalDep,
    session: TenantSessionDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    hits: bool = False,
    sort: Annotated[str, Query(pattern="^(risk|row|name)$")] = "risk",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RowListResponse:
    await _load(session, batch_id)
    statuses = [s for s in (status_filter or "").split(",") if s] or None
    rows, total = await batch_service.list_rows(
        session,
        batch_id,
        statuses=statuses,
        only_hits=hits,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return RowListResponse(items=[_row(r) for r in rows], total=total)


@router.post("/{batch_id}/rows/{row_id}/resolve", response_model=RowResponse)
async def resolve_row(
    batch_id: uuid.UUID,
    row_id: uuid.UUID,
    body: ResolveRequest,
    principal: RequireBatchWrite,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> RowResponse:
    """Belirsiz eşleşmede insan kararı; satır yeniden kuyruğa girer."""
    batch = await _load(session, batch_id)
    row = await session.get(ScreeningBatchRow, row_id)
    if row is None or row.batch_id != batch.id:
        raise NotFoundError("Satır bulunamadı.")
    try:
        await batch_service.resolve_row(
            session,
            batch,
            row,
            entity_id=body.entity_id,
            actor=_actor(principal),
            settings=settings,
        )
    except batch_service.BatchError as exc:
        raise _raise(exc) from exc
    return _row(row)


@router.post("/{batch_id}/bulk", response_model=BulkResponse)
async def bulk(
    batch_id: uuid.UUID,
    body: BulkRequest,
    principal: RequireBatchWrite,
    session: TenantSessionDep,
) -> BulkResponse:
    """Seçili (taranmış) satırların varlıklarını izlemeye alır ya da her biri için vaka açar."""
    batch = await _load(session, batch_id)
    try:
        result = await batch_service.bulk_action(
            session, batch, body.row_ids, body.action, actor=_actor(principal)
        )
    except batch_service.BatchError as exc:
        raise _raise(exc) from exc
    return BulkResponse(**result)


@router.get("/{batch_id}/export.csv")
async def export(
    batch_id: uuid.UUID, _principal: PrincipalDep, session: TenantSessionDep
) -> Response:
    """Sonuç özeti (Excel'de doğrudan açılır: UTF-8 BOM, ``;``), riske göre sıralı."""
    batch = await _load(session, batch_id)
    rows, _ = await batch_service.list_rows(
        session, batch.id, statuses=None, only_hits=False, sort="risk", limit=5000, offset=0
    )
    stem = batch.file_name.rsplit(".", 1)[0][:60] or "toplu"
    ascii_name = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") or "toplu"
    return Response(
        content=batch_service.export_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_name}-sonuc.csv"; '
            f"filename*=UTF-8''{quote(stem)}-sonuc.csv"
        },
    )
