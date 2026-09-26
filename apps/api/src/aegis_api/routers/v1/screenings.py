"""/api/v1/screenings — yaptırım/PEP taraması ve eşleşme incelemesi (E1.3).

Yetkilendirme:

- **Tarama çalıştırma / görüntüleme:** owner · compliance_officer · analyst.
  Salt-okunur denetçi (auditor) yalnız görüntüler.
- **Eşleşme kararı (onay/eleme):** owner · compliance_officer. Analist dosyayı hazırlar,
  kararı uyumdan sorumlu rol verir; bu ayrım MASAK denetiminde "kim karar verdi"
  sorusunun cevabını tekilleştirir.

**PII notu (KVKK).** İstekte gelen kimlik numaraları (TCKN/vergi no) yente sorgusunda
bellekte kullanılır, ancak veritabanına **maskeli** yazılır: ``screening.subjects``
JSONB'si alan-düzeyi şifreleme taşımaz. Kimlik numaralarının şifreli saklanması, varlık
kütüğü geldiğinde (E1.4) ``entity`` tablosunun ``EncryptedString`` kolonlarında olur.

**Başarısız koşu 'temiz' değildir.** yente erişilemezse kayıt ``failed`` durumuyla
oluşur ve 200 yerine 502 döner; kaynak yine de sorgulanabilir, çünkü "taramaya çalıştık
ama yapamadık" bilgisi denetim izinin parçasıdır.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_api.dependencies import (
    Principal,
    PrincipalDep,
    SettingsDep,
    TenantSessionDep,
    YenteClientDep,
    require_role,
)
from aegis_api.errors import NotFoundError, ValidationFailedError
from aegis_api.queue import dispatch
from aegis_core.entities import service as entity_service
from aegis_core.models import (
    MatchCandidate,
    Role,
    SanctionsDataset,
    Screening,
    ScreeningStatus,
    SubjectRole,
)
from aegis_core.queueing import TASK_SCREENING_RUN
from aegis_core.screening import service as screening_service
from aegis_core.screening.normalization import SubjectType
from aegis_core.screening.service import ScreeningInputError, ScreeningSubject
from aegis_core.screening.thresholds import (
    SCREENING_THRESHOLD_SETTING_KEY,
    MatchDecision,
    ScreeningThresholds,
)
from aegis_core.services import tenant_settings as settings_service

router = APIRouter(prefix="/screenings", tags=["screenings"])

RequireScreeningRun = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.ANALYST))
]
RequireMatchDecision = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER))
]

# İsteğe kabul edilen FtM kimlik özellikleri — serbest özellik enjeksiyonu engellenir.
ALLOWED_IDENTIFIER_PROPERTIES = frozenset(
    {"taxNumber", "registrationNumber", "idNumber", "leiCode", "innCode", "birthDate"}
)


def _mask(value: str) -> str:
    """Kimlik numarasını saklamak için maskeler (son 4 hane görünür).

    Denetim izi "vergi numarasıyla tarandı" diyebilmeli ama numaranın kendisini
    şifresiz tutmamalıdır (KVKK, Invariant 3).
    """
    stripped = value.strip()
    if len(stripped) <= 4:
        return "*" * len(stripped)
    return "*" * (len(stripped) - 4) + stripped[-4:]


# ── Şemalar ──────────────────────────────────────────────────────────────────


class SubjectRequest(BaseModel):
    """Taranacak bir özne (şirket, yönetici ya da gerçek faydalanıcı)."""

    name: str = Field(min_length=1, max_length=512)
    subject_type: Literal["person", "company"] = "company"
    role: Literal["self", "officer", "ubo", "shareholder"] = "self"
    country: str | None = Field(default=None, max_length=8)
    identifiers: dict[str, str] = Field(default_factory=dict)


class ScreeningCreateRequest(BaseModel):
    """Tarama koşusu isteği: birincil özne + (varsa) ilgili kişiler."""

    subject: SubjectRequest
    related_subjects: list[SubjectRequest] = Field(default_factory=list)
    entity_id: uuid.UUID | None = None
    """E1.4'te varlık kütüğüne bağlamak için (şimdilik serbest referans)."""


class MatchCandidateResponse(BaseModel):
    """Bir aday eşleşme — skor, "neden eşleşti" ve karar durumu."""

    id: uuid.UUID
    subject_key: str
    subject_name: str
    subject_role: str
    external_id: str
    caption: str
    schema_type: str
    score: float
    band: str
    decision: str
    decided_automatically: bool
    flagged: bool
    datasets: list[str]
    topics: list[str]
    countries: list[str]
    features: dict[str, Any]
    properties: dict[str, Any]
    source_url: str | None
    review_note: str | None
    reviewed_at: datetime | None


