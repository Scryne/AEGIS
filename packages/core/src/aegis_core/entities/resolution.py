"""Varlık çözümleme (entity resolution) v1 — E1.4, Revizyon R4.

Soru: elimizdeki ad/numara, kütükteki **mevcut** bir varlığa mı ait, yoksa yeni mi?

Sıra bilinçlidir:

1. **Deterministik tanımlayıcı** (vergi no · MERSİS · LEI · TCKN kör indeksi) — eşleşme
   varsa iş biter. Bu numaralar tekildir; ada bakmaya gerek yoktur.
2. **Çelişki kontrolü** — adı benzeyen ama tanımlayıcısı FARKLI olan aday, eşleşme
   sayılmaz. "Yıldız İnşaat" iki ayrı vergi numarasıyla iki ayrı şirkettir; adın
   benzerliği bunu değiştirmez. Bu kural, bulanık eşleşmenin en tehlikeli hatasını
   (iki farklı müşteriyi birleştirmek) kapatır.
3. **Bulanık ad** (``pg_trgm`` trigram benzerliği, Türkçe normalizasyondan geçmiş ASCII
   ad üzerinde) — tek ve yüksek skorlu aday varsa eşleşme; birden çok aday ya da orta
   skor varsa **belirsiz** sayılır ve insana sorulur.
4. Hiçbiri değilse **yeni varlık**.

**Neden embedding yok (R4):** yente zaten yaptırım tarafındaki zor bulanık eşleştirmeyi
çözüyor; içeride ikinci bir sistem kurmak tekrar iş olurdu. Ayrıca etiketli değerlendirme
seti olmadan embedding hattı ayarlanamaz — o seti önce insan inceleme kuyruğunun
*üretmesi* gerekir. pgvector Phase 2'de, olumsuz medya için gelir.

**Otomatik birleştirme yoktur.** Bu modül bir *öneri* döndürür; birleştirmeyi
``service.merge_entities`` yapar ve onu da bir kullanıcı tetikler.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.models import Entity, EntitySchema, EntityStatus
from aegis_core.screening.normalization import SubjectType, normalize_name

# Bu skorun üstünde, TEK aday varsa eşleşme kabul edilir.
AUTO_MATCH_SIMILARITY = 0.92
# Bu skorun üstündeki adaylar insana gösterilir (inceleme bandı).
REVIEW_SIMILARITY = 0.55
# İncelemeye sunulan azami aday sayısı.
MAX_CANDIDATES = 10


class ResolutionOutcome(StrEnum):
    """Çözümlemenin sonucu."""

    MATCHED = "matched"
    """Kesin eşleşme (deterministik tanımlayıcı ya da tek + yüksek skorlu ad)."""

    AMBIGUOUS = "ambiguous"
    """Aday(lar) var ama kesin değil — **insan kararı gerekir**."""

    NEW = "new"
    """Eşleşme yok; yeni varlık oluşturulmalı."""


@dataclass(frozen=True)
class ResolutionCandidate:
    """Bir aday eşleşme ve neden aday olduğu."""

    entity_id: uuid.UUID
    name: str
    schema_type: str
    similarity: float
    reason: str
    """"vergi no eşleşti" / "ad benzerliği 0.87" — kullanıcı kararını buna bakarak verir."""

    conflicting_identifier: str | None = None
    """Adı benziyor ama şu tanımlayıcısı çelişiyor (eşleşme olarak KABUL EDİLMEZ)."""


@dataclass(frozen=True)
class ResolutionResult:
    """``resolve_entity`` çıktısı."""

    outcome: ResolutionOutcome
    matched: Entity | None = None
    candidates: list[ResolutionCandidate] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        """İnsan kararı gerekiyor mu."""
        return self.outcome is ResolutionOutcome.AMBIGUOUS


@dataclass(frozen=True)
class ResolutionQuery:
    """Çözümlenecek girdi (henüz kütükte olmayan bir varlık tanımı)."""

    name: str
    schema_type: EntitySchema
    tax_number: str | None = None
    mersis_number: str | None = None
    lei_code: str | None = None
    national_id_fingerprint: str | None = None


def _active(statement: Select[tuple[Entity]]) -> Select[tuple[Entity]]:
    """Yalnız aktif kayıtlar: birleştirilmiş varlıklar eşleşme hedefi olamaz."""
    return statement.where(Entity.status == EntityStatus.ACTIVE.value)


async def _match_by_identifier(
    session: AsyncSession, query: ResolutionQuery
) -> tuple[Entity | None, str | None]:
    """Deterministik tanımlayıcılardan biriyle eşleşen varlığı döndürür."""
    conditions = []
    labels: dict[str, str] = {}
    if query.tax_number:
        conditions.append(Entity.tax_number == query.tax_number)
        labels["tax_number"] = "vergi numarası"
    if query.mersis_number:
        conditions.append(Entity.mersis_number == query.mersis_number)
        labels["mersis_number"] = "MERSİS numarası"
    if query.lei_code:
        conditions.append(Entity.lei_code == query.lei_code)
        labels["lei_code"] = "LEI"
    if query.national_id_fingerprint:
        conditions.append(Entity.national_id_fingerprint == query.national_id_fingerprint)
        labels["national_id_fingerprint"] = "T.C. kimlik numarası"
    if not conditions:
        return None, None

    entity = await session.scalar(_active(select(Entity)).where(or_(*conditions)).limit(1))
    if entity is None:
        return None, None
    for attribute, label in labels.items():
        if getattr(entity, attribute) == getattr(query, attribute):
            return entity, label
    return entity, "tanımlayıcı"  # pragma: no cover - yukarıdaki döngü kapsar


def _conflicting_identifier(entity: Entity, query: ResolutionQuery) -> str | None:
    """Aday ile sorgunun tanımlayıcıları çelişiyor mu (ikisi de dolu ve farklı)."""
    pairs = (
        ("vergi numarası", entity.tax_number, query.tax_number),
        ("MERSİS numarası", entity.mersis_number, query.mersis_number),
        ("LEI", entity.lei_code, query.lei_code),
        (
            "T.C. kimlik numarası",
            entity.national_id_fingerprint,
            query.national_id_fingerprint,
        ),
    )
    for label, existing, incoming in pairs:
        if existing and incoming and existing != incoming:
            return label
    return None


async def find_similar(
    session: AsyncSession,
    name: str,
    schema_type: EntitySchema,
    *,
    threshold: float = REVIEW_SIMILARITY,
    limit: int = MAX_CANDIDATES,
) -> list[tuple[Entity, float]]:
    """Ada göre benzer varlıkları trigram benzerliğiyle bulur (en yüksek skor önce).

    Karşılaştırma, taramada kullanılan **aynı** Türkçe normalizasyondan geçmiş ASCII ad
    üzerinde yapılır; böylece "Yıldız İnşaat A.Ş." ile "YILDIZ INSAAT LTD STI" aynı
    uzayda buluşur.
    """
    subject = SubjectType.PERSON if schema_type is EntitySchema.PERSON else SubjectType.COMPANY
    normalized = normalize_name(name, subject)
    if normalized.is_empty:
        return []

    similarity = func.similarity(Entity.name_ascii, normalized.ascii)
    statement = (
        _active(select(Entity, similarity.label("score")))
        .where(Entity.schema_type == schema_type.value)
        .where(similarity >= threshold)
        .order_by(similarity.desc())
        .limit(limit)
    )
    rows = await session.execute(statement)
    return [(row[0], float(row[1])) for row in rows]


async def resolve_entity(session: AsyncSession, query: ResolutionQuery) -> ResolutionResult:
    """Bir varlık tanımını kütükle çözümler (eşleşti / belirsiz / yeni).

    RLS aktif kiracıyla sınırlar; çağıran ayrıca kiracı filtresi vermez.
    """
    matched, label = await _match_by_identifier(session, query)
    if matched is not None:
        return ResolutionResult(
            outcome=ResolutionOutcome.MATCHED,
            matched=matched,
            candidates=[
                ResolutionCandidate(
                    entity_id=matched.id,
                    name=matched.name,
                    schema_type=matched.schema_type,
                    similarity=1.0,
                    reason=f"{label} eşleşti",
                )
            ],
        )

    similar = await find_similar(session, query.name, query.schema_type)
    candidates: list[ResolutionCandidate] = []
    clean_matches: list[tuple[Entity, float]] = []
    for entity, score in similar:
        conflict = _conflicting_identifier(entity, query)
        candidates.append(
            ResolutionCandidate(
                entity_id=entity.id,
                name=entity.name,
                schema_type=entity.schema_type,
                similarity=score,
                reason=(
                    f"ad benzerliği {score:.2f}"
                    if conflict is None
                    else f"ad benzerliği {score:.2f} ama {conflict} farklı"
                ),
                conflicting_identifier=conflict,
            )
        )
        if conflict is None:
            clean_matches.append((entity, score))

    if not clean_matches:
        # Yalnız çelişkili adaylar varsa bile bu YENİ bir varlıktır; adaylar kullanıcıya
        # bilgi olarak döner ("benzer ad var ama başka bir şirket").
        return ResolutionResult(outcome=ResolutionOutcome.NEW, candidates=candidates)

    best_entity, best_score = clean_matches[0]
    only_one_strong = len([1 for _, score in clean_matches if score >= AUTO_MATCH_SIMILARITY]) == 1
    if best_score >= AUTO_MATCH_SIMILARITY and only_one_strong:
        return ResolutionResult(
            outcome=ResolutionOutcome.MATCHED, matched=best_entity, candidates=candidates
        )
    return ResolutionResult(outcome=ResolutionOutcome.AMBIGUOUS, candidates=candidates)
