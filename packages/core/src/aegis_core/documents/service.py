"""Belge servisi — yükleme, çıkarım→öneri, önerinin kütüğe uygulanması (E1.4).

Akış::

    yükleme → nesne deposu + document satırı → (Celery) metne çevir → desen çıkarımı
            → ExtractionProposal satırları → İNSAN ONAYI → entity/relationship

Son oktaki **insan onayı** Revizyon R2'nin açık koşuludur ve atlanmaz: OCR'ın okuduğu
bir ismi sessizce "şirketin yöneticisi" yapmak, ürünün "karar desteği" duruşunu bozardı.

Kişi önerisi kabul edilirken varlık çözümleme (ER) devreye girer: aynı kişi başka bir
dosyada zaten varsa yeni kayıt açılmaz. Çözümleme **belirsiz** derse kullanıcıya sorulur
(``AmbiguousProposalError``) — otomatik birleştirme yoktur.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.documents.extraction import ExtractionResult
from aegis_core.entities import service as entity_service
from aegis_core.entities.resolution import (
    ResolutionCandidate,
    ResolutionOutcome,
    ResolutionQuery,
    resolve_entity,
)
from aegis_core.logging import get_logger
from aegis_core.models import (
    AuditAction,
    Document,
    DocumentType,
    Entity,
    EntitySchema,
    ExtractionProposal,
    ExtractionStatus,
    ProposalKind,
    ProposalStatus,
    RelationshipType,
    SourceType,
)
from aegis_core.models.entity import NATIONAL_ID_DOMAIN
from aegis_core.security.encryption import blind_index, get_secret_box
from aegis_core.services import audit as audit_service

logger = get_logger("aegis.documents.service")

# Çıkarımın denendiği belge türleri (R2: kapsam bilinçli olarak dar).
EXTRACTABLE_TYPES = frozenset(
    {
        DocumentType.IMZA_SIRKULERI.value,
        DocumentType.FAALIYET_BELGESI.value,
        DocumentType.TICARET_SICIL_GAZETESI.value,
    }
)

# Kabul edilen içerik türleri — yürütülebilir/aktif içerik kabul edilmez.
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/tiff",
        "text/plain",
    }
)


# Öneri gövdesi JSONB'dir ve şifresizdir (ADR-0007 §5). TCKN oraya düz yazılırsa şifreli
# ``entity.national_id`` kolonu anlamsız kalır: numara karar verilene kadar — reddedilen
# önerilerde saklama süresi boyunca — açıkta dururdu. Bu yüzden öneride yalnız şifreli token
# (alan-ayrımlı AAD ile) ve maske tutulur; düz değer yalnız kabul anında çözülür.
_PROPOSAL_ID_AAD = b"extraction_proposal.national_id"


def seal_national_id(national_id: str) -> dict[str, str]:
    """Öneri gövdesine girecek TCKN alanlarını üretir (şifreli token + maske)."""
    return {
        "national_id_enc": get_secret_box().encrypt(national_id, aad=_PROPOSAL_ID_AAD),
        "national_id_masked": entity_service.mask_identifier(national_id),
    }


def proposal_national_id(payload: dict[str, object]) -> str | None:
    """Öneri gövdesindeki TCKN'yi çözer. Eski (düz metin) satırlar da okunur."""
    token = payload.get("national_id_enc")
    if token:
        return get_secret_box().decrypt(str(token), aad=_PROPOSAL_ID_AAD)
    legacy = payload.get("national_id")
    return str(legacy) if legacy else None


class DocumentInputError(ValueError):
    """Belge girdisi geçersiz (tür, boyut, içerik)."""


class AmbiguousProposalError(RuntimeError):
    """Öneri kabul edilemedi: hangi varlığa bağlanacağı belirsiz — kullanıcı seçmeli."""

    def __init__(self, candidates: list[ResolutionCandidate]) -> None:
        super().__init__("Kişi kütükte birden çok kayda benziyor; seçim gerekiyor.")
        self.candidates = candidates


@dataclass(frozen=True)
class UploadedFile:
    """Yüklenen dosyanın ham hâli."""

    filename: str
    content_type: str
    data: bytes