class ScreeningSummaryResponse(BaseModel):
    """Karar dağılımı özeti."""

    total: int
    pending: int
    confirmed: int
    dismissed: int
    flagged: int
    sanction_hits: int
    pep_hits: int
    flagged_pending: int
    """Yüksek skorlu ve hâlâ karar bekleyen aday sayısı ("acil inceleme" uyarısının ölçüsü)."""


class ScreeningResponse(BaseModel):
    """Tarama koşusu (liste görünümü)."""

    id: uuid.UUID
    status: str
    subject_name: str
    subject_normalized: str
    subject_type: str
    subject_country: str | None
    subjects: list[dict[str, Any]]
    dataset: str
    dataset_versions: dict[str, Any]
    algorithm: str
    thresholds: dict[str, Any]
    candidate_count: int
    duration_ms: int | None
    error: str | None
    entity_id: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None
    summary: ScreeningSummaryResponse


class ScreeningDetailResponse(ScreeningResponse):
    """Tarama koşusu + adayları (detay görünümü)."""

    candidates: list[MatchCandidateResponse]


class ScreeningListResponse(BaseModel):
    """Sayfalanmış tarama listesi."""

    total: int
    items: list[ScreeningResponse]


class MatchDecisionRequest(BaseModel):
    """Eşleşme kararı: onayla ya da gerekçesiyle ele."""

    decision: Literal["confirmed", "dismissed"]
    note: str | None = Field(default=None, max_length=2000)


class DatasetStateResponse(BaseModel):
    """Bir yaptırım veri kümesinin tazelik durumu."""

    name: str
    title: str | None
    version: str | None
    last_export_at: datetime | None
    entity_count: int | None
    checked_at: datetime
    age_hours: float | None
    stale: bool


class DatasetFreshnessResponse(BaseModel):
    """Veri tazeliği raporu — bayat veri kümesi varsa ``stale`` işaretlenir."""

    staleness_threshold_hours: int
    any_stale: bool
    datasets: list[DatasetStateResponse]


# ── Dönüştürücüler ───────────────────────────────────────────────────────────


def _candidate_response(candidate: MatchCandidate) -> MatchCandidateResponse:
    return MatchCandidateResponse(
        id=candidate.id,
        subject_key=candidate.subject_key,
        subject_name=candidate.subject_name,
        subject_role=candidate.subject_role,
        external_id=candidate.external_id,
        caption=candidate.caption,
        schema_type=candidate.schema_type,
        score=candidate.score,
        band=candidate.band,
        decision=candidate.decision,
        decided_automatically=candidate.decided_automatically,
        flagged=candidate.flagged,
        datasets=list(candidate.datasets),
        topics=list(candidate.topics),
        countries=list(candidate.countries),
        features=dict(candidate.features),
        properties=dict(candidate.properties),
        source_url=candidate.source_url,
        review_note=candidate.review_note,
        reviewed_at=candidate.reviewed_at,
    )


def _screening_response(
    screening: Screening, summary: screening_service.ScreeningSummary
) -> ScreeningResponse:
    return ScreeningResponse(
        id=screening.id,
        status=screening.status,
        subject_name=screening.subject_name,
        subject_normalized=screening.subject_normalized,
        subject_type=screening.subject_type,
        subject_country=screening.subject_country,
        subjects=list(screening.subjects),
        dataset=screening.dataset,
        dataset_versions=dict(screening.dataset_versions),
        algorithm=screening.algorithm,
        thresholds=dict(screening.thresholds),
        candidate_count=screening.candidate_count,
        duration_ms=screening.duration_ms,
        error=screening.error,
        entity_id=screening.entity_id,
        created_at=screening.created_at,
        completed_at=screening.completed_at,
        summary=ScreeningSummaryResponse(
            total=summary.total,
            pending=summary.pending,
            confirmed=summary.confirmed,
            dismissed=summary.dismissed,
            flagged=summary.flagged,
            sanction_hits=summary.sanction_hits,
            pep_hits=summary.pep_hits,
            flagged_pending=summary.flagged_pending,
        ),
    )


