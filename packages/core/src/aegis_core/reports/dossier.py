"""Durum tespiti dosyasının toplanması — ``DossierData`` (E1.5).

ROADMAP E1.5'in içerik listesi birebir karşılanır: *"profile, screening results incl.
dismissed-with-reason matches, discrepancies, source references, run timestamps +
dataset versions"*.

**Elenen eşleşmeler rapordan çıkarılmaz.** Otomatik elenen bir aday da, gerekçesiyle
birlikte dosyada görünür (ADR-0006: "hiçbir aday silinmez"). MASAK denetiminde savunma
"neye baktık ve neden elemedik"tir; yalnız onaylananları basan bir rapor bu soruyu
cevaplayamaz.

**Kişisel veri raporda maskelidir.** Dosya kurumdan dışarı çıkan bir belgedir; TCKN
``mask_identifier`` ile son dört hanesi görünecek şekilde yazılır (ADR-0005'in duruşu:
şifreli kolon + gösterimde maske). Vergi/MERSİS/LEI kamuya açık kütük numaralarıdır ve
tam yazılır.

Toplama işi oluşturuculardan (PDF/Word) **ayrıdır**: iki biçim de aynı ``DossierData``
nesnesinden beslenir, böylece PDF ile Word'ün içeriği birbirinden ayrışamaz.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.entities import service as entity_service
from aegis_core.models import (
    Discrepancy,
    Document,
    Entity,
    EntityAttribute,
    MatchCandidate,
    Relationship,
    Screening,
)
from aegis_core.reports import labels
from aegis_core.reports.risk import (
    DiscrepancyView,
    MatchView,
    RiskAssessment,
    ScreeningView,
    assess_risk,
)
from aegis_core.screening.thresholds import MatchDecision

# Dosyaya girecek en fazla tarama koşusu (en yeniden eskiye). Bir varlık için onlarca
# koşu birikebilir; rapor okunabilir kalmalı ve PDF şişmemelidir.
MAX_SCREENINGS_IN_DOSSIER = 10


@dataclass(frozen=True)
class ProfileField:
    """Kimlik bölümünde basılan tek bir alan."""

    label: str
    value: str


@dataclass(frozen=True)
class RelatedParty:
    """Dosyadaki ilgili taraf (yönetici, ortak, gerçek faydalanıcı …)."""

    name: str
    rel_type_label: str
    role_title: str | None
    ownership_percent: str
    source_label: str
    source_ref: str | None


@dataclass(frozen=True)
class ObservationRow:
    """Provenans tablosunun bir satırı: değer + kaynağı + gözlem zamanı."""

    attribute_label: str
    value: str
    source_label: str
    source_ref: str | None
    observed_at: str


@dataclass(frozen=True)
class DocumentRow:
    """Dosyaya kanıt olarak eklenmiş bir belge."""

    filename: str
    doc_type_label: str
    uploaded_at: str
    sha256: str
    source_ref: str | None


@dataclass(frozen=True)
class MatchRow:
    """Rapordaki bir aday eşleşme (elenenler dahil)."""

    subject_name: str
    subject_role_label: str
    caption: str
    score: str
    decision: str
    """Ham karar değeri (``MatchDecision``) — bölümleme etiket metnine bağlanmasın."""

    decision_label: str
    band_label: str
    decided_automatically: bool
    flagged: bool
    topics: str
    datasets: str
    source_url: str | None
    review_note: str | None
    match_features: str
    """"Neden eşleşti": skoru oluşturan özellikler (şeffaflık gereği raporda da vardır)."""


@dataclass(frozen=True)
class ScreeningSection:
    """Bir tarama koşusunun rapordaki bölümü."""

    screening_id: uuid.UUID
    status_label: str
    succeeded: bool
    dataset: str
    algorithm: str
    thresholds: str
    started_at: str
    completed_at: str
    duration: str
    error: str | None
    dataset_versions: dict[str, Any]
    matches: tuple[MatchRow, ...]

    @property
    def confirmed(self) -> tuple[MatchRow, ...]:
        """Onaylanmış eşleşmeler."""
        return self._by_decision(MatchDecision.CONFIRMED)

    @property
    def dismissed(self) -> tuple[MatchRow, ...]:
        """Gerekçesiyle elenmiş eşleşmeler — rapordan ÇIKARILMAZ."""
        return self._by_decision(MatchDecision.DISMISSED)

    @property
    def pending(self) -> tuple[MatchRow, ...]:
        """Karar bekleyen eşleşmeler."""
        return self._by_decision(MatchDecision.PENDING)

    def _by_decision(self, decision: MatchDecision) -> tuple[MatchRow, ...]:
        return tuple(row for row in self.matches if row.decision == decision.value)


@dataclass(frozen=True)
class DiscrepancyRow:
    """Rapordaki bir tutarsızlık (kapatılmış olanlar da görünür)."""

    attribute_label: str
    severity_label: str
    status_label: str
    declared_value: str
    observed_value: str
    observed_source_label: str
    observed_source_ref: str | None
    resolution_note: str | None
    reviewed_at: str


@dataclass(frozen=True)
class DossierData:
    """Bir dosyanın rapora girecek tüm içeriği (biçimden bağımsız)."""

    entity_id: uuid.UUID
    title: str
    subject_name: str
    subject_kind_label: str
    generated_at: datetime
    generated_by: str | None
    organization_name: str | None
    risk: RiskAssessment
    profile: tuple[ProfileField, ...] = ()
    related_parties: tuple[RelatedParty, ...] = ()
    screenings: tuple[ScreeningSection, ...] = ()
    discrepancies: tuple[DiscrepancyRow, ...] = ()
    documents: tuple[DocumentRow, ...] = ()
    observations: tuple[ObservationRow, ...] = ()
    dataset_versions: dict[str, Any] = field(default_factory=dict)
    screening_ids: tuple[uuid.UUID, ...] = ()

    @property
    def generated_at_label(self) -> str:
        """Üretim zamanı (rapor kapağında)."""
        return labels.format_datetime(self.generated_at)


# ── Yardımcılar ──────────────────────────────────────────────────────────────


def _profile_fields(entity: Entity) -> tuple[ProfileField, ...]:
    """Kimlik alanlarını rapor sırasıyla toplar (boş olanlar basılmaz)."""
    national_id = entity_service.mask_identifier(entity.national_id) if entity.national_id else None
    pairs: list[tuple[str, object]] = [
        ("Unvan / ad", entity.name),
        ("Tür", labels.label(labels.SCHEMA_LABELS, entity.schema_type)),
        ("Vergi no", entity.tax_number),
        ("MERSİS no", entity.mersis_number),
        ("Ticaret sicil no", entity.trade_registry_number),
        ("LEI", entity.lei_code),
        ("T.C. kimlik no (maskeli)", national_id),
        ("Ülke", entity.country),
        ("Adres", entity.address),
        ("Kuruluş tarihi", entity.incorporation_date),
        ("Doğum tarihi", entity.birth_date),
        ("Kayıt oluşturma", entity.created_at),
    ]
    return tuple(
        ProfileField(label=name, value=labels.format_value(value))
        for name, value in pairs
        if value not in (None, "")
    )


def _match_features(features: dict[str, Any]) -> str:
    """Skoru oluşturan özellikleri okunur tek satıra çevirir (en etkili üçü)."""
    if not features:
        return "—"
    ranked = sorted(
        ((str(name), value) for name, value in features.items()),
        key=lambda item: abs(float(item[1])) if isinstance(item[1], int | float) else 0.0,
        reverse=True,
    )[:3]
    return ", ".join(
        f"{name}: {value:.2f}" if isinstance(value, int | float) else f"{name}: {value}"
        for name, value in ranked
    )


def _match_row(candidate: MatchCandidate) -> MatchRow:
    topics = candidate.topics if isinstance(candidate.topics, list) else []
    datasets = candidate.datasets if isinstance(candidate.datasets, list) else []
    return MatchRow(
        subject_name=candidate.subject_name,
        subject_role_label=labels.label(labels.SUBJECT_ROLE_LABELS, candidate.subject_role),
        caption=candidate.caption,
        score=f"{candidate.score:.2f}",
        decision=candidate.decision,
        decision_label=labels.label(labels.DECISION_LABELS, candidate.decision),
        band_label=labels.label(labels.BAND_LABELS, candidate.band),
        decided_automatically=candidate.decided_automatically,
        flagged=candidate.flagged,
        topics=", ".join(str(topic) for topic in topics) or "—",
        datasets=", ".join(str(item) for item in datasets) or "—",
        source_url=candidate.source_url,
        review_note=candidate.review_note,
        match_features=_match_features(candidate.features or {}),
    )


def _match_view(candidate: MatchCandidate) -> MatchView:
    topics = candidate.topics if isinstance(candidate.topics, list) else []
    datasets = candidate.datasets if isinstance(candidate.datasets, list) else []
    return MatchView(
        subject_name=candidate.subject_name,
        caption=candidate.caption,
        score=candidate.score,
        decision=candidate.decision,
        band=candidate.band,
        flagged=candidate.flagged,
        decided_automatically=candidate.decided_automatically,
        topics=tuple(str(topic) for topic in topics),
        datasets=tuple(str(item) for item in datasets),
        source_url=candidate.source_url,
        review_note=candidate.review_note,
    )


def _duration_label(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "—"
    return f"{duration_ms / 1000:.1f} sn"


def _thresholds_label(thresholds: dict[str, Any]) -> str:
    """Koşu anındaki eşik bandını okunur biçimde yazar (raporda donmuş provenans)."""
    if not thresholds:
        return "—"
    parts = []
    if "auto_dismiss_below" in thresholds:
        parts.append(f"otomatik eleme < {thresholds['auto_dismiss_below']}")
    if "auto_flag_at" in thresholds:
        parts.append(f"otomatik işaretleme ≥ {thresholds['auto_flag_at']}")
    if "candidate_cutoff" in thresholds:
        parts.append(f"aday alt kesme {thresholds['candidate_cutoff']}")
    return "; ".join(parts) or "—"


def _discrepancy_row(item: Discrepancy) -> DiscrepancyRow:
    return DiscrepancyRow(
        attribute_label=labels.label(labels.ATTRIBUTE_LABELS, item.attribute_name),
        severity_label=labels.label(labels.SEVERITY_LABELS, item.severity),
        status_label=labels.label(labels.DISCREPANCY_STATUS_LABELS, item.status),
        declared_value=item.declared_value,
        observed_value=item.observed_value,
        observed_source_label=labels.label(labels.SOURCE_LABELS, item.observed_source_type),
        observed_source_ref=item.observed_source_ref,
        resolution_note=item.resolution_note,
        reviewed_at=labels.format_datetime(item.reviewed_at),
    )


def _discrepancy_view(item: Discrepancy) -> DiscrepancyView:
    return DiscrepancyView(
        attribute_label=labels.label(labels.ATTRIBUTE_LABELS, item.attribute_name),
        severity=item.severity,
        status=item.status,
        declared_value=item.declared_value,
        observed_value=item.observed_value,
        observed_source_ref=item.observed_source_ref,
    )


def _observation_row(attribute: EntityAttribute) -> ObservationRow:
    return ObservationRow(
        attribute_label=labels.label(labels.ATTRIBUTE_LABELS, attribute.name),
        value=attribute.value,
        source_label=labels.label(labels.SOURCE_LABELS, attribute.source_type),
        source_ref=attribute.source_ref,
        observed_at=labels.format_datetime(attribute.observed_at),
    )


def _ownership_label(value: object) -> str:
    return "—" if value is None else f"%{value}"


# ── Sorgular ─────────────────────────────────────────────────────────────────


async def _load_screenings(
    session: AsyncSession, entity_id: uuid.UUID
) -> list[tuple[Screening, list[MatchCandidate]]]:
    """Varlığın tarama koşularını adaylarıyla yükler (en yeniden eskiye).

    Adaylar ORM ilişkisiyle değil açık sorguyla çekilir (gerekçe:
    ``models.screening.Screening.candidate_count`` docstring'i).
    """
    screenings = list(
        await session.scalars(
            select(Screening)
            .where(Screening.entity_id == entity_id)
            .order_by(Screening.created_at.desc())
            .limit(MAX_SCREENINGS_IN_DOSSIER)
        )
    )
    loaded: list[tuple[Screening, list[MatchCandidate]]] = []
    for screening in screenings:
        candidates = list(
            await session.scalars(
                select(MatchCandidate)
                .where(MatchCandidate.screening_id == screening.id)
                .order_by(MatchCandidate.score.desc())
            )
        )
        loaded.append((screening, candidates))
    return loaded


async def _load_related_parties(session: AsyncSession, entity: Entity) -> tuple[RelatedParty, ...]:
    """Varlığa bağlı tarafları adlarıyla toplar."""
    relationships: Sequence[Relationship] = await entity_service.list_relationships(
        session, entity.id
    )
    parties: list[RelatedParty] = []
    for relationship in relationships:
        other_id = (
            relationship.source_entity_id
            if relationship.target_entity_id == entity.id
            else relationship.target_entity_id
        )
        other = await entity_service.get_entity(session, other_id)
        parties.append(
            RelatedParty(
                name=other.name if other else "(kayıt bulunamadı)",
                rel_type_label=labels.label(labels.REL_TYPE_LABELS, relationship.rel_type),
                role_title=relationship.role_title,
                ownership_percent=_ownership_label(relationship.ownership_percent),
                source_label=labels.label(labels.SOURCE_LABELS, relationship.source_type),
                source_ref=relationship.source_ref,
            )
        )
    return tuple(parties)


async def build_dossier(
    session: AsyncSession,
    entity: Entity,
    *,
    generated_by: str | None = None,
    organization_name: str | None = None,
    generated_at: datetime | None = None,
) -> DossierData:
    """Bir varlık için dosyanın tüm içeriğini toplar ve risk özetini hesaplar.

    Oturum kiracı bağlamlı olmalıdır (``get_tenant_session``): tüm sorgular RLS ile
    çağıranın kiracısıyla sınırlıdır.
    """
    now = generated_at or datetime.now(UTC)

    screening_pairs = await _load_screenings(session, entity.id)
    discrepancies = await entity_service.list_discrepancies(session, entity_id=entity.id)
    attributes = await entity_service.list_attributes(session, entity.id)
    documents = list(
        await session.scalars(
            select(Document)
            .where(Document.entity_id == entity.id)
            .order_by(Document.created_at.desc())
        )
    )
    related_parties = await _load_related_parties(session, entity)

    sections: list[ScreeningSection] = []
    dataset_versions: dict[str, Any] = {}
    for screening, candidates in screening_pairs:
        versions = screening.dataset_versions or {}
        # En yeni koşu önce geldiği için setdefault "en güncel sürümü koru" demektir.
        for name, value in versions.items():
            dataset_versions.setdefault(name, value)
        sections.append(
            ScreeningSection(
                screening_id=screening.id,
                status_label=labels.label(labels.SCREENING_STATUS_LABELS, screening.status),
                succeeded=screening.status == "completed",
                dataset=screening.dataset,
                algorithm=screening.algorithm,
                thresholds=_thresholds_label(screening.thresholds or {}),
                started_at=labels.format_datetime(screening.started_at),
                completed_at=labels.format_datetime(screening.completed_at),
                duration=_duration_label(screening.duration_ms),
                error=screening.error,
                dataset_versions=versions,
                matches=tuple(_match_row(candidate) for candidate in candidates),
            )
        )

    risk = assess_risk(
        screenings=[
            ScreeningView(
                status=screening.status,
                completed_at=screening.completed_at,
                dataset=screening.dataset,
                matches=tuple(_match_view(candidate) for candidate in candidates),
                error=screening.error,
            )
            for screening, candidates in screening_pairs
        ],
        discrepancies=[_discrepancy_view(item) for item in discrepancies],
        assessed_at=now,
    )

    return DossierData(
        entity_id=entity.id,
        title=f"Müşteri Tanıma Dosyası — {entity.name}",
        subject_name=entity.name,
        subject_kind_label=labels.label(labels.SCHEMA_LABELS, entity.schema_type),
        generated_at=now,
        generated_by=generated_by,
        organization_name=organization_name,
        risk=risk,
        profile=_profile_fields(entity),
        related_parties=related_parties,
        screenings=tuple(sections),
        discrepancies=tuple(_discrepancy_row(item) for item in discrepancies),
        documents=tuple(
            DocumentRow(
                filename=document.filename,
                doc_type_label=labels.label(labels.DOC_TYPE_LABELS, document.doc_type),
                uploaded_at=labels.format_datetime(document.created_at),
                sha256=document.sha256,
                source_ref=document.source_ref,
            )
            for document in documents
        ),
        observations=tuple(_observation_row(attribute) for attribute in attributes),
        dataset_versions=dataset_versions,
        screening_ids=tuple(screening.id for screening, _ in screening_pairs),
    )


def dataset_version_rows(versions: dict[str, Any]) -> tuple[tuple[str, str, str], ...]:
    """Veri kümesi sürümlerini (ad, sürüm, son güncelleme) satırlarına çevirir."""
    rows: list[tuple[str, str, str]] = []
    for name in sorted(versions):
        entry = versions[name]
        if isinstance(entry, dict):
            version = str(entry.get("version") or "—")
            exported = entry.get("last_export_at")
            rows.append((name, version, _iso_to_label(exported)))
        else:
            rows.append((name, str(entry), "—"))
    return tuple(rows)


def _iso_to_label(value: object) -> str:
    """ISO zaman damgasını rapor biçimine çevirir; çözümlenemezse ham hâlini korur."""
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return labels.format_datetime(parsed)


__all__ = [
    "MAX_SCREENINGS_IN_DOSSIER",
    "DiscrepancyRow",
    "DocumentRow",
    "DossierData",
    "MatchRow",
    "ObservationRow",
    "ProfileField",
    "RelatedParty",
    "ScreeningSection",
    "build_dossier",
    "dataset_version_rows",
]
