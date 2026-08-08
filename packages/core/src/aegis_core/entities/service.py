"""Varlık kütüğü servisi — CRUD, provenans, tutarsızlık, birleştirme (E1.4).

Değişmezler:

- **Her değer bir gözlemdir.** ``entity`` satırı "şu an geçerli kabul ettiğimiz" değeri
  taşır; her yazım ayrıca ``entity_attribute`` satırı üretir (kim, ne zaman, nereden).
  Bu, ROADMAP'in *"provenance on every attribute"* koşuludur ve tutarsızlık tespitinin
  girdisidir.
- **Kütüğü değiştiren her eylem bir denetim olayı yazar** (Invariant 2): dosyanın kimin
  hakkında olduğu ve hangi bağların kurulduğu, tarama sonucunu doğrudan belirler.
- **TCKN düz metin olarak ikinci bir yere yazılmaz.** ``entity.national_id`` şifrelidir;
  öznitelik/tutarsızlık satırlarına yalnız **maskeli** biçim (son 4 hane) girer.
  Bilinen sınır: son 4 hanesi aynı olan iki farklı TCKN'de tutarsızlık yakalanmaz —
  kabul edilir, çünkü varlık düzeyinde kör indeks üzerindeki tekil kısıt aynı numaranın
  iki kayda bağlanmasını zaten engeller.
- **Birleştirme veriyi silmez:** kaynak kayıt ``merged`` olarak işaretlenir ve hedefe
  işaret eder; eski taramalar ve belgeler bağlı kalır.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.entities.identifiers import IdentifierKind, check_identifier
from aegis_core.logging import get_logger
from aegis_core.models import (
    AuditAction,
    Discrepancy,
    DiscrepancySeverity,
    DiscrepancyStatus,
    Document,
    Entity,
    EntityAttribute,
    EntitySchema,
    EntityStatus,
    ExtractionProposal,
    Relationship,
    RelationshipType,
    SourceType,
)
from aegis_core.models.entity import NATIONAL_ID_DOMAIN
from aegis_core.screening.normalization import SubjectType, canonicalize, normalize_name
from aegis_core.security.encryption import blind_index
from aegis_core.services import audit as audit_service

logger = get_logger("aegis.entities.service")

# FtM benzeri öznitelik adları (entity_attribute.name).
ATTR_NAME = "name"
ATTR_ADDRESS = "address"
ATTR_COUNTRY = "country"
ATTR_TAX_NUMBER = "taxNumber"
ATTR_MERSIS_NUMBER = "mersisNumber"
ATTR_LEI_CODE = "leiCode"
ATTR_TRADE_REGISTRY = "tradeRegistryNumber"
ATTR_NATIONAL_ID = "nationalId"
ATTR_INCORPORATION_DATE = "incorporationDate"
ATTR_BIRTH_DATE = "birthDate"

# Kimlik tanımlayıcılarındaki fark kimlik şüphesidir → en yüksek ağırlık.
_CRITICAL_ATTRIBUTES = frozenset(
    {ATTR_TAX_NUMBER, ATTR_MERSIS_NUMBER, ATTR_LEI_CODE, ATTR_NATIONAL_ID}
)
_WARNING_ATTRIBUTES = frozenset(
    {ATTR_NAME, ATTR_ADDRESS, ATTR_INCORPORATION_DATE, ATTR_TRADE_REGISTRY, ATTR_BIRTH_DATE}
)

# entity kolonu ↔ öznitelik adı eşlemesi (tek yerde tutulur ki kaymasın).
_COLUMN_BY_ATTRIBUTE: dict[str, str] = {
    ATTR_NAME: "name",
    ATTR_ADDRESS: "address",
    ATTR_COUNTRY: "country",
    ATTR_TAX_NUMBER: "tax_number",
    ATTR_MERSIS_NUMBER: "mersis_number",
    ATTR_LEI_CODE: "lei_code",
    ATTR_TRADE_REGISTRY: "trade_registry_number",
    ATTR_INCORPORATION_DATE: "incorporation_date",
    ATTR_BIRTH_DATE: "birth_date",
}


class EntityInputError(ValueError):
    """Varlık girdisi geçersiz."""


@dataclass(frozen=True)
class IdentifierWarning:
    """Kimlik numarası uyarısı — kayıt **reddedilmez**, yalnız işaretlenir."""

    field: str
    value: str
    message: str


def mask_identifier(value: str) -> str:
    """Kimlik numarasını gösterim için maskeler (son 4 hane görünür)."""
    stripped = value.strip()
    if len(stripped) <= 4:
        return "*" * len(stripped)
    return "*" * (len(stripped) - 4) + stripped[-4:]


def _subject_type(schema_type: EntitySchema) -> SubjectType:
    return SubjectType.PERSON if schema_type is EntitySchema.PERSON else SubjectType.COMPANY


def _comparable(attribute: str, value: str) -> str:
    """İki gözlemin "aynı" sayılıp sayılmayacağını belirleyen karşılaştırma biçimi.

    Adres ve unvanda yazım farkı (büyük/küçük harf, noktalama, fazla boşluk) tutarsızlık
    değildir; numaralarda ise her fark anlamlıdır.
    """
    if attribute in {ATTR_TAX_NUMBER, ATTR_MERSIS_NUMBER, ATTR_TRADE_REGISTRY}:
        return "".join(char for char in value if char.isdigit())
    if attribute == ATTR_LEI_CODE:
        return value.strip().upper()
    if attribute == ATTR_NAME:
        return normalize_name(value, SubjectType.COMPANY).sort_key
    return canonicalize(value)


def _severity(attribute: str) -> DiscrepancySeverity:
    if attribute in _CRITICAL_ATTRIBUTES:
        return DiscrepancySeverity.CRITICAL
    if attribute in _WARNING_ATTRIBUTES:
        return DiscrepancySeverity.WARNING
    return DiscrepancySeverity.INFO


def validate_identifiers(
    *,
    tax_number: str | None = None,
    mersis_number: str | None = None,
    lei_code: str | None = None,
    national_id: str | None = None,
) -> tuple[dict[str, str | None], list[IdentifierWarning]]:
    """Kimlik numaralarını normalize eder ve **uyarı** listesi döndürür.

    Hiçbir numara reddedilmez (bkz. ``identifiers`` modül başlığı): kullanıcının elindeki
    gerçek belgede yazan numarayı kaydedememek kabul edilemez bir davranıştır.
    """
    warnings: list[IdentifierWarning] = []
    normalized: dict[str, str | None] = {}
    checks = (
        ("tax_number", IdentifierKind.VKN, tax_number),
        ("mersis_number", IdentifierKind.MERSIS, mersis_number),
        ("lei_code", IdentifierKind.LEI, lei_code),
        ("national_id", IdentifierKind.TCKN, national_id),
    )
    for field_name, kind, raw in checks:
        if not raw or not raw.strip():
            normalized[field_name] = None
            continue
        result = check_identifier(kind, raw)
        normalized[field_name] = result.normalized or None
        if not result.looks_valid and result.reason:
            warnings.append(IdentifierWarning(field_name, result.normalized, result.reason))
    return normalized, warnings


async def record_attribute(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity_id: uuid.UUID,
    name: str,
    value: str,
    source_type: SourceType,
    source_ref: str | None = None,
    document_id: uuid.UUID | None = None,
    observed_at: datetime | None = None,
    recorded_by_user_id: uuid.UUID | None = None,
    is_current: bool = False,
) -> EntityAttribute | None:
    """Bir öznitelik gözlemini kaydeder (aynı kaynaktan aynı değer tekrarlanmaz).

    ``nationalId`` için değer **maskelenmiş** gelmelidir; bu tablo şifreli değildir.
    """
    existing = await session.scalar(
        select(EntityAttribute).where(
            EntityAttribute.entity_id == entity_id,
            EntityAttribute.name == name,
            EntityAttribute.value == value,
            EntityAttribute.source_type == source_type.value,
        )
    )
    if existing is not None:
        if is_current and not existing.is_current:
            existing.is_current = True
            await session.flush()
        return existing

    attribute = EntityAttribute(
        tenant_id=tenant_id,
        entity_id=entity_id,
        name=name,
        value=value,
        source_type=source_type.value,
        source_ref=source_ref,
        document_id=document_id,
        observed_at=observed_at or datetime.now(UTC),
        recorded_by_user_id=recorded_by_user_id,
        is_current=is_current,
    )
    session.add(attribute)
    await session.flush()
    return attribute


async def detect_discrepancy(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity_id: uuid.UUID,
    attribute_name: str,
    observed_value: str,
    observed_source_type: SourceType,
    observed_source_ref: str | None = None,
    document_id: uuid.UUID | None = None,
) -> Discrepancy | None:
    """Yeni bir gözlemi **beyanla** karşılaştırır; çelişki varsa bulgu üretir.

    Karşılaştırma yalnız ``declared`` (müşteri beyanı) gözlemlerine karşı yapılır: iki
    belgenin birbirinden farklı olması normaldir (tarihleri farklıdır), asıl anlamlı olan
    müşterinin söylediği ile kaynağın gösterdiği arasındaki farktır.
    """
    if observed_source_type is SourceType.DECLARED:
        return None

    declared = await session.scalar(
        select(EntityAttribute)
        .where(
            EntityAttribute.entity_id == entity_id,
            EntityAttribute.name == attribute_name,
            EntityAttribute.source_type == SourceType.DECLARED.value,
        )
        .order_by(EntityAttribute.observed_at.desc())
        .limit(1)
    )
    if declared is None:
        return None
    if _comparable(attribute_name, declared.value) == _comparable(attribute_name, observed_value):
        return None

    existing = await session.scalar(
        select(Discrepancy).where(
            Discrepancy.entity_id == entity_id,
            Discrepancy.attribute_name == attribute_name,
            Discrepancy.declared_value == declared.value,
            Discrepancy.observed_value == observed_value,
        )
    )
    if existing is not None:
        return existing

    discrepancy = Discrepancy(
        tenant_id=tenant_id,
        entity_id=entity_id,
        attribute_name=attribute_name,
        declared_value=declared.value,
        declared_source_ref=declared.source_ref,
        observed_value=observed_value,
        observed_source_type=observed_source_type.value,
        observed_source_ref=observed_source_ref,
        document_id=document_id,
        severity=_severity(attribute_name).value,
        status=DiscrepancyStatus.OPEN.value,
    )
    session.add(discrepancy)
    await session.flush()
    logger.info(
        "tutarsizlik_tespit",
        entity_id=str(entity_id),
        attribute=attribute_name,
        severity=discrepancy.severity,
    )
    return discrepancy


def _apply_names(entity: Entity, name: str) -> None:
    """Adı ve türev (kanonik/ASCII) kolonlarını birlikte günceller."""
    normalized = normalize_name(name, _subject_type(EntitySchema(entity.schema_type)))
    entity.name = name
    entity.name_normalized = normalized.canonical or canonicalize(name)
    entity.name_ascii = normalized.ascii or normalized.canonical


async def create_entity(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str,
    schema_type: EntitySchema,
    tax_number: str | None = None,
    mersis_number: str | None = None,
    lei_code: str | None = None,
    trade_registry_number: str | None = None,
    national_id: str | None = None,
    country: str | None = None,
    address: str | None = None,
    incorporation_date: date | None = None,
    birth_date: date | None = None,
    notes: str | None = None,
    source_type: SourceType = SourceType.DECLARED,
    source_ref: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    retention_years: int = 5,
) -> tuple[Entity, list[IdentifierWarning]]:
    """Yeni bir varlık oluşturur; her alan için provenans satırı ve denetim olayı yazar."""
    if not name.strip():
        raise EntityInputError("Ad/unvan boş olamaz.")

    normalized_ids, warnings = validate_identifiers(
        tax_number=tax_number,
        mersis_number=mersis_number,
        lei_code=lei_code,
        national_id=national_id,
    )
    tckn = normalized_ids["national_id"]
    entity = Entity(
        tenant_id=tenant_id,
        schema_type=schema_type.value,
        name=name,
        name_normalized="",
        name_ascii="",
        tax_number=normalized_ids["tax_number"],
        mersis_number=normalized_ids["mersis_number"],
        lei_code=normalized_ids["lei_code"],
        trade_registry_number=trade_registry_number,
        national_id=tckn,
        national_id_fingerprint=(blind_index(tckn, domain=NATIONAL_ID_DOMAIN) if tckn else None),
        country=country,
        address=address,
        incorporation_date=incorporation_date,
        birth_date=birth_date,
        notes=notes,
        status=EntityStatus.ACTIVE.value,
        created_by_user_id=actor_user_id,
        retention_until=datetime.now(UTC) + timedelta(days=365 * retention_years),
    )
    _apply_names(entity, name)
    session.add(entity)
    await session.flush()

    observations: dict[str, str | None] = {
        ATTR_NAME: name,
        ATTR_ADDRESS: address,
        ATTR_COUNTRY: country,
        ATTR_TAX_NUMBER: normalized_ids["tax_number"],
        ATTR_MERSIS_NUMBER: normalized_ids["mersis_number"],
        ATTR_LEI_CODE: normalized_ids["lei_code"],
        ATTR_TRADE_REGISTRY: trade_registry_number,
        ATTR_INCORPORATION_DATE: incorporation_date.isoformat() if incorporation_date else None,
        ATTR_BIRTH_DATE: birth_date.isoformat() if birth_date else None,
        # TCKN maskelenerek yazılır — bu tablo şifreli değildir (bkz. modül başlığı).
        ATTR_NATIONAL_ID: mask_identifier(tckn) if tckn else None,
    }
    for attribute_name, value in observations.items():
        if value:
            await record_attribute(
                session,
                tenant_id=tenant_id,
                entity_id=entity.id,
                name=attribute_name,
                value=value,
                source_type=source_type,
                source_ref=source_ref,
                recorded_by_user_id=actor_user_id,
                is_current=True,
            )

    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.ENTITY_EDIT,
        object_type="entity",
        object_id=str(entity.id),
        source_ref=source_ref,
        payload={
            "operation": "create",
            "schema_type": entity.schema_type,
            "name": entity.name,
            "identifiers": {
                "taxNumber": entity.tax_number,
                "mersisNumber": entity.mersis_number,
                "leiCode": entity.lei_code,
                # Denetim izine TCKN'nin kendisi DEĞİL, maskesi girer.
                "nationalId": mask_identifier(tckn) if tckn else None,
            },
            "identifier_warnings": [warning.field for warning in warnings],
            "source_type": source_type.value,
        },
    )
    return entity, warnings


async def update_entity(
    session: AsyncSession,
    entity: Entity,
    *,
    changes: dict[str, Any],
    source_type: SourceType = SourceType.DECLARED,
    source_ref: str | None = None,
    document_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    promote_to_current: bool = True,
) -> tuple[Entity, list[IdentifierWarning], list[Discrepancy]]:
    """Varlığı günceller: provenans satırı yazar, tutarsızlık arar, denetim olayı üretir.

    ``changes`` anahtarları FtM öznitelik adlarıdır (``name``, ``address``, ``taxNumber`` …).
    ``promote_to_current=False`` ile gözlem kaydedilir ama ``entity`` satırı DEĞİŞMEZ —
    kütükten/belgeden gelen veriyi beyanın üstüne yazmadan karşılaştırmak için.
    """
    warnings: list[IdentifierWarning] = []
    discrepancies: list[Discrepancy] = []
    applied: dict[str, Any] = {}

    national_id = changes.pop(ATTR_NATIONAL_ID, None)
    if national_id:
        normalized_ids, id_warnings = validate_identifiers(national_id=str(national_id))
        warnings.extend(id_warnings)
        tckn = normalized_ids["national_id"]
        if tckn:
            masked = mask_identifier(tckn)
            discrepancy = await detect_discrepancy(
                session,
                tenant_id=entity.tenant_id,
                entity_id=entity.id,
                attribute_name=ATTR_NATIONAL_ID,
                observed_value=masked,
                observed_source_type=source_type,
                observed_source_ref=source_ref,
                document_id=document_id,
            )
            if discrepancy is not None:
                discrepancies.append(discrepancy)
            await record_attribute(
                session,
                tenant_id=entity.tenant_id,
                entity_id=entity.id,
                name=ATTR_NATIONAL_ID,
                value=masked,
                source_type=source_type,
                source_ref=source_ref,
                document_id=document_id,
                recorded_by_user_id=actor_user_id,
                is_current=promote_to_current,
            )
            if promote_to_current:
                entity.national_id = tckn
                entity.national_id_fingerprint = blind_index(tckn, domain=NATIONAL_ID_DOMAIN)
                applied[ATTR_NATIONAL_ID] = masked

    for attribute_name, raw_value in changes.items():
        if raw_value is None or attribute_name not in _COLUMN_BY_ATTRIBUTE:
            continue
        value = raw_value.isoformat() if isinstance(raw_value, date) else str(raw_value)
        if not value.strip():
            continue

        if attribute_name in {ATTR_TAX_NUMBER, ATTR_MERSIS_NUMBER, ATTR_LEI_CODE}:
            kind = {
                ATTR_TAX_NUMBER: IdentifierKind.VKN,
                ATTR_MERSIS_NUMBER: IdentifierKind.MERSIS,
                ATTR_LEI_CODE: IdentifierKind.LEI,
            }[attribute_name]
            check = check_identifier(kind, value)
            value = check.normalized or value
            if not check.looks_valid and check.reason:
                warnings.append(IdentifierWarning(attribute_name, value, check.reason))

        discrepancy = await detect_discrepancy(
            session,
            tenant_id=entity.tenant_id,
            entity_id=entity.id,
            attribute_name=attribute_name,
            observed_value=value,
            observed_source_type=source_type,
            observed_source_ref=source_ref,
            document_id=document_id,
        )
        if discrepancy is not None:
            discrepancies.append(discrepancy)

        await record_attribute(
            session,
            tenant_id=entity.tenant_id,
            entity_id=entity.id,
            name=attribute_name,
            value=value,
            source_type=source_type,
            source_ref=source_ref,
            document_id=document_id,
            recorded_by_user_id=actor_user_id,
            is_current=promote_to_current,
        )

        if promote_to_current:
            column = _COLUMN_BY_ATTRIBUTE[attribute_name]
            if attribute_name in {ATTR_INCORPORATION_DATE, ATTR_BIRTH_DATE}:
                setattr(entity, column, date.fromisoformat(value))
            elif attribute_name == ATTR_NAME:
                _apply_names(entity, value)
            else:
                setattr(entity, column, value)
            applied[attribute_name] = value

    await session.flush()
    await audit_service.record_event(
        session,
        tenant_id=entity.tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.ENTITY_EDIT,
        object_type="entity",
        object_id=str(entity.id),
        source_ref=source_ref,
        payload={
            "operation": "update",
            "applied": applied,
            "source_type": source_type.value,
            "promoted": promote_to_current,
            "discrepancies": [str(item.id) for item in discrepancies],
            "identifier_warnings": [warning.field for warning in warnings],
        },
    )
    return entity, warnings, discrepancies


async def get_entity(session: AsyncSession, entity_id: uuid.UUID) -> Entity | None:
    """Tek bir varlığı döndürür (RLS ile kiracıya sınırlı)."""
    entity: Entity | None = await session.scalar(select(Entity).where(Entity.id == entity_id))
    return entity


async def list_entities(
    session: AsyncSession,
    *,
    query: str | None = None,
    schema_type: EntitySchema | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Entity]:
    """Varlıkları listeler; ``query`` verilirse ada göre (ASCII, ILIKE) süzer."""
    statement = select(Entity).where(Entity.status == EntityStatus.ACTIVE.value)
    if schema_type is not None:
        statement = statement.where(Entity.schema_type == schema_type.value)
    if query and query.strip():
        normalized = normalize_name(query, SubjectType.COMPANY)
        needle = normalized.ascii or query.strip().lower()
        statement = statement.where(Entity.name_ascii.ilike(f"%{needle}%"))
    result = await session.scalars(
        statement.order_by(Entity.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result)


async def count_entities(session: AsyncSession) -> int:
    """Aktif varlık sayısı."""
    total = await session.scalar(
        select(func.count()).select_from(Entity).where(Entity.status == EntityStatus.ACTIVE.value)
    )
    return int(total or 0)


async def list_attributes(session: AsyncSession, entity_id: uuid.UUID) -> list[EntityAttribute]:
    """Varlığın tüm öznitelik gözlemlerini döndürür (yeni → eski)."""
    result = await session.scalars(
        select(EntityAttribute)
        .where(EntityAttribute.entity_id == entity_id)
        .order_by(EntityAttribute.name, EntityAttribute.observed_at.desc())
    )
    return list(result)


async def list_discrepancies(
    session: AsyncSession, *, entity_id: uuid.UUID | None = None, open_only: bool = False
) -> list[Discrepancy]:
    """Tutarsızlıkları listeler."""
    statement = select(Discrepancy)
    if entity_id is not None:
        statement = statement.where(Discrepancy.entity_id == entity_id)
    if open_only:
        statement = statement.where(Discrepancy.status == DiscrepancyStatus.OPEN.value)
    result = await session.scalars(statement.order_by(Discrepancy.created_at.desc()))
    return list(result)


async def decide_discrepancy(
    session: AsyncSession,
    discrepancy: Discrepancy,
    *,
    status: DiscrepancyStatus,
    note: str,
    actor_user_id: uuid.UUID,
    actor_role: str | None = None,
) -> Discrepancy:
    """Tutarsızlığı karara bağlar (gerekçe zorunlu) ve denetim olayı yazar."""
    if status is DiscrepancyStatus.OPEN:
        raise EntityInputError("Karar 'open' olamaz.")
    if not note.strip():
        # "Neden kabul edildi" sorusu MASAK denetiminde cevapsız kalamaz.
        raise EntityInputError("Tutarsızlık kararı için gerekçe zorunludur.")

    previous = discrepancy.status
    discrepancy.status = status.value
    discrepancy.resolution_note = note
    discrepancy.reviewed_by_user_id = actor_user_id
    discrepancy.reviewed_at = datetime.now(UTC)
    await session.flush()

    await audit_service.record_event(
        session,
        tenant_id=discrepancy.tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.DISCREPANCY_DECISION,
        object_type="discrepancy",
        object_id=str(discrepancy.id),
        source_ref=discrepancy.observed_source_ref,
        payload={
            "entity_id": str(discrepancy.entity_id),
            "attribute": discrepancy.attribute_name,
            "severity": discrepancy.severity,
            "previous_status": previous,
            "status": discrepancy.status,
            "note": note,
        },
    )
    return discrepancy


# ── İlişkiler ────────────────────────────────────────────────────────────────


async def create_relationship(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_entity_id: uuid.UUID,
    target_entity_id: uuid.UUID,
    rel_type: RelationshipType,
    role_title: str | None = None,
    ownership_percent: float | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    source_type: SourceType = SourceType.DECLARED,
    source_ref: str | None = None,
    document_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_role: str | None = None,
) -> Relationship:
    """İki varlık arasında bağ kurar (idempotent) ve denetim olayı yazar."""
    if source_entity_id == target_entity_id:
        raise EntityInputError("Bir varlık kendisiyle ilişkilendirilemez.")
    if ownership_percent is not None and not 0 <= ownership_percent <= 100:
        raise EntityInputError("Ortaklık payı 0 ile 100 arasında olmalıdır.")

    existing = await session.scalar(
        select(Relationship).where(
            Relationship.source_entity_id == source_entity_id,
            Relationship.target_entity_id == target_entity_id,
            Relationship.rel_type == rel_type.value,
            Relationship.role_title.is_not_distinct_from(role_title),
        )
    )
    if existing is not None:
        return existing

    relationship = Relationship(
        tenant_id=tenant_id,
        source_entity_id=source_entity_id,
        target_entity_id=target_entity_id,
        rel_type=rel_type.value,
        role_title=role_title,
        ownership_percent=ownership_percent,
        start_date=start_date,
        end_date=end_date,
        source_type=source_type.value,
        source_ref=source_ref,
        document_id=document_id,
        created_by_user_id=actor_user_id,
    )
    session.add(relationship)
    await session.flush()

    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.RELATIONSHIP_EDIT,
        object_type="relationship",
        object_id=str(relationship.id),
        source_ref=source_ref,
        payload={
            "operation": "create",
            "source_entity_id": str(source_entity_id),
            "target_entity_id": str(target_entity_id),
            "rel_type": rel_type.value,
            "role_title": role_title,
            "ownership_percent": ownership_percent,
            "source_type": source_type.value,
        },
    )
    return relationship


async def list_relationships(session: AsyncSession, entity_id: uuid.UUID) -> list[Relationship]:
    """Varlığa bağlı tüm ilişkileri (her iki yön) döndürür."""
    result = await session.scalars(
        select(Relationship)
        .where(
            (Relationship.target_entity_id == entity_id)
            | (Relationship.source_entity_id == entity_id)
        )
        .order_by(Relationship.created_at)
    )
    return list(result)


async def get_relationship(
    session: AsyncSession, relationship_id: uuid.UUID
) -> Relationship | None:
    """Tek bir ilişkiyi döndürür."""
    relationship: Relationship | None = await session.scalar(
        select(Relationship).where(Relationship.id == relationship_id)
    )
    return relationship


async def delete_relationship(
    session: AsyncSession,
    relationship: Relationship,
    *,
    actor_user_id: uuid.UUID,
    actor_role: str | None = None,
) -> None:
    """Bir ilişkiyi kaldırır ve denetim olayı yazar (silinen bağ izde kalır)."""
    payload = {
        "operation": "delete",
        "source_entity_id": str(relationship.source_entity_id),
        "target_entity_id": str(relationship.target_entity_id),
        "rel_type": relationship.rel_type,
        "role_title": relationship.role_title,
    }
    tenant_id = relationship.tenant_id
    relationship_id = relationship.id
    await session.delete(relationship)
    await session.flush()
    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.RELATIONSHIP_EDIT,
        object_type="relationship",
        object_id=str(relationship_id),
        payload=payload,
    )


# ── Birleştirme (ER kararının uygulanması) ───────────────────────────────────


async def merge_entities(
    session: AsyncSession,
    *,
    source: Entity,
    target: Entity,
    actor_user_id: uuid.UUID,
    actor_role: str | None = None,
    note: str | None = None,
) -> Entity:
    """``source`` varlığını ``target``a birleştirir (kayıt silinmez, işaretlenir).

    Bağlı kayıtlar (öznitelik gözlemleri, ilişkiler, belgeler, tutarsızlıklar, taramalar)
    hedefe taşınır; kaynak ``merged`` durumuna geçer ve hedefi işaret eder. Böylece eski
    bir tarama raporundaki bağlantı kırılmaz, ama kütükte tek bir aktif kayıt kalır.
    """
    if source.id == target.id:
        raise EntityInputError("Varlık kendisiyle birleştirilemez.")
    if source.schema_type != target.schema_type:
        raise EntityInputError("Farklı türdeki varlıklar (kişi/şirket) birleştirilemez.")
    if source.status == EntityStatus.MERGED.value:
        raise EntityInputError("Kaynak varlık zaten birleştirilmiş.")

    for model in (EntityAttribute, Relationship, Document, ExtractionProposal, Discrepancy):
        column = "entity_id"
        if model is Relationship:
            await session.execute(
                update(Relationship)
                .where(Relationship.source_entity_id == source.id)
                .values(source_entity_id=target.id)
            )
            await session.execute(
                update(Relationship)
                .where(Relationship.target_entity_id == source.id)
                .values(target_entity_id=target.id)
            )
            continue
        await session.execute(
            update(model).where(getattr(model, column) == source.id).values(entity_id=target.id)
        )

    # Hedefte boş olan deterministik tanımlayıcıları kaynaktan devral.
    for column in ("tax_number", "mersis_number", "lei_code", "trade_registry_number"):
        if getattr(target, column) is None and getattr(source, column) is not None:
            setattr(target, column, getattr(source, column))
    if target.national_id_fingerprint is None and source.national_id_fingerprint is not None:
        target.national_id = source.national_id
        target.national_id_fingerprint = source.national_id_fingerprint
        source.national_id = None
        source.national_id_fingerprint = None

    source.status = EntityStatus.MERGED.value
    source.merged_into_id = target.id
    await session.flush()

    await audit_service.record_event(
        session,
        tenant_id=target.tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.ENTITY_MERGE,
        object_type="entity",
        object_id=str(target.id),
        payload={
            "merged_entity_id": str(source.id),
            "merged_entity_name": source.name,
            "target_entity_name": target.name,
            "note": note,
        },
    )
    logger.info("varlik_birlestirildi", source=str(source.id), target=str(target.id))
    return target


async def screening_subjects_for(
    session: AsyncSession, entity: Entity
) -> Sequence[tuple[Entity, str]]:
    """Bir şirket için taranacak özneleri toplar: şirketin kendisi + kişi bağları.

    E1.3'teki tarama ucu bunu kullanarak "şirket + yöneticiler/UBO'lar" koşusunu tek
    çağrıda kurar (ROADMAP E1.3: *"entity + directors/UBOs"*).
    """
    relationships = await list_relationships(session, entity.id)
    subjects: list[tuple[Entity, str]] = [(entity, "self")]
    seen: set[uuid.UUID] = {entity.id}
    for relationship in relationships:
        if relationship.target_entity_id != entity.id:
            continue
        if relationship.source_entity_id in seen:
            continue
        related = await get_entity(session, relationship.source_entity_id)
        if related is None or related.status != EntityStatus.ACTIVE.value:
            continue
        role = relationship.rel_type
        if role not in {item.value for item in RelationshipType}:  # pragma: no cover
            role = RelationshipType.OFFICER.value
        subjects.append((related, role))
        seen.add(relationship.source_entity_id)
    return subjects