def validate_upload(upload: UploadedFile, *, max_size_mb: int) -> None:
    """Dosya türü ve boyutunu doğrular (yükleme öncesi kapı)."""
    if not upload.data:
        raise DocumentInputError("Boş dosya yüklenemez.")
    limit = max_size_mb * 1024 * 1024
    if len(upload.data) > limit:
        raise DocumentInputError(f"Dosya {max_size_mb} MB sınırını aşıyor.")
    content_type = upload.content_type.split(";")[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise DocumentInputError(
            f"Desteklenmeyen dosya türü: {content_type}. "
            f"Kabul edilenler: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}."
        )


async def create_document(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity_id: uuid.UUID | None,
    doc_type: DocumentType,
    filename: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    storage_key: str,
    source_ref: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    retention_years: int = 5,
) -> Document:
    """Belge meta kaydını oluşturur ve denetim olayı yazar.

    Dosyanın kendisi çağıran tarafından **önce** nesne deposuna yazılır; burada yalnız
    meta tutulur (bkz. ``storage`` modül başlığı).
    """
    document = Document(
        tenant_id=tenant_id,
        entity_id=entity_id,
        doc_type=doc_type.value,
        filename=filename[:512],
        content_type=content_type[:128],
        size_bytes=size_bytes,
        sha256=sha256,
        storage_key=storage_key,
        source_ref=source_ref,
        uploaded_by_user_id=actor_user_id,
        extraction_status=(
            ExtractionStatus.PENDING.value
            if doc_type.value in EXTRACTABLE_TYPES
            else ExtractionStatus.SKIPPED.value
        ),
        retention_until=datetime.now(UTC) + timedelta(days=365 * retention_years),
    )
    session.add(document)
    await session.flush()

    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.DOCUMENT_UPLOAD,
        object_type="document",
        object_id=str(document.id),
        source_ref=source_ref,
        payload={
            "entity_id": str(entity_id) if entity_id else None,
            "doc_type": document.doc_type,
            "filename": document.filename,
            "sha256": document.sha256,
            "size_bytes": document.size_bytes,
        },
    )
    return document


async def get_document(session: AsyncSession, document_id: uuid.UUID) -> Document | None:
    """Tek bir belgeyi döndürür (RLS ile kiracıya sınırlı)."""
    document: Document | None = await session.scalar(
        select(Document).where(Document.id == document_id)
    )
    return document


async def list_documents(
    session: AsyncSession, *, entity_id: uuid.UUID | None = None
) -> list[Document]:
    """Belgeleri listeler (yeni → eski)."""
    statement = select(Document)
    if entity_id is not None:
        statement = statement.where(Document.entity_id == entity_id)
    result = await session.scalars(statement.order_by(Document.created_at.desc()))
    return list(result)