def _to_subject(request: SubjectRequest, *, force_self: bool) -> ScreeningSubject:
    """İstek şemasını servis öznesine çevirir (kimlik özellikleri doğrulanır)."""
    unknown = sorted(set(request.identifiers) - ALLOWED_IDENTIFIER_PROPERTIES)
    if unknown:
        raise ValidationFailedError(
            "Tanınmayan kimlik alanı: " + ", ".join(unknown),
            details=[{"allowed": sorted(ALLOWED_IDENTIFIER_PROPERTIES)}],
        )
    return ScreeningSubject(
        name=request.name,
        subject_type=SubjectType(request.subject_type),
        role=SubjectRole.SELF if force_self else SubjectRole(request.role),
        country=request.country,
        identifiers=dict(request.identifiers),
    )


async def _load_thresholds(session: AsyncSession) -> ScreeningThresholds:
    """Kiracının eşik bandını okur; bozuk yapılandırmada taramayı reddeder.

    Sessizce varsayılana düşmek tehlikelidir: hatalı bir ``auto_dismiss_below``
    gerçek bir yaptırım eşleşmesini fark ettirmeden eleyebilirdi.
    """
    row = await settings_service.get_setting(session, SCREENING_THRESHOLD_SETTING_KEY)
    try:
        return ScreeningThresholds.from_mapping(row.value if row else None)
    except (ValueError, TypeError) as exc:
        raise ValidationFailedError(
            f"'{SCREENING_THRESHOLD_SETTING_KEY}' ayarı geçersiz: {exc}"
        ) from exc


# ── Uçlar ────────────────────────────────────────────────────────────────────
# NOT: /datasets, /{screening_id}'den ÖNCE tanımlanır (yol çakışmasını önler).


@router.get("/datasets", response_model=DatasetFreshnessResponse)
async def dataset_freshness(
    _principal: PrincipalDep, session: TenantSessionDep, settings: SettingsDep
) -> DatasetFreshnessResponse:
    """Yaptırım veri kümelerinin tazeliğini döndürür (bayatlık > 24 sa işaretlenir).

    Veri bayatsa tarama sonucu "temiz" görünse bile güvenilmezdir; bu uç, arayüzün
    kullanıcıyı uyarabilmesi içindir.
    """
    rows = list(await session.scalars(select(SanctionsDataset).order_by(SanctionsDataset.name)))
    threshold = settings.sanctions_staleness_hours
    items: list[DatasetStateResponse] = []
    any_stale = False
    for row in rows:
        age: float | None = None
        if row.last_export_at is not None:
            elapsed = datetime.now(UTC) - row.last_export_at
            age = elapsed.total_seconds() / 3600
        # Sürümü hiç bilinmeyen küme de bayat sayılır: "bilmiyoruz" ≠ "taze".
        stale = age is None or age > threshold
        any_stale = any_stale or stale
        items.append(
            DatasetStateResponse(
                name=row.name,
                title=row.title,
                version=row.version,
                last_export_at=row.last_export_at,
                entity_count=row.entity_count,
                checked_at=row.checked_at,
                age_hours=age,
                stale=stale,
            )
        )
    return DatasetFreshnessResponse(
        staleness_threshold_hours=threshold,
        # Hiç kayıt yoksa senkron job'ı henüz koşmamıştır → bayat kabul edilir.
        any_stale=any_stale or not items,
        datasets=items,
    )


@router.post("", response_model=ScreeningDetailResponse, status_code=status.HTTP_201_CREATED)
async def run_screening(
    body: ScreeningCreateRequest,
    principal: RequireScreeningRun,
    session: TenantSessionDep,
    settings: SettingsDep,
    yente: YenteClientDep,
    response: Response,
) -> ScreeningDetailResponse:
    """Tarama çalıştırır (senkron yol) ve sonuçları adaylarıyla döndürür.

    Özne sayısı ``screening_sync_subject_limit``i aşarsa istek reddedilir: derin koşu
    Celery'ye aittir (``POST /screenings/deep``), senkron yol NFR'yi korumalıdır.
    """
    thresholds = await _load_thresholds(session)
    subjects = [_to_subject(body.subject, force_self=True)]
    subjects += [_to_subject(item, force_self=False) for item in body.related_subjects]
    if len(subjects) > settings.screening_sync_subject_limit:
        raise ValidationFailedError(
            f"Senkron tarama en fazla {settings.screening_sync_subject_limit} özne alır; "
            "daha fazlası için derin koşuyu (/screenings/deep) kullanın."
        )

    try:
        screening = await screening_service.run_screening(
            session,
            yente,
            tenant_id=principal.tenant_id,
            subjects=subjects,
            thresholds=thresholds,
            dataset=settings.yente_dataset,
            algorithm=settings.yente_algorithm,
            requested_by_user_id=principal.user_id,
            requested_by_role=principal.role.value,
            entity_id=body.entity_id,
            retention_years=settings.document_retention_years,
            limit=settings.screening_candidate_limit,
        )
    except ScreeningInputError as exc:
        raise ValidationFailedError(str(exc)) from exc

    _mask_persisted_identifiers(screening)
    await session.flush()

    summary = await screening_service.summarize_screening(session, screening.id)
    if screening.status == "failed":
        # Kayıt oluştu (denetim izi için) ama tarama YAPILAMADI — 2xx yanıltıcı olurdu.
        response.status_code = status.HTTP_502_BAD_GATEWAY
    candidates = await screening_service.list_candidates(session, screening.id)
    return ScreeningDetailResponse(
        **_screening_response(screening, summary).model_dump(),
        candidates=[_candidate_response(candidate) for candidate in candidates],
    )


