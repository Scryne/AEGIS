"""/api/v1/documents — belge yükleme, indirme ve çıkarım önerileri (E1.4, R2).

Belgenin kendisi nesne deposunda, meta veritabanında durur. İndirme **kısa ömürlü imzalı
URL** ile yapılır: dosya API üzerinden akıtılmaz (bellek/bant genişliği) ve bağlantı
paylaşılsa bile kalıcı bir erişim kapısı bırakmaz.

Çıkarım **asenkrondur**: Docling ağır bir motordur ve yükleme isteğini bekletmemelidir.
Yükleme ``pending`` döner, Celery görevi çıkarımı yapar, kullanıcı öneri listesini
tazeler. Motor kurulu değilse belge ``skipped`` olur — yükleme yine başarılıdır.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from aegis_api.dependencies import (
    Principal,
    PrincipalDep,
    SettingsDep,
    TenantSessionDep,
    require_role,
)
from aegis_api.errors import ConflictError, NotFoundError, ValidationFailedError
from aegis_api.queue import dispatch
from aegis_core.documents import service as document_service
from aegis_core.documents.service import (
    AmbiguousProposalError,
    DocumentInputError,
    UploadedFile,
)
from aegis_core.documents.storage import (
    StorageError,
    build_storage_key,
    ensure_bucket,
    presigned_url,
    put_object,
    sha256_hex,
)
from aegis_core.entities import service as entity_service
from aegis_core.models import Document, DocumentType, ExtractionProposal, Role
from aegis_core.queueing import TASK_DOCUMENT_EXTRACT

router = APIRouter(prefix="/documents", tags=["documents"])

RequireDocumentWrite = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.ANALYST))
]

DocTypeLiteral = Literal["imza_sirkuleri", "faaliyet_belgesi", "ticaret_sicil_gazetesi", "other"]


# ── Şemalar ──────────────────────────────────────────────────────────────────


class DocumentResponse(BaseModel):
    """Belge kaydı."""

    id: uuid.UUID
    entity_id: uuid.UUID | None
    doc_type: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    source_ref: str | None
    extraction_status: str
    extraction_error: str | None
    extraction_engine: str | None
    page_count: int | None
    extracted_at: datetime | None
    created_at: datetime


class DocumentDownloadResponse(BaseModel):
    """Kısa ömürlü indirme bağlantısı."""

    url: str
    expires_in_seconds: int


class ProposalResponse(BaseModel):
    """Belgeden çıkan, onay bekleyen öneri."""

    id: uuid.UUID
    document_id: uuid.UUID
    entity_id: uuid.UUID | None
    kind: str
    payload: dict[str, Any]
    confidence: float
    evidence_text: str | None
    page_number: int | None
    status: str
    review_note: str | None
    reviewed_at: datetime | None
    resulting_entity_id: uuid.UUID | None


class ProposalDecisionRequest(BaseModel):
    """Öneri kararı."""

    decision: Literal["accepted", "rejected"]
    note: str | None = Field(default=None, max_length=2000)
    link_entity_id: uuid.UUID | None = None
    """Kişi önerisi belirsizse: hangi mevcut kayda bağlanacağı (kullanıcı seçimi)."""


# ── Dönüştürücüler ───────────────────────────────────────────────────────────


def _document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        entity_id=document.entity_id,
        doc_type=document.doc_type,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        sha256=document.sha256,
        source_ref=document.source_ref,
        extraction_status=document.extraction_status,
        extraction_error=document.extraction_error,
        extraction_engine=document.extraction_engine,
        page_count=document.page_count,
        extracted_at=document.extracted_at,
        created_at=document.created_at,
    )


def _proposal_response(proposal: ExtractionProposal) -> ProposalResponse:
    payload = dict(proposal.payload)
    # TCKN öneride şifreli durur; arayüze yalnız maskesi gider (şifreli token hiç çıkmaz).
    token_masked = payload.pop("national_id_masked", None)
    payload.pop("national_id_enc", None)
    if token_masked:
        payload["national_id"] = token_masked
    elif payload.get("national_id"):  # şifreleme öncesi (eski) satırlar
        payload["national_id"] = entity_service.mask_identifier(str(payload["national_id"]))
    return ProposalResponse(
        id=proposal.id,
        document_id=proposal.document_id,
        entity_id=proposal.entity_id,
        kind=proposal.kind,
        payload=payload,
        confidence=proposal.confidence,
        evidence_text=proposal.evidence_text,
        page_number=proposal.page_number,
        status=proposal.status,
        review_note=proposal.review_note,
        reviewed_at=proposal.reviewed_at,
        resulting_entity_id=proposal.resulting_entity_id,
    )


# ── Uçlar ────────────────────────────────────────────────────────────────────


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    principal: RequireDocumentWrite,
    session: TenantSessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    entity_id: Annotated[uuid.UUID | None, Form()] = None,
    doc_type: Annotated[DocTypeLiteral, Form()] = "other",
    gazette_issue_number: Annotated[str | None, Form()] = None,
    gazette_issue_date: Annotated[date | None, Form()] = None,
    gazette_url: Annotated[str | None, Form()] = None,
) -> DocumentResponse:
    """Belge yükler; çıkarılabilir türse çıkarımı kuyruğa alır.

    Ticaret Sicil Gazetesi için (Revizyon R1: otomatik sorgu YOK) kullanıcı sayı/tarih/
    bağlantı verir; bunlar kanıt referansı olarak saklanır ve raporda görünür.
    """
    if entity_id is not None:
        entity = await entity_service.get_entity(session, entity_id)
        if entity is None:
            raise NotFoundError("Varlık bulunamadı.")

    data = await file.read()
    upload = UploadedFile(
        filename=file.filename or "belge",
        content_type=file.content_type or "application/octet-stream",
        data=data,
    )
    try:
        document_service.validate_upload(upload, max_size_mb=settings.max_document_size_mb)
    except DocumentInputError as exc:
        raise ValidationFailedError(str(exc)) from exc

    resolved_type = DocumentType(doc_type)
    source_ref: str | None = None
    if resolved_type is DocumentType.TICARET_SICIL_GAZETESI:
        source_ref = document_service.gazette_source_ref(
            issue_number=gazette_issue_number,
            issue_date=gazette_issue_date,
            url=gazette_url,
        )

    document_id = uuid.uuid4()
    key = build_storage_key(principal.tenant_id, document_id, upload.filename)
    try:
        # boto3 senkrondur; olay döngüsünü bloke etmemek için havuzda çalışır.
        await run_in_threadpool(ensure_bucket, settings)
        stored = await run_in_threadpool(
            put_object, key, upload.data, upload.content_type, settings
        )
    except StorageError as exc:
        raise ValidationFailedError(f"Belge saklanamadı: {exc}") from exc

    try:
        document = await document_service.create_document(
            session,
            tenant_id=principal.tenant_id,
            entity_id=entity_id,
            doc_type=resolved_type,
            filename=upload.filename,
            content_type=upload.content_type,
            size_bytes=stored.size_bytes,
            sha256=sha256_hex(upload.data),
            storage_key=stored.key,
            source_ref=source_ref,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
            retention_years=settings.document_retention_years,
        )
    except DocumentInputError as exc:
        raise ValidationFailedError(str(exc)) from exc

    if document.extraction_status == "pending":
        dispatch(
            TASK_DOCUMENT_EXTRACT,
            kwargs={
                "tenant_id": str(principal.tenant_id),
                "document_id": str(document.id),
                "actor_role": principal.role.value,
            },
            redis_url=settings.redis_url,
        )
    return _document_response(document)


@router.post(
    "/{document_id}/extract",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_extraction(
    document_id: uuid.UUID,
    principal: RequireDocumentWrite,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> DocumentResponse:
    """Başarısız ya da atlanmış çıkarımı yeniden kuyruğa alır (ör. Docling sonradan kuruldu).

    Belge ``pending``'e döner ve çıkarım görevi yeniden gönderilir; uygun olmayan durumda
    (tamamlanmış, bekleyen ya da çıkarım yapılmayan tür) **409**.
    """
    document = await document_service.get_document(session, document_id)
    if document is None:
        raise NotFoundError("Belge bulunamadı.")
    try:
        document = await document_service.requeue_extraction(
            session,
            document,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
        )
    except DocumentInputError as exc:
        raise ConflictError(str(exc)) from exc
    dispatch(
        TASK_DOCUMENT_EXTRACT,
        kwargs={
            "tenant_id": str(principal.tenant_id),
            "document_id": str(document.id),
            "actor_role": principal.role.value,
        },
        redis_url=settings.redis_url,
    )
    return _document_response(document)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    _principal: PrincipalDep,
    session: TenantSessionDep,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[DocumentResponse]:
    """Belgeleri listeler (isteğe bağlı varlık süzgeciyle)."""
    rows = await document_service.list_documents(session, entity_id=entity_id)
    return [_document_response(row) for row in rows]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID, _principal: PrincipalDep, session: TenantSessionDep
) -> DocumentResponse:
    """Tek bir belgeyi döndürür."""
    document = await document_service.get_document(session, document_id)
    if document is None:
        raise NotFoundError("Belge bulunamadı.")
    return _document_response(document)


@router.get("/{document_id}/download", response_model=DocumentDownloadResponse)
async def download_document(
    document_id: uuid.UUID,
    _principal: PrincipalDep,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> DocumentDownloadResponse:
    """Belge için kısa ömürlü imzalı indirme bağlantısı üretir."""
    document = await document_service.get_document(session, document_id)
    if document is None:
        raise NotFoundError("Belge bulunamadı.")
    ttl = settings.document_download_url_ttl_seconds
    try:
        url = await run_in_threadpool(
            presigned_url, document.storage_key, expires_in=ttl, settings=settings
        )
    except StorageError as exc:
        raise ValidationFailedError(f"İndirme bağlantısı üretilemedi: {exc}") from exc
    return DocumentDownloadResponse(url=url, expires_in_seconds=ttl)


@router.get("/{document_id}/proposals", response_model=list[ProposalResponse])
async def list_proposals(
    document_id: uuid.UUID,
    _principal: PrincipalDep,
    session: TenantSessionDep,
    pending_only: Annotated[bool, Query()] = False,
) -> list[ProposalResponse]:
    """Belgeden çıkan önerileri döndürür (güveni yüksek olan önce)."""
    document = await document_service.get_document(session, document_id)
    if document is None:
        raise NotFoundError("Belge bulunamadı.")
    rows = await document_service.list_proposals(
        session, document_id=document_id, pending_only=pending_only
    )
    return [_proposal_response(row) for row in rows]


@router.post("/{document_id}/proposals/{proposal_id}/decision", response_model=ProposalResponse)
async def decide_proposal(
    document_id: uuid.UUID,
    proposal_id: uuid.UUID,
    body: ProposalDecisionRequest,
    principal: RequireDocumentWrite,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> ProposalResponse:
    """Öneriyi kabul eder (kütüğe uygular) ya da reddeder.

    Kişi önerisinde kütükte birden çok benzer kayıt varsa **409** döner ve adayları
    listeler; kullanıcı ``link_entity_id`` ile hangisine bağlanacağını seçer. Otomatik
    birleştirme yapılmaz.
    """
    proposal = await document_service.get_proposal(session, proposal_id)
    if proposal is None or proposal.document_id != document_id:
        raise NotFoundError("Öneri bulunamadı.")

    try:
        if body.decision == "accepted":
            updated = await document_service.accept_proposal(
                session,
                proposal,
                actor_user_id=principal.user_id,
                actor_role=principal.role.value,
                link_entity_id=body.link_entity_id,
                note=body.note,
                retention_years=settings.document_retention_years,
            )
        else:
            updated = await document_service.reject_proposal(
                session,
                proposal,
                actor_user_id=principal.user_id,
                actor_role=principal.role.value,
                note=body.note,
            )
    except AmbiguousProposalError as exc:
        raise ConflictError(
            str(exc),
            details=[
                {
                    "entity_id": str(candidate.entity_id),
                    "name": candidate.name,
                    "similarity": candidate.similarity,
                    "reason": candidate.reason,
                }
                for candidate in exc.candidates
            ],
        ) from exc
    except DocumentInputError as exc:
        raise ValidationFailedError(str(exc)) from exc
    return _proposal_response(updated)