async def store_extraction_result(
    session: AsyncSession,
    document: Document,
    result: ExtractionResult,
    *,
    engine: str,
    page_count: int | None = None,
) -> list[ExtractionProposal]:
    """Çıkarım sonucunu **öneri** satırlarına çevirir (kütüğe yazmaz).

    Yeniden çalıştırmada mevcut ``pending`` öneriler silinip yenilenir; karara bağlanmış
    öneriler korunur — kullanıcının verdiği karar bir yeniden çıkarımla kaybolmamalıdır.
    """
    existing = list(
        await session.scalars(
            select(ExtractionProposal).where(
                ExtractionProposal.document_id == document.id,
                ExtractionProposal.status == ProposalStatus.PENDING.value,
            )
        )
    )
    for stale in existing:
        await session.delete(stale)

    proposals: list[ExtractionProposal] = []
    for attribute in result.attributes:
        proposals.append(
            ExtractionProposal(
                tenant_id=document.tenant_id,
                document_id=document.id,
                entity_id=document.entity_id,
                kind=ProposalKind.ATTRIBUTE.value,
                payload={"name": attribute.name, "value": attribute.value},
                confidence=attribute.confidence,
                evidence_text=attribute.evidence[:2000] if attribute.evidence else None,
                page_number=attribute.page,
                status=ProposalStatus.PENDING.value,
            )
        )
    for person in result.persons:
        proposals.append(
            ExtractionProposal(
                tenant_id=document.tenant_id,
                document_id=document.id,
                entity_id=document.entity_id,
                kind=ProposalKind.RELATIONSHIP.value,
                payload={
                    "person_name": person.name,
                    "rel_type": person.rel_type,
                    "role_title": person.role_title,
                    # TCKN öneride yalnız ŞİFRELİ tutulur (bkz. seal_national_id); kabul
                    # edilince şifreli varlık kolonuna yazılır. Reddedilen öneri satırla
                    # birlikte kalır — bu yüzden reddedilen öneriler saklama süresine tabidir.
                    **(seal_national_id(person.national_id) if person.national_id else {}),
                },
                confidence=person.confidence,
                evidence_text=person.evidence[:2000] if person.evidence else None,
                page_number=person.page,
                status=ProposalStatus.PENDING.value,
            )
        )

    session.add_all(proposals)
    document.extraction_status = ExtractionStatus.COMPLETED.value
    document.extraction_error = None
    document.extracted_at = datetime.now(UTC)
    document.extraction_engine = engine
    document.page_count = page_count
    await session.flush()
    logger.info(
        "cikarim_tamamlandi",
        document_id=str(document.id),
        proposals=len(proposals),
        engine=engine,
    )
    return proposals


async def mark_extraction_failed(
    session: AsyncSession, document: Document, *, error: str, skipped: bool = False
) -> Document:
    """Çıkarımı başarısız/atlanmış olarak işaretler (belge saklanmaya devam eder)."""
    document.extraction_status = (
        ExtractionStatus.SKIPPED.value if skipped else ExtractionStatus.FAILED.value
    )
    document.extraction_error = error[:2000]
    document.extracted_at = datetime.now(UTC)
    await session.flush()
    return document


RETRYABLE_EXTRACTION_STATUSES = frozenset(
    {ExtractionStatus.FAILED.value, ExtractionStatus.SKIPPED.value}
)


async def requeue_extraction(
    session: AsyncSession,
    document: Document,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    actor_role: str,
) -> Document:
    """Başarısız ya da atlanmış çıkarımı ``pending``'e döndürür (kuyruğa alma çağıranda).

    Neden gerekli: çıkarım görevi idempotenttir, ``pending`` dışındaki belgeye bir daha
    dokunmaz. Docling kurulu değilken yüklenen belge "skipped", motor geçici olarak
    düştüğünde "failed" kalır ve — bu yol olmadan — hiçbir zaman işlenemezdi (aynı dosyayı
    yeniden yüklemek de aynı kanıtı ikinci kez kütüğe sokardı). Önceki durum ve hata
    denetim izine yazılır; öneriler yine insan onayı bekler.
    """
    if document.doc_type not in EXTRACTABLE_TYPES:
        raise DocumentInputError("Bu belge türü için çıkarım yapılmaz.")
    if document.extraction_status not in RETRYABLE_EXTRACTION_STATUSES:
        raise DocumentInputError(
            "Yalnız başarısız ya da atlanmış çıkarım yeniden denenebilir "
            f"(şu anki durum: {document.extraction_status})."
        )
    previous_status = document.extraction_status
    previous_error = (document.extraction_error or "")[:500]
    document.extraction_status = ExtractionStatus.PENDING.value
    document.extraction_error = None
    document.extracted_at = None
    await session.flush()

    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.DOCUMENT_EXTRACTION_RETRY,
        object_type="document",
        object_id=str(document.id),
        payload={"previous_status": previous_status, "previous_error": previous_error},
    )
    return document


async def list_proposals(
    session: AsyncSession,
    *,
    document_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    pending_only: bool = False,
) -> list[ExtractionProposal]:
    """Önerileri listeler (güveni yüksek olan önce)."""
    statement = select(ExtractionProposal)
    if document_id is not None:
        statement = statement.where(ExtractionProposal.document_id == document_id)
    if entity_id is not None:
        statement = statement.where(ExtractionProposal.entity_id == entity_id)
    if pending_only:
        statement = statement.where(ExtractionProposal.status == ProposalStatus.PENDING.value)
    result = await session.scalars(statement.order_by(ExtractionProposal.confidence.desc()))
    return list(result)


