"""Tarama akışı: normalize → yente ile eşleştir → kalıcılaştır → denetle (E1.3).

Akışın değişmezleri:

- **Her koşu bir denetim olayı yazar** (Invariant 2), başarısız koşu dahil. "Tarayamadık"
  bilgisi, "temiz çıktı" bilgisinden farklıdır ve izde ayrı görünmelidir.
- **Hiçbir aday silinmez.** Eşik bandının otomatik elediği adaylar da saklanır; dosya
  raporu (E1.5) "gerekçesiyle elenen eşleşmeler"i göstermek zorundadır.
- **Otomatik onay yoktur.** Yüksek skorlu aday bile ``pending`` kalır, yalnız
  ``flagged`` olur; onay bir insan kararıdır (Ürün Planı §3.3: karar desteği).
- **Provenans koşu anında dondurulur:** veri kümesi sürümleri ve eşikler ``screening``
  satırına yazılır. Sonradan eşik değişirse eski koşu yeniden yorumlanmaz.
- **Motor hatası sessizce 'temiz' olmaz:** yente erişilemezse koşu ``failed`` durumuyla
  kalıcılaşır ve öyle raporlanır.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from aegis_core.logging import get_logger
from aegis_core.models import (
    AuditAction,
    MatchCandidate,
    SanctionsDataset,
    Screening,
    ScreeningStatus,
    SubjectRole,
)
from aegis_core.screening.normalization import SubjectType, name_variants, normalize_name
from aegis_core.screening.thresholds import (
    MatchDecision,
    ScreeningThresholds,
)
from aegis_core.screening.yente import (
    SCHEMA_COMPANY,
    SCHEMA_PERSON,
    MatchQuery,
    SyncYenteClient,
    YenteClient,
    YenteError,
    YenteMatch,
)
from aegis_core.services import audit as audit_service

logger = get_logger("aegis.screening.service")

# Bir koşuda taranabilecek azami özne sayısı (şirket + yöneticiler/UBO'lar).
MAX_SUBJECTS_PER_RUN = 50
# Özne başına yente'den istenen azami aday sayısı.
DEFAULT_CANDIDATE_LIMIT = 10


class ScreeningInputError(ValueError):
    """Tarama girdisi geçersiz (boş ad, çok fazla özne …)."""


@dataclass(frozen=True)
class ScreeningSubject:
    """Taranacak tek bir özne (şirketin kendisi, bir yöneticisi ya da bir UBO'su)."""

    name: str
    subject_type: SubjectType = SubjectType.COMPANY
    role: SubjectRole = SubjectRole.SELF
    country: str | None = None
    identifiers: dict[str, str] = field(default_factory=dict)
    """FtM özellik adı → değer (``taxNumber``, ``registrationNumber``, ``idNumber``)."""


@dataclass(frozen=True)
class ScreeningSummary:
    """Bir koşunun karar dağılımı — risk özetinin (E1.5) girdisi."""

    total: int
    pending: int
    confirmed: int
    dismissed: int
    flagged: int
    sanction_hits: int
    pep_hits: int

    @property
    def needs_review(self) -> bool:
        """İnsan incelemesi bekleyen aday var mı."""
        return self.pending > 0


def _schema_for(subject_type: SubjectType) -> str:
    return SCHEMA_PERSON if subject_type is SubjectType.PERSON else SCHEMA_COMPANY


def _build_queries(
    subjects: Sequence[ScreeningSubject],
) -> tuple[list[MatchQuery], list[dict[str, Any]]]:
    """Öznelerden yente sorgularını ve kalıcılaşacak özne anlık görüntülerini üretir.

    Sorgu anahtarı (``s0``, ``s1`` …) yanıtı özneye geri bağlar; aynı anahtar aday
    satırlarına da yazılır, böylece "bu eşleşme hangi kişiden geldi" sorusu cevaplanır.
    """
    queries: list[MatchQuery] = []
    snapshots: list[dict[str, Any]] = []
    for index, subject in enumerate(subjects):
        normalized = normalize_name(subject.name, subject.subject_type)
        if normalized.is_empty:
            raise ScreeningInputError(
                f"'{subject.name}' normalizasyondan sonra boşaldı — taranacak ad yok."
            )
        key = f"s{index}"
        queries.append(
            MatchQuery(
                key=key,
                schema=_schema_for(subject.subject_type),
                names=name_variants(normalized),
                country=subject.country,
                identifiers=dict(subject.identifiers),
            )
        )
        snapshots.append(
            {
                "key": key,
                "name": subject.name,
                "normalized": normalized.canonical,
                "ascii": normalized.ascii,
                "stripped": list(normalized.stripped),
                "type": subject.subject_type.value,
                "role": subject.role.value,
                "country": subject.country,
                "identifiers": dict(subject.identifiers),
            }
        )
    return queries, snapshots


def _validate_subjects(subjects: Sequence[ScreeningSubject]) -> None:
    if not subjects:
        raise ScreeningInputError("En az bir özne gereklidir.")
    if len(subjects) > MAX_SUBJECTS_PER_RUN:
        raise ScreeningInputError(
            f"Tek koşuda en fazla {MAX_SUBJECTS_PER_RUN} özne taranabilir "
            f"(verilen: {len(subjects)})."
        )
    for subject in subjects:
        if not subject.name.strip():
            raise ScreeningInputError("Özne adı boş olamaz.")


def _candidate_from_match(
    *,
    tenant_id: uuid.UUID,
    screening_id: uuid.UUID,
    snapshot: dict[str, Any],
    match: YenteMatch,
    thresholds: ScreeningThresholds,
) -> MatchCandidate:
    """Bir yente adayını, eşik bandının verdiği başlangıç kararıyla satıra çevirir."""
    disposition = thresholds.disposition(match.score)
    return MatchCandidate(
        tenant_id=tenant_id,
        screening_id=screening_id,
        subject_key=str(snapshot["key"]),
        subject_name=str(snapshot["name"])[:512],
        subject_role=str(snapshot["role"]),
        external_id=match.entity_id[:255],
        caption=match.caption[:512],
        schema_type=match.schema[:64],
        score=match.score,
        engine_matched=match.matched,
        datasets=list(match.datasets),
        topics=list(match.topics),
        countries=list(match.countries),
        features=dict(match.features),
        properties=dict(match.properties),
        source_url=match.source_url[:1024] if match.source_url else None,
        band=disposition.band.value,
        decision=disposition.decision.value,
        decided_automatically=disposition.auto,
        flagged=disposition.flagged,
        review_note=("Eşik altında otomatik elendi." if disposition.auto else None),
        reviewed_at=datetime.now(UTC) if disposition.auto else None,
    )


async def load_dataset_versions(session: AsyncSession) -> dict[str, Any]:
    """Kayıtlı veri kümesi sürümlerini döndürür (koşuya provenans olarak gömülür).

    Katalog için yente'ye ek bir HTTP çağrısı yapılmaz: günlük senkron job'ı
    ``sanctions_dataset`` tablosunu zaten günceller. Bu, senkron yolun gecikmesini
    (NFR: < 30 sn) motorun katalog cevabına bağımlı olmaktan kurtarır.
    """
    rows = list(await session.scalars(select(SanctionsDataset)))
    return {
        row.name: {
            "version": row.version,
            "last_export_at": row.last_export_at.isoformat() if row.last_export_at else None,
        }
        for row in rows
    }


async def summarize_screening(session: AsyncSession, screening_id: uuid.UUID) -> ScreeningSummary:
    """Bir koşunun karar dağılımını hesaplar (RLS ile kiracıya sınırlı)."""
    rows = list(
        await session.execute(
            select(
                MatchCandidate.decision,
                MatchCandidate.flagged,
                MatchCandidate.topics,
            ).where(MatchCandidate.screening_id == screening_id)
        )
    )
    counts = {decision.value: 0 for decision in MatchDecision}
    flagged = 0
    sanction_hits = 0
    pep_hits = 0
    for decision, is_flagged, topics in rows:
        counts[decision] = counts.get(decision, 0) + 1
        if is_flagged:
            flagged += 1
        topic_list = topics if isinstance(topics, list) else []
        if decision != MatchDecision.DISMISSED.value:
            if any(str(topic).startswith("sanction") for topic in topic_list):
                sanction_hits += 1
            if any(str(topic).startswith("role.pep") for topic in topic_list):
                pep_hits += 1
    return ScreeningSummary(
        total=len(rows),
        pending=counts.get(MatchDecision.PENDING.value, 0),
        confirmed=counts.get(MatchDecision.CONFIRMED.value, 0),
        dismissed=counts.get(MatchDecision.DISMISSED.value, 0),
        flagged=flagged,
        sanction_hits=sanction_hits,
        pep_hits=pep_hits,
    )


async def create_screening(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    subjects: Sequence[ScreeningSubject],
    thresholds: ScreeningThresholds,
    dataset: str,
    algorithm: str,
    requested_by_user_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    retention_years: int = 5,
    status: ScreeningStatus = ScreeningStatus.RUNNING,
) -> tuple[Screening, list[MatchQuery], list[dict[str, Any]]]:
    """Tarama satırını (henüz sonuçsuz) oluşturur ve sorguları hazırlar.

    Koşunun kendisi başarısız olsa bile kayıt kalır — "ne zaman neyi taramaya çalıştık"
    denetim izinin parçasıdır.
    """
    _validate_subjects(subjects)
    queries, snapshots = _build_queries(subjects)
    primary = subjects[0]
    primary_snapshot = snapshots[0]

    screening = Screening(
        tenant_id=tenant_id,
        subject_type=primary.subject_type.value,
        subject_name=primary.name[:512],
        subject_normalized=str(primary_snapshot["normalized"])[:512],
        subject_country=primary.country,
        subjects=snapshots,
        entity_id=entity_id,
        dataset=dataset,
        dataset_versions=await load_dataset_versions(session),
        algorithm=algorithm,
        thresholds=thresholds.to_mapping(),
        status=status.value,
        requested_by_user_id=requested_by_user_id,
        started_at=datetime.now(UTC),
        retention_until=datetime.now(UTC) + timedelta(days=365 * retention_years),
    )
    session.add(screening)
    await session.flush()
    return screening, queries, snapshots


async def _finalize(
    session: AsyncSession,
    screening: Screening,
    *,
    results: dict[str, list[YenteMatch]] | None,
    snapshots: Sequence[dict[str, Any]],
    thresholds: ScreeningThresholds,
    started_monotonic: float,
    actor_role: str | None = None,
    error: str | None = None,
) -> Screening:
    """Sonuçları kalıcılaştırır, koşuyu kapatır ve denetim olayını yazar."""
    candidate_count = 0
    if results is not None:
        by_key = {str(snapshot["key"]): snapshot for snapshot in snapshots}
        for key, matches in results.items():
            snapshot = by_key.get(key)
            if snapshot is None:
                # Motor tanımadığımız bir anahtar döndürdü: yut ama izle.
                logger.warning("yente_bilinmeyen_sorgu_anahtari", key=key)
                continue
            for match in matches:
                session.add(
                    _candidate_from_match(
                        tenant_id=screening.tenant_id,
                        screening_id=screening.id,
                        snapshot=snapshot,
                        match=match,
                        thresholds=thresholds,
                    )
                )
                candidate_count += 1

    screening.candidate_count = candidate_count
    screening.completed_at = datetime.now(UTC)
    screening.duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    screening.status = ScreeningStatus.FAILED.value if error else ScreeningStatus.COMPLETED.value
    screening.error = error
    await session.flush()

    summary = await summarize_screening(session, screening.id)
    await audit_service.record_event(
        session,
        tenant_id=screening.tenant_id,
        actor_user_id=screening.requested_by_user_id,
        actor_role=actor_role,
        action=AuditAction.SCREENING_RUN,
        object_type="screening",
        object_id=str(screening.id),
        source_ref=f"yente:{screening.dataset}",
        payload={
            "status": screening.status,
            "subject_count": len(snapshots),
            "subject": screening.subject_normalized,
            "candidate_count": candidate_count,
            "pending": summary.pending,
            "dismissed": summary.dismissed,
            "flagged": summary.flagged,
            "sanction_hits": summary.sanction_hits,
            "pep_hits": summary.pep_hits,
            "duration_ms": screening.duration_ms,
            "algorithm": screening.algorithm,
            "thresholds": screening.thresholds,
            "dataset_versions": screening.dataset_versions,
            "error": error,
        },
    )
    logger.info(
        "screening_tamamlandi",
        screening_id=str(screening.id),
        status=screening.status,
        candidates=candidate_count,
        duration_ms=screening.duration_ms,
    )
    return screening


async def run_screening(
    session: AsyncSession,
    client: YenteClient,
    *,
    tenant_id: uuid.UUID,
    subjects: Sequence[ScreeningSubject],
    thresholds: ScreeningThresholds,
    dataset: str,
    algorithm: str,
    requested_by_user_id: uuid.UUID | None = None,
    requested_by_role: str | None = None,
    entity_id: uuid.UUID | None = None,
    retention_years: int = 5,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> Screening:
    """Bir taramayı uçtan uca çalıştırır (senkron yol; NFR < 30 sn).

    Motor hatası istisna olarak dışarı sızmaz: koşu ``failed`` durumuyla kalıcılaşır,
    denetim olayı yazılır ve çağıran duruma bakarak kullanıcıyı uyarır. Böylece
    "tarama denendi ama yapılamadı" bilgisi kaybolmaz.
    """
    started = time.monotonic()
    screening, queries, snapshots = await create_screening(
        session,
        tenant_id=tenant_id,
        subjects=subjects,
        thresholds=thresholds,
        dataset=dataset,
        algorithm=algorithm,
        requested_by_user_id=requested_by_user_id,
        entity_id=entity_id,
        retention_years=retention_years,
    )
    try:
        results = await client.match(
            queries,
            cutoff=thresholds.candidate_cutoff,
            threshold=thresholds.auto_flag_at,
            limit=limit,
        )
    except YenteError as exc:
        logger.error("screening_motor_hatasi", screening_id=str(screening.id), error=str(exc))
        return await _finalize(
            session,
            screening,
            results=None,
            snapshots=snapshots,
            thresholds=thresholds,
            started_monotonic=started,
            actor_role=requested_by_role,
            error=str(exc),
        )
    return await _finalize(
        session,
        screening,
        results=results,
        snapshots=snapshots,
        thresholds=thresholds,
        started_monotonic=started,
        actor_role=requested_by_role,
        error=None,
    )


def queries_from_snapshots(
    snapshots: Sequence[dict[str, Any]],
    identifiers: dict[str, dict[str, str]] | None = None,
) -> list[MatchQuery]:
    """Kalıcılaşmış özne anlık görüntülerinden yente sorgularını yeniden kurar.

    Kuyruğa alınmış (derin) koşular içindir: worker, taramanın kaydedilmiş öznelerini
    okur. Kimlik numaraları veritabanında **maskeli** durduğundan, gerçek değerler
    göreve mesajla geçirilir ve burada ``identifiers`` ile geri bağlanır.
    """
    supplied = identifiers or {}
    queries: list[MatchQuery] = []
    for snapshot in snapshots:
        key = str(snapshot["key"])
        subject_type = SubjectType(str(snapshot.get("type", SubjectType.COMPANY.value)))
        normalized = normalize_name(str(snapshot["name"]), subject_type)
        if normalized.is_empty:
            continue
        country = snapshot.get("country")
        queries.append(
            MatchQuery(
                key=key,
                schema=_schema_for(subject_type),
                names=name_variants(normalized),
                country=str(country) if country else None,
                identifiers=supplied.get(key, {}),
            )
        )
    return queries


async def run_existing_screening(
    session: AsyncSession,
    client: YenteClient,
    screening: Screening,
    *,
    identifiers: dict[str, dict[str, str]] | None = None,
    actor_role: str | None = None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> Screening:
    """Kuyruğa alınmış bir taramayı çalıştırır (derin koşu, Celery worker'ından).

    Eşikler ve veri kümesi, koşu **oluşturulduğu andaki** hâliyle kullanılır: kayıt
    zaten o anlık görüntüyü taşır, arada eşik değişse bile koşu tutarlı kalır.
    """
    started = time.monotonic()
    thresholds = ScreeningThresholds.from_mapping(dict(screening.thresholds))
    snapshots = list(screening.subjects)
    queries = queries_from_snapshots(snapshots, identifiers)

    screening.status = ScreeningStatus.RUNNING.value
    screening.started_at = datetime.now(UTC)
    await session.flush()

    try:
        results = await client.match(
            queries,
            cutoff=thresholds.candidate_cutoff,
            threshold=thresholds.auto_flag_at,
            limit=limit,
        )
    except YenteError as exc:
        logger.error("derin_tarama_motor_hatasi", screening_id=str(screening.id), error=str(exc))
        return await _finalize(
            session,
            screening,
            results=None,
            snapshots=snapshots,
            thresholds=thresholds,
            started_monotonic=started,
            actor_role=actor_role,
            error=str(exc),
        )
    return await _finalize(
        session,
        screening,
        results=results,
        snapshots=snapshots,
        thresholds=thresholds,
        started_monotonic=started,
        actor_role=actor_role,
        error=None,
    )


async def get_screening(session: AsyncSession, screening_id: uuid.UUID) -> Screening | None:
    """Tek bir taramayı adaylarıyla döndürür (RLS ile kiracıya sınırlı)."""
    screening: Screening | None = await session.scalar(
        select(Screening).where(Screening.id == screening_id)
    )
    return screening


async def list_screenings(
    session: AsyncSession, *, limit: int = 50, offset: int = 0
) -> list[Screening]:
    """Kiracının taramalarını en yeniden eskiye listeler."""
    result = await session.scalars(
        select(Screening).order_by(Screening.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result)


async def count_screenings(session: AsyncSession) -> int:
    """Kiracının toplam tarama sayısı (sayfalama için)."""
    total = await session.scalar(select(func.count()).select_from(Screening))
    return int(total or 0)


async def list_candidates(session: AsyncSession, screening_id: uuid.UUID) -> list[MatchCandidate]:
    """Bir koşunun adaylarını skora göre azalan döndürür (RLS ile kiracıya sınırlı).

    Adaylar ORM ilişkisiyle değil, her zaman bu açık sorguyla çekilir (gerekçe:
    ``models.screening.Screening.candidate_count`` docstring'i).
    """
    result = await session.scalars(
        select(MatchCandidate)
        .where(MatchCandidate.screening_id == screening_id)
        .order_by(MatchCandidate.score.desc())
    )
    return list(result)


async def get_candidate(
    session: AsyncSession, *, screening_id: uuid.UUID, candidate_id: uuid.UUID
) -> MatchCandidate | None:
    """Bir taramaya ait tek aday eşleşmeyi döndürür."""
    candidate: MatchCandidate | None = await session.scalar(
        select(MatchCandidate).where(
            MatchCandidate.id == candidate_id,
            MatchCandidate.screening_id == screening_id,
        )
    )
    return candidate


async def decide_candidate(
    session: AsyncSession,
    candidate: MatchCandidate,
    *,
    decision: MatchDecision,
    actor_user_id: uuid.UUID,
    actor_role: str,
    note: str | None = None,
) -> MatchCandidate:
    """Bir adayı onaylar ya da eler (HITL) ve denetim olayını yazar.

    Karar geri alınabilir (yeniden ``pending``e çekilemez ama diğer yöne çevrilebilir);
    her değişiklik yeni bir denetim olayı üretir, önceki karar izde kalır.
    """
    if decision is MatchDecision.PENDING:
        raise ValueError("Karar 'pending' olamaz; onaylayın ya da eleyin.")
    if decision is MatchDecision.DISMISSED and not (note or "").strip():
        # MASAK denetiminde "neden elendi" cevapsız kalamaz.
        raise ValueError("Eleme kararı için gerekçe zorunludur.")

    previous = candidate.decision
    candidate.decision = decision.value
    candidate.decided_automatically = False
    candidate.reviewed_by_user_id = actor_user_id
    candidate.reviewed_at = datetime.now(UTC)
    candidate.review_note = note
    await session.flush()

    action = (
        AuditAction.MATCH_CONFIRM
        if decision is MatchDecision.CONFIRMED
        else AuditAction.MATCH_DISMISS
    )
    await audit_service.record_event(
        session,
        tenant_id=candidate.tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        object_type="match_candidate",
        object_id=str(candidate.id),
        source_ref=candidate.source_url,
        payload={
            "screening_id": str(candidate.screening_id),
            "external_id": candidate.external_id,
            "caption": candidate.caption,
            "score": candidate.score,
            "band": candidate.band,
            "previous_decision": previous,
            "decision": candidate.decision,
            "note": note,
            "topics": candidate.topics,
        },
    )
    return candidate


def refresh_dataset_state_sync(session: Session, client: SyncYenteClient) -> list[SanctionsDataset]:
    """Katalogdan veri kümesi durumlarını okuyup ``sanctions_dataset``'i günceller.

    Celery worker'ından (senkron oturum) çağrılır. Tablo kiracıdan bağımsızdır; RLS
    bağlamı gerektirmez.
    """
    checked_at = datetime.now(UTC)
    updated: list[SanctionsDataset] = []
    for info in client.catalog():
        row = session.get(SanctionsDataset, info.name)
        if row is None:
            row = SanctionsDataset(name=info.name, checked_at=checked_at)
            session.add(row)
        row.title = info.title
        row.version = info.version
        row.last_export_at = info.last_export
        row.entity_count = info.entity_count
        row.checked_at = checked_at
        updated.append(row)
    session.flush()
    return updated
