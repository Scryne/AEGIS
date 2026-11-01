"""Toplu tarama servisi (E3.3, ADR-0015).

Akış: CSV + sütun eşlemesi → taslak (satırlar doğrulanmış, yalnız eşlenen alanlar) → başlat
(kota denetimi, ``queued``) → parça parça işleme (worker ya da "şimdi işle") → sonuç.

Satır işleme, elle varlık taramasıyla aynı yolu kullanır: varlık çözümlemesi (E1.4 ER) →
eşleşen varlık ya da yeni varlık → ``subjects_for_entity`` → ``run_screening``. ER belirsiz
derse satır ``needs_review`` olur ve insan karar verene kadar taranmaz: toplu iş iki farklı
müşteriyi sessizce birleştirmez.

Her satır kendi alt işlemindedir; bir satırın hatası diğerlerini durdurmaz. Satırlar
``FOR UPDATE SKIP LOCKED`` ile alınır, böylece worker ile "şimdi işle" aynı anda çalışsa bile
bir satır iki kez taranmaz. Yarıda kalan koşu kalan ``pending`` satırlardan devam eder.
"""

from __future__ import annotations

import csv
import hashlib
import io
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.batch import csv_import
from aegis_core.billing import service as billing_service
from aegis_core.cases import service as case_service
from aegis_core.cases.lifecycle import CaseSource
from aegis_core.config import Settings
from aegis_core.entities import service as entity_service
from aegis_core.entities.resolution import ResolutionOutcome, ResolutionQuery, resolve_entity
from aegis_core.logging import get_logger
from aegis_core.models import (
    AuditAction,
    BatchStatus,
    Entity,
    EntitySchema,
    MatchCandidate,
    RowStatus,
    ScreeningBatch,
    ScreeningBatchRow,
    ScreeningStatus,
    SourceType,
)
from aegis_core.monitoring import service as monitoring_service
from aegis_core.screening import service as screening_service
from aegis_core.screening.entity_run import load_thresholds, subjects_for_entity
from aegis_core.screening.yente import YenteClient
from aegis_core.services import audit as audit_service

logger = get_logger("aegis.batch")

MAX_ATTEMPTS = 3
OBJECT_TYPE = "screening_batch"


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID | None
    role: str


class BatchError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def risk_rank(*, sanction_hits: int, pep_hits: int, flagged: int, top_score: float | None) -> int:
    """Sonuç listesinin sıralama anahtarı: yaptırım > PEP > yüksek skorlu aday > skor."""
    return sanction_hits * 1000 + pep_hits * 300 + flagged * 50 + round((top_score or 0.0) * 100)


async def _audit(
    session: AsyncSession,
    batch: ScreeningBatch,
    action: AuditAction,
    actor: Actor,
    payload: dict[str, Any],
) -> None:
    await audit_service.record_event(
        session,
        tenant_id=batch.tenant_id,
        actor_user_id=actor.user_id,
        actor_role=actor.role,
        action=action,
        object_type=OBJECT_TYPE,
        object_id=str(batch.id),
        payload=payload,
    )


def preview(data: bytes, mapping: Mapping[str, str | None] | None = None) -> dict[str, Any]:
    """Durumsuz önizleme: başlıklar, önerilen eşleme, ilk 20 satırın doğrulanmış hâli."""
    parsed = csv_import.parse(data)
    suggested = csv_import.suggest_mapping(parsed.headers)
    used = csv_import.validate_mapping(parsed.headers, mapping or suggested)
    rows = csv_import.build_rows(parsed, used)
    return {
        "headers": parsed.headers,
        "delimiter": parsed.delimiter,
        "suggested_mapping": suggested,
        "mapping": used,
        "national_id_columns": csv_import.national_id_headers(parsed.headers),
        "total_rows": len(rows),
        "valid_rows": sum(1 for r in rows if r.valid and r.duplicate_of is None),
        "invalid_rows": sum(1 for r in rows if not r.valid),
        "duplicate_rows": sum(1 for r in rows if r.valid and r.duplicate_of is not None),
        "sample": [
            {
                "row_no": r.row_no,
                "data": r.data,
                "errors": r.errors,
                "warnings": r.warnings,
                "duplicate_of": r.duplicate_of,
            }
            for r in rows[:20]
        ],
    }