async def get_proposal(session: AsyncSession, proposal_id: uuid.UUID) -> ExtractionProposal | None:
    """Tek bir öneriyi döndürür."""
    proposal: ExtractionProposal | None = await session.scalar(
        select(ExtractionProposal).where(ExtractionProposal.id == proposal_id)
    )
    return proposal


async def _resolve_person(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str,
    national_id: str | None,
    link_entity_id: uuid.UUID | None,
    source_ref: str | None,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
    retention_years: int,
) -> Entity:
    """Öneri edilen kişiyi kütükte bulur ya da oluşturur (belirsizlikte kullanıcıya sorar)."""
    if link_entity_id is not None:
        linked = await entity_service.get_entity(session, link_entity_id)
        if linked is None:
            raise DocumentInputError("Bağlanacak varlık bulunamadı.")
        return linked

    fingerprint = blind_index(national_id, domain=NATIONAL_ID_DOMAIN) if national_id else None
    resolution = await resolve_entity(
        session,
        ResolutionQuery(
            name=name,
            schema_type=EntitySchema.PERSON,
            national_id_fingerprint=fingerprint,
        ),
    )
    if resolution.outcome is ResolutionOutcome.MATCHED and resolution.matched is not None:
        return resolution.matched
    if resolution.outcome is ResolutionOutcome.AMBIGUOUS:
        raise AmbiguousProposalError(resolution.candidates)

    entity, _warnings = await entity_service.create_entity(
        session,
        tenant_id=tenant_id,
        name=name,
        schema_type=EntitySchema.PERSON,
        national_id=national_id,
        source_type=SourceType.DOCUMENT,
        source_ref=source_ref,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        retention_years=retention_years,
    )
    return entity


async def accept_proposal(
    session: AsyncSession,
    proposal: ExtractionProposal,
    *,
    actor_user_id: uuid.UUID,
    actor_role: str | None = None,
    link_entity_id: uuid.UUID | None = None,
    note: str | None = None,
    retention_years: int = 5,
) -> ExtractionProposal:
    """Öneriyi kabul eder ve kütüğe uygular; sonucu öneri satırına bağlar.

    Öznitelik önerisi ``document`` kaynaklı bir gözlem olarak yazılır ve beyanla
    çelişiyorsa **tutarsızlık** üretir. Beyanın üstüne yazılmaz (``promote_to_current``
    yalnız beyan yoksa anlamlı olurdu; burada bilinçli olarak yazılmaz) — müşterinin
    ne dediği ile belgenin ne gösterdiği ayrı ayrı durmalıdır.
    """
    if proposal.status != ProposalStatus.PENDING.value:
        raise DocumentInputError("Bu öneri zaten karara bağlanmış.")
    if proposal.entity_id is None:
        raise DocumentInputError("Öneri bir varlığa bağlı değil; önce dosyayı seçin.")

    entity = await entity_service.get_entity(session, proposal.entity_id)
    if entity is None:
        raise DocumentInputError("Önerinin bağlı olduğu varlık bulunamadı.")

    document = await get_document(session, proposal.document_id)
    source_ref = (document.source_ref or document.filename) if document else None
    resulting_entity_id: uuid.UUID | None = None

    if proposal.kind == ProposalKind.ATTRIBUTE.value:
        name = str(proposal.payload.get("name", ""))
        value = str(proposal.payload.get("value", ""))
        if not name or not value:
            raise DocumentInputError("Öneri içeriği eksik.")
        await entity_service.update_entity(
            session,
            entity,
            changes={name: value},
            source_type=SourceType.DOCUMENT,
            source_ref=source_ref,
            document_id=proposal.document_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            promote_to_current=False,
        )
        resulting_entity_id = entity.id
    else:
        person_name = str(proposal.payload.get("person_name", ""))
        if not person_name:
            raise DocumentInputError("Öneride kişi adı yok.")
        raw_rel_type = str(proposal.payload.get("rel_type") or RelationshipType.OFFICER.value)
        rel_type = (
            RelationshipType(raw_rel_type)
            if raw_rel_type in {item.value for item in RelationshipType}
            else RelationshipType.OFFICER
        )
        national_id = proposal_national_id(proposal.payload)
        person = await _resolve_person(
            session,
            tenant_id=proposal.tenant_id,
            name=person_name,
            national_id=national_id,
            link_entity_id=link_entity_id,
            source_ref=source_ref,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            retention_years=retention_years,
        )
        role_title = proposal.payload.get("role_title")
        await entity_service.create_relationship(
            session,
            tenant_id=proposal.tenant_id,
            source_entity_id=person.id,
            target_entity_id=entity.id,
            rel_type=rel_type,
            role_title=str(role_title)[:255] if role_title else None,
            source_type=SourceType.DOCUMENT,
            source_ref=source_ref,
            document_id=proposal.document_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )
        resulting_entity_id = person.id

    proposal.status = ProposalStatus.ACCEPTED.value
    proposal.reviewed_by_user_id = actor_user_id
    proposal.reviewed_at = datetime.now(UTC)
    proposal.review_note = note
    proposal.resulting_entity_id = resulting_entity_id
    await session.flush()

    await audit_service.record_event(
        session,
        tenant_id=proposal.tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.PROPOSAL_ACCEPT,
        object_type="extraction_proposal",
        object_id=str(proposal.id),
        source_ref=source_ref,
        payload={
            "document_id": str(proposal.document_id),
            "entity_id": str(proposal.entity_id),
            "kind": proposal.kind,
            # TCKN denetim izine girmez; yalnız varlığının bilgisi.
            "payload": _redacted_payload(proposal.payload),
            "confidence": proposal.confidence,
            "resulting_entity_id": str(resulting_entity_id) if resulting_entity_id else None,
            "note": note,
        },
    )
    return proposal