def _mask_persisted_identifiers(screening: Screening) -> None:
    """Kalıcılaşan özne anlık görüntüsündeki kimlik numaralarını maskeler (KVKK).

    Sorgu zaten yapıldı; saklanan izde numaranın kendisi değil, hangi tür kimlikle
    tarandığı ve son 4 hanesi kalır.
    """
    masked_subjects: list[dict[str, Any]] = []
    for snapshot in screening.subjects:
        copied = dict(snapshot)
        identifiers = copied.get("identifiers")
        if isinstance(identifiers, dict):
            copied["identifiers"] = {key: _mask(str(value)) for key, value in identifiers.items()}
        masked_subjects.append(copied)
    screening.subjects = masked_subjects


@router.get("", response_model=ScreeningListResponse)
async def list_screenings(
    _principal: PrincipalDep,
    session: TenantSessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ScreeningListResponse:
    """Kiracının taramalarını en yeniden eskiye listeler (RLS ile sınırlı)."""
    screenings = await screening_service.list_screenings(session, limit=limit, offset=offset)
    total = await screening_service.count_screenings(session)
    items: list[ScreeningResponse] = []
    for screening in screenings:
        summary = await screening_service.summarize_screening(session, screening.id)
        items.append(_screening_response(screening, summary))
    return ScreeningListResponse(total=total, items=items)


@router.get("/{screening_id}", response_model=ScreeningDetailResponse)
async def get_screening(
    screening_id: uuid.UUID, _principal: PrincipalDep, session: TenantSessionDep
) -> ScreeningDetailResponse:
    """Tek bir taramayı adaylarıyla döndürür."""
    screening = await screening_service.get_screening(session, screening_id)
    if screening is None:
        raise NotFoundError("Tarama bulunamadı.")
    summary = await screening_service.summarize_screening(session, screening.id)
    candidates = await screening_service.list_candidates(session, screening.id)
    return ScreeningDetailResponse(
        **_screening_response(screening, summary).model_dump(),
        candidates=[_candidate_response(candidate) for candidate in candidates],
    )


@router.post(
    "/{screening_id}/candidates/{candidate_id}/decision",
    response_model=MatchCandidateResponse,
)
async def decide_candidate(
    screening_id: uuid.UUID,
    candidate_id: uuid.UUID,
    body: MatchDecisionRequest,
    principal: RequireMatchDecision,
    session: TenantSessionDep,
) -> MatchCandidateResponse:
    """Bir aday eşleşmeyi onaylar ya da gerekçesiyle eler (HITL).

    Her karar tam olarak bir denetim olayı yazar (Invariant 2) ve önceki kararı
    payload'ında taşır; karar değiştirilse bile geçmiş izde durur.
    """
    candidate = await screening_service.get_candidate(
        session, screening_id=screening_id, candidate_id=candidate_id
    )
    if candidate is None:
        raise NotFoundError("Eşleşme adayı bulunamadı.")
    try:
        updated = await screening_service.decide_candidate(
            session,
            candidate,
            decision=MatchDecision(body.decision),
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
            note=body.note,
        )
    except ValueError as exc:
        raise ValidationFailedError(str(exc)) from exc
    return _candidate_response(updated)


@router.post(
    "/from-entity/{entity_id}",
    response_model=ScreeningDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def screen_entity(
    entity_id: uuid.UUID,
    principal: RequireScreeningRun,
    session: TenantSessionDep,
    settings: SettingsDep,
    yente: YenteClientDep,
    response: Response,
) -> ScreeningDetailResponse:
    """Kütükteki bir varlığı **bağlı kişileriyle birlikte** tarar (E1.3 × E1.4).

    ROADMAP E1.3: *"yente match (entity + directors/UBOs)"*. Özneler kütükten okunur:
    şirketin kendisi + ona bağlı yönetici/ortak/UBO kayıtları. Böylece kullanıcı adları
    yeniden yazmaz ve tarama, dosyada kayıtlı olanla birebir aynı kişiler üzerinde koşar.

    Kimlik numaraları kütükte şifrelidir ve buradan yente'ye **gönderilmez**: eşleştirme
    ad üzerinden yapılır (yaptırım listeleri TCKN taşımaz).
    """
    entity = await entity_service.get_entity(session, entity_id)
    if entity is None:
        raise NotFoundError("Varlık bulunamadı.")

    thresholds = await _load_thresholds(session)
    pairs = await entity_service.screening_subjects_for(session, entity)
    subjects = [
        ScreeningSubject(
            name=item.name,
            subject_type=(
                SubjectType.PERSON if item.schema_type == "Person" else SubjectType.COMPANY
            ),
            role=SubjectRole(role)
            if role in {r.value for r in SubjectRole}
            else SubjectRole.OFFICER,
            country=item.country,
            identifiers=(
                {"taxNumber": item.tax_number} if item.tax_number and role == "self" else {}
            ),
        )
        for item, role in pairs
    ]
    if len(subjects) > settings.screening_sync_subject_limit:
        raise ValidationFailedError(
            f"Bu dosyada {len(subjects)} özne var; senkron tarama en fazla "
            f"{settings.screening_sync_subject_limit} alır. Derin koşuyu kullanın."
        )

    try:
        screening = await screening_service.run_screening(
            session,
            yente,
            tenant_id=principal.tenant_id,
            subjects=subjects,
            thresholds=thresholds,
            dataset=settings.yente_dataset,
            algorithm=settings.yente_algorithm,
            requested_by_user_id=principal.user_id,
            requested_by_role=principal.role.value,
            entity_id=entity.id,
            retention_years=settings.document_retention_years,
            limit=settings.screening_candidate_limit,
        )
    except ScreeningInputError as exc:
        raise ValidationFailedError(str(exc)) from exc

    _mask_persisted_identifiers(screening)
    await session.flush()
    summary = await screening_service.summarize_screening(session, screening.id)
    if screening.status == "failed":
        response.status_code = status.HTTP_502_BAD_GATEWAY
    candidates = await screening_service.list_candidates(session, screening.id)
    return ScreeningDetailResponse(
        **_screening_response(screening, summary).model_dump(),
        candidates=[_candidate_response(candidate) for candidate in candidates],
    )


@router.post("/deep", response_model=ScreeningResponse, status_code=status.HTTP_202_ACCEPTED)
async def queue_deep_screening(
    body: ScreeningCreateRequest,
    principal: RequireScreeningRun,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> ScreeningResponse:
    """Çok özneli (derin) taramayı kuyruğa alır; sonuç ``GET /screenings/{id}`` ile alınır.

    Kimlik numaraları göreve **mesajla** geçirilir, veritabanına maskeli yazılır: derin
    koşu da senkron koşuyla aynı KVKK kuralına uyar.
    """
    thresholds = await _load_thresholds(session)
    subjects = [_to_subject(body.subject, force_self=True)]
    subjects += [_to_subject(item, force_self=False) for item in body.related_subjects]

    try:
        screening, _queries, _snapshots = await screening_service.create_screening(
            session,
            tenant_id=principal.tenant_id,
            subjects=subjects,
            thresholds=thresholds,
            dataset=settings.yente_dataset,
            algorithm=settings.yente_algorithm,
            requested_by_user_id=principal.user_id,
            entity_id=body.entity_id,
            retention_years=settings.document_retention_years,
            status=ScreeningStatus.QUEUED,
        )
    except ScreeningInputError as exc:
        raise ValidationFailedError(str(exc)) from exc

    identifiers_by_key = {
        str(snapshot["key"]): dict(snapshot.get("identifiers") or {})
        for snapshot in screening.subjects
    }
    _mask_persisted_identifiers(screening)
    await session.flush()

    dispatch(
        TASK_SCREENING_RUN,
        kwargs={
            "tenant_id": str(principal.tenant_id),
            "screening_id": str(screening.id),
            "identifiers": identifiers_by_key,
            "actor_role": principal.role.value,
        },
        redis_url=settings.redis_url,
    )
    summary = await screening_service.summarize_screening(session, screening.id)
    return _screening_response(screening, summary)