async def create_batch(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    file_name: str,
    data: bytes,
    mapping: Mapping[str, str | None],
    actor: Actor,
    retention_years: int,
) -> ScreeningBatch:
    parsed = csv_import.parse(data)
    used = csv_import.validate_mapping(parsed.headers, mapping)
    drafts = csv_import.build_rows(parsed, used)
    batch = ScreeningBatch(
        tenant_id=tenant_id,
        file_name=file_name[:255] or "toplu.csv",
        file_sha256=hashlib.sha256(data).hexdigest(),
        column_map=dict(used),
        status=BatchStatus.DRAFT.value,
        total_rows=len(drafts),
        created_by_user_id=actor.user_id,
        created_by_role=actor.role,
        retention_until=datetime.now(UTC) + timedelta(days=365 * retention_years),
    )
    session.add(batch)
    await session.flush()
    for d in drafts:
        if not d.valid:
            st = RowStatus.INVALID
        elif d.duplicate_of is not None:
            st = RowStatus.DUPLICATE
        else:
            st = RowStatus.PENDING
        session.add(
            ScreeningBatchRow(
                tenant_id=tenant_id,
                batch_id=batch.id,
                row_no=d.row_no,
                data=d.data,
                errors=d.errors,
                warnings=d.warnings,
                status=st.value,
                duplicate_of=d.duplicate_of,
            )
        )
    await session.flush()
    counts = await row_counts(session, batch.id)
    await _audit(
        session,
        batch,
        AuditAction.BATCH_CREATE,
        actor,
        {"file_sha256": batch.file_sha256, "rows": batch.total_rows, "counts": counts},
    )
    return batch


async def row_counts(session: AsyncSession, batch_id: uuid.UUID) -> dict[str, int]:
    rows = await session.execute(
        select(ScreeningBatchRow.status, func.count())
        .where(ScreeningBatchRow.batch_id == batch_id)
        .group_by(ScreeningBatchRow.status)
    )
    out = {s.value: 0 for s in RowStatus}
    for st, n in rows:
        out[st] = int(n)
    return out


async def risk_counts(session: AsyncSession, batch_id: uuid.UUID) -> dict[str, int]:
    row = (
        await session.execute(
            select(
                func.count().filter(ScreeningBatchRow.sanction_hits > 0),
                func.count().filter(ScreeningBatchRow.pep_hits > 0),
                func.count().filter(ScreeningBatchRow.flagged_count > 0),
            ).where(ScreeningBatchRow.batch_id == batch_id)
        )
    ).one()
    return {"sanction_rows": int(row[0]), "pep_rows": int(row[1]), "flagged_rows": int(row[2])}


async def start_batch(
    session: AsyncSession, batch: ScreeningBatch, *, actor: Actor
) -> ScreeningBatch:
    if batch.status != BatchStatus.DRAFT.value:
        raise BatchError("invalid_state", "Yalnız taslak toplu iş başlatılabilir.")
    pending = (await row_counts(session, batch.id))[RowStatus.PENDING.value]
    if pending == 0:
        raise BatchError("invalid_state", "Taranacak geçerli satır yok.")
    try:
        # Her satır en az bir sorgudur (varlığın kendisi); bağlı kişiler gerçek kullanımda sayılır.
        await billing_service.require_screening_quota(session, batch.tenant_id, pending)
    except billing_service.QuotaExceededError as exc:
        raise BatchError("quota", str(exc)) from exc
    batch.status = BatchStatus.QUEUED.value
    await session.flush()
    await _audit(session, batch, AuditAction.BATCH_START, actor, {"pending_rows": pending})
    return batch