def _redacted_payload(payload: dict[str, object]) -> dict[str, object]:
    """Denetim olayına giren öneri içeriğinden kimlik numarasını çıkarır (KVKK)."""
    redacted = dict(payload)
    redacted.pop("national_id_enc", None)
    if redacted.get("national_id"):
        redacted["national_id"] = "***"
    return redacted


async def reject_proposal(
    session: AsyncSession,
    proposal: ExtractionProposal,
    *,
    actor_user_id: uuid.UUID,
    actor_role: str | None = None,
    note: str | None = None,
) -> ExtractionProposal:
    """Öneriyi reddeder (satır silinmez: "belgede vardı ama kabul edilmedi" izi kalır)."""
    if proposal.status != ProposalStatus.PENDING.value:
        raise DocumentInputError("Bu öneri zaten karara bağlanmış.")
    proposal.status = ProposalStatus.REJECTED.value
    proposal.reviewed_by_user_id = actor_user_id
    proposal.reviewed_at = datetime.now(UTC)
    proposal.review_note = note
    await session.flush()

    await audit_service.record_event(
        session,
        tenant_id=proposal.tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.PROPOSAL_REJECT,
        object_type="extraction_proposal",
        object_id=str(proposal.id),
        payload={
            "document_id": str(proposal.document_id),
            "kind": proposal.kind,
            "payload": _redacted_payload(proposal.payload),
            "note": note,
        },
    )
    return proposal


def gazette_source_ref(
    *, issue_number: str | None, issue_date: date | None, url: str | None
) -> str:
    """Ticaret Sicil Gazetesi kaynak referansını tek satıra biçimler (R1: manuel yol).

    E0.3 doğrulaması olmadan otomatik gazete sorgusu yapılmaz; kullanıcı gazete
    sayısını/tarihini ve (varsa) bağlantısını verir, biz kanıt referansı olarak saklarız.
    Bulgunun kaynağı böylece raporda gösterilebilir (Invariant 4).
    """
    parts = ["Ticaret Sicil Gazetesi"]
    if issue_number:
        parts.append(f"Sayı {issue_number}")
    if issue_date:
        parts.append(issue_date.isoformat())
    if url:
        parts.append(url)
    return " · ".join(parts)[:1024]