async def _screen_row(
    session: AsyncSession,
    client: YenteClient,
    batch: ScreeningBatch,
    row: ScreeningBatchRow,
    entity: Entity,
    settings: Settings,
) -> None:
    screening = await screening_service.run_screening(
        session,
        client,
        tenant_id=batch.tenant_id,
        subjects=await subjects_for_entity(session, entity),
        thresholds=await load_thresholds(session),
        dataset=settings.yente_dataset,
        algorithm=settings.yente_algorithm,
        requested_by_user_id=batch.created_by_user_id,
        requested_by_role=batch.created_by_role,
        entity_id=entity.id,
        retention_years=settings.document_retention_years,
        limit=settings.screening_candidate_limit,
    )
    row.screening_id = screening.id
    if screening.status != ScreeningStatus.COMPLETED.value:
        row.status = RowStatus.FAILED.value
        row.error = "Tarama yapılamadı (tarama motoruna ulaşılamadı); yeniden denenebilir."
        return
    summary = await screening_service.summarize_screening(session, screening.id)
    top = await session.scalar(
        select(func.max(MatchCandidate.score)).where(MatchCandidate.screening_id == screening.id)
    )
    row.candidate_count = summary.total
    row.flagged_count = summary.flagged
    row.sanction_hits = summary.sanction_hits
    row.pep_hits = summary.pep_hits
    row.top_score = float(top) if top is not None else None
    row.risk_rank = risk_rank(
        sanction_hits=summary.sanction_hits,
        pep_hits=summary.pep_hits,
        flagged=summary.flagged,
        top_score=row.top_score,
    )
    row.status = RowStatus.DONE.value
    row.error = None


async def _entity_for_row(
    session: AsyncSession, batch: ScreeningBatch, row: ScreeningBatchRow, settings: Settings
) -> Entity | None:
    """Satırın varlığı: önceden bağlanmışsa o, ER eşleşirse o, yeni ise açılır, belirsizse None."""
    if row.entity_id is not None:
        return await entity_service.get_entity(session, row.entity_id)
    d = row.data
    result = await resolve_entity(
        session,
        ResolutionQuery(
            name=d["name"],
            schema_type=EntitySchema(d["schema_type"]),
            tax_number=d.get("tax_number"),
            mersis_number=d.get("mersis_number"),
        ),
    )
    row.resolution_candidates = [
        {
            "entity_id": str(c.entity_id),
            "name": c.name,
            "similarity": round(c.similarity, 3),
            "reason": c.reason,
            "conflicting_identifier": c.conflicting_identifier,
        }
        for c in result.candidates[:5]
    ]
    if result.outcome is ResolutionOutcome.MATCHED and result.matched is not None:
        row.resolution = "matched"
        row.entity_id = result.matched.id
        return result.matched
    if result.outcome is ResolutionOutcome.AMBIGUOUS:
        row.resolution = "ambiguous"
        row.status = RowStatus.NEEDS_REVIEW.value
        return None
    entity, _warnings = await entity_service.create_entity(
        session,
        tenant_id=batch.tenant_id,
        name=d["name"],
        schema_type=EntitySchema(d["schema_type"]),
        tax_number=d.get("tax_number"),
        mersis_number=d.get("mersis_number"),
        country=d.get("country"),
        source_type=SourceType.DECLARED,
        source_ref=f"batch:{batch.id}#satir-{row.row_no}",
        actor_user_id=batch.created_by_user_id,
        actor_role=batch.created_by_role,
        retention_years=settings.document_retention_years,
    )
    row.resolution = "new"
    row.entity_id = entity.id
    return entity


async def process_rows(
    session: AsyncSession,
    client: YenteClient,
    batch: ScreeningBatch,
    *,
    settings: Settings,
    limit: int = 25,
) -> dict[str, int]:
    """En çok ``limit`` bekleyen satırı işler. Dönen ``remaining`` 0 ise iş bitmiştir."""
    if batch.status not in (BatchStatus.QUEUED.value, BatchStatus.RUNNING.value):
        raise BatchError("invalid_state", "Toplu iş işlenecek durumda değil.")
    if batch.status == BatchStatus.QUEUED.value:
        batch.status = BatchStatus.RUNNING.value
        batch.started_at = datetime.now(UTC)
    rows = list(
        await session.scalars(
            select(ScreeningBatchRow)
            .where(
                ScreeningBatchRow.batch_id == batch.id,
                ScreeningBatchRow.status == RowStatus.PENDING.value,
            )
            .order_by(ScreeningBatchRow.row_no)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    done = failed = review = 0
    for row in rows:
        row.attempts += 1
        try:
            async with session.begin_nested():
                entity = await _entity_for_row(session, batch, row, settings)
                if entity is not None:
                    await _screen_row(session, client, batch, row, entity, settings)
        except Exception as exc:  # bir satırın hatası diğerlerini durdurmaz
            logger.exception("toplu_satir_hatasi", batch_id=str(batch.id), row_no=row.row_no)
            row.status = RowStatus.FAILED.value
            row.error = f"İşlenemedi: {type(exc).__name__}"
        row.processed_at = datetime.now(UTC)
        if row.status == RowStatus.DONE.value:
            done += 1
        elif row.status == RowStatus.NEEDS_REVIEW.value:
            review += 1
        elif row.status == RowStatus.FAILED.value:
            failed += 1
    await session.flush()
    remaining = (await row_counts(session, batch.id))[RowStatus.PENDING.value]
    if remaining == 0:
        await _finish(session, batch)
    return {
        "processed": len(rows),
        "done": done,
        "needs_review": review,
        "failed": failed,
        "remaining": remaining,
    }


async def _finish(session: AsyncSession, batch: ScreeningBatch) -> None:
    if batch.status == BatchStatus.COMPLETED.value:
        return
    batch.status = BatchStatus.COMPLETED.value
    batch.finished_at = datetime.now(UTC)
    await session.flush()
    await _audit(
        session,
        batch,
        AuditAction.BATCH_COMPLETE,
        Actor(None, "worker"),
        {"counts": await row_counts(session, batch.id), **await risk_counts(session, batch.id)},
    )


def _require_active(batch: ScreeningBatch) -> None:
    if batch.status in (BatchStatus.CANCELLED.value, BatchStatus.DRAFT.value):
        raise BatchError("invalid_state", "Toplu iş başlatılmamış ya da iptal edilmiş.")


async def retry_failed(session: AsyncSession, batch: ScreeningBatch, *, actor: Actor) -> int:
    """Deneme hakkı kalan başarısız satırları yeniden kuyruğa alır."""
    _require_active(batch)
    rows = list(
        await session.scalars(
            select(ScreeningBatchRow).where(
                ScreeningBatchRow.batch_id == batch.id,
                ScreeningBatchRow.status == RowStatus.FAILED.value,
                ScreeningBatchRow.attempts < MAX_ATTEMPTS,
            )
        )
    )
    for row in rows:
        row.status = RowStatus.PENDING.value
        row.error = None  # eski hata yeni denemenin sonucuyla karışmasın (iz denetimde)
    if rows:
        batch.status = BatchStatus.RUNNING.value
        batch.finished_at = None
    await session.flush()
    await _audit(session, batch, AuditAction.BATCH_START, actor, {"retry_rows": len(rows)})
    return len(rows)


async def resolve_row(
    session: AsyncSession,
    batch: ScreeningBatch,
    row: ScreeningBatchRow,
    *,
    entity_id: uuid.UUID | None,
    actor: Actor,
    settings: Settings,
) -> ScreeningBatchRow:
    """Belirsiz satırda insan kararı: mevcut bir varlık (``entity_id``) ya da yeni varlık."""
    _require_active(batch)
    if row.status != RowStatus.NEEDS_REVIEW.value:
        raise BatchError("invalid_state", "Yalnız karar bekleyen satır çözümlenebilir.")
    if entity_id is not None:
        entity = await entity_service.get_entity(session, entity_id)
        if entity is None:
            raise BatchError("not_found", "Varlık bulunamadı.")
        row.entity_id = entity.id
        row.resolution = "matched_by_user"
    else:
        d = row.data
        entity, _ = await entity_service.create_entity(
            session,
            tenant_id=batch.tenant_id,
            name=d["name"],
            schema_type=EntitySchema(d["schema_type"]),
            tax_number=d.get("tax_number"),
            mersis_number=d.get("mersis_number"),
            country=d.get("country"),
            source_type=SourceType.DECLARED,
            source_ref=f"batch:{batch.id}#satir-{row.row_no}",
            actor_user_id=actor.user_id,
            actor_role=actor.role,
            retention_years=settings.document_retention_years,
        )
        row.entity_id = entity.id
        row.resolution = "new_by_user"
    row.status = RowStatus.PENDING.value
    if batch.status == BatchStatus.COMPLETED.value:
        batch.status = BatchStatus.RUNNING.value
        batch.finished_at = None
    await session.flush()
    await _audit(
        session,
        batch,
        AuditAction.BATCH_ROW_RESOLVE,
        actor,
        {"row_no": row.row_no, "entity_id": str(row.entity_id), "decision": row.resolution},
    )
    return row


async def cancel_batch(
    session: AsyncSession, batch: ScreeningBatch, *, actor: Actor
) -> ScreeningBatch:
    if batch.status in (BatchStatus.COMPLETED.value, BatchStatus.CANCELLED.value):
        raise BatchError("invalid_state", "Bitmiş toplu iş iptal edilemez.")
    rows = list(
        await session.scalars(
            select(ScreeningBatchRow).where(
                ScreeningBatchRow.batch_id == batch.id,
                ScreeningBatchRow.status.in_(
                    [RowStatus.PENDING.value, RowStatus.NEEDS_REVIEW.value]
                ),
            )
        )
    )
    for row in rows:
        row.status = RowStatus.CANCELLED.value
    batch.status = BatchStatus.CANCELLED.value
    batch.finished_at = datetime.now(UTC)
    await session.flush()
    await _audit(session, batch, AuditAction.BATCH_CANCEL, actor, {"cancelled_rows": len(rows)})
    return batch


SORTS = {
    "risk": (ScreeningBatchRow.risk_rank.desc(), ScreeningBatchRow.row_no),
    "row": (ScreeningBatchRow.row_no,),
    "name": (ScreeningBatchRow.data["name"].astext, ScreeningBatchRow.row_no),
}


async def list_rows(
    session: AsyncSession,
    batch_id: uuid.UUID,
    *,
    statuses: Sequence[str] | None,
    only_hits: bool,
    sort: str,
    limit: int,
    offset: int,
) -> tuple[list[ScreeningBatchRow], int]:
    base = select(ScreeningBatchRow).where(ScreeningBatchRow.batch_id == batch_id)
    if statuses:
        base = base.where(ScreeningBatchRow.status.in_(statuses))
    if only_hits:
        base = base.where(ScreeningBatchRow.risk_rank > 0, ScreeningBatchRow.candidate_count > 0)
    total = int(await session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = await session.scalars(base.order_by(*SORTS[sort]).limit(limit).offset(offset))
    return list(rows), total


async def bulk_action(
    session: AsyncSession,
    batch: ScreeningBatch,
    row_ids: Sequence[uuid.UUID],
    action: str,
    *,
    actor: Actor,
) -> dict[str, int]:
    """Seçili satırların varlıklarına toplu işlem: izlemeye al ya da vaka aç."""
    rows = list(
        await session.scalars(
            select(ScreeningBatchRow).where(
                ScreeningBatchRow.batch_id == batch.id,
                ScreeningBatchRow.id.in_(list(row_ids)),
                ScreeningBatchRow.status == RowStatus.DONE.value,
                ScreeningBatchRow.entity_id.is_not(None),
            )
        )
    )
    applied = skipped = 0
    for row in rows:
        entity = await entity_service.get_entity(session, row.entity_id) if row.entity_id else None
        if entity is None:
            skipped += 1
            continue
        if action == "monitor":
            if entity.monitored:
                skipped += 1
                continue
            try:
                await billing_service.require_monitoring_slot(session, batch.tenant_id)
            except billing_service.MonitoringLimitError as exc:
                raise BatchError("plan_limit", str(exc)) from exc
            await monitoring_service.set_monitored(
                session,
                entity,
                True,
                tenant_id=batch.tenant_id,
                actor_user_id=actor.user_id,
                actor_role=actor.role,
            )
            applied += 1
        elif action == "open_case":
            severity = (
                "critical"
                if (row.sanction_hits or 0) > 0
                else "high"
                if (row.pep_hits or 0) > 0
                else "info"
            )
            await case_service.open_case(
                session,
                tenant_id=batch.tenant_id,
                entity=entity,
                title=f"Toplu tarama ({batch.file_name}, satır {row.row_no}): {entity.name}",
                source=CaseSource.SCREENING,
                severity=severity,
                edd=severity == "critical",
                actor=case_service.Actor(actor.user_id, actor.role),
                source_screening_id=row.screening_id,
            )
            applied += 1
        else:
            raise BatchError("invalid", f"Bilinmeyen toplu işlem: {action}")
    skipped += len(row_ids) - len(rows)
    return {"applied": applied, "skipped": skipped}


EXPORT_HEADERS = (
    "Satır",
    "Ad / unvan",
    "Tür",
    "Vergi no",
    "Müşteri referansı",
    "Durum",
    "Kütük eşleşmesi",
    "Aday",
    "Yüksek skorlu",
    "Yaptırım",
    "PEP",
    "En yüksek skor",
    "Varlık",
    "Tarama",
    "Not",
)

STATUS_TR = {
    "invalid": "Geçersiz",
    "duplicate": "Dosyada tekrar",
    "pending": "Bekliyor",
    "done": "Tarandı",
    "needs_review": "Karar bekliyor",
    "failed": "Başarısız",
    "cancelled": "İptal",
}
RESOLUTION_TR = {
    "matched": "Mevcut varlık",
    "new": "Yeni varlık",
    "ambiguous": "Belirsiz",
    "matched_by_user": "Mevcut varlık (kullanıcı)",
    "new_by_user": "Yeni varlık (kullanıcı)",
}


def _safe(value: object) -> str:
    """CSV formül enjeksiyonuna karşı (=, +, -, @ ile başlayan hücre metin olarak kalır)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def export_csv(rows: Sequence[ScreeningBatchRow]) -> bytes:
    """Türkçe Excel'in doğrudan açtığı biçim: UTF-8 BOM, ``;`` ayraç."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(EXPORT_HEADERS)
    for r in rows:
        d = r.data
        note = (
            "; ".join(r.errors or [])
            or r.error
            or (f"{r.duplicate_of}. satırın tekrarı" if r.duplicate_of else "")
        )
        w.writerow(
            [
                _safe(x)
                for x in (
                    r.row_no,
                    d.get("name"),
                    "Kişi" if d.get("schema_type") == "Person" else "Şirket",
                    d.get("tax_number"),
                    d.get("external_ref"),
                    STATUS_TR.get(r.status, r.status),
                    RESOLUTION_TR.get(r.resolution or "", ""),
                    r.candidate_count,
                    r.flagged_count,
                    r.sanction_hits,
                    r.pep_hits,
                    f"{r.top_score:.2f}" if r.top_score is not None else "",
                    r.entity_id,
                    r.screening_id,
                    note,
                )
            ]
        )
    return ("﻿" + buf.getvalue()).encode("utf-8")
