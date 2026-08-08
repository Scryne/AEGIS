"""/api/v1/entities — varlık kütüğü, ilişkiler, çözümleme, zenginleştirme (E1.4).

Yetkilendirme:

- **Okuma:** tüm roller (denetçi dahil).
- **Kütük düzenleme** (varlık/ilişki oluşturma, güncelleme, GLEIF sorgusu):
  owner · compliance_officer · analyst — analist dosyayı hazırlar.
- **Birleştirme ve tutarsızlık kararı:** owner · compliance_officer. İki kaydı
  birleştirmek ya da "bu fark açıklandı" demek, geri alınması pahalı bir uyum kararıdır;
  analistin hazırlığından sonra uyumdan sorumlu rol verir.

**Kimlik numarası doğrulaması engel değildir:** kontrol basamağı tutmayan bir numara
kaydedilir ve yanıtta ``identifier_warnings`` ile bildirilir. Kullanıcının elindeki
gerçek belgede yazan numarayı kaydedememek kabul edilemez.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from aegis_api.dependencies import (
    Principal,
    PrincipalDep,
    SettingsDep,
    TenantSessionDep,
    require_role,
)
from aegis_api.errors import ConflictError, NotFoundError, ValidationFailedError
from aegis_core.entities import service as entity_service
from aegis_core.entities.gleif import GleifClient, GleifError, GleifNotFoundError
from aegis_core.entities.resolution import ResolutionQuery, resolve_entity
from aegis_core.entities.service import EntityInputError
from aegis_core.models import (
    AuditAction,
    DiscrepancyStatus,
    Entity,
    EntitySchema,
    Relationship,
    RelationshipType,
    Role,
    SourceType,
)
from aegis_core.models.entity import NATIONAL_ID_DOMAIN
from aegis_core.security.encryption import blind_index
from aegis_core.services import audit as audit_service

router = APIRouter(prefix="/entities", tags=["entities"])

RequireRegistryWrite = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.ANALYST))
]
RequireComplianceDecision = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER))
]

SchemaLiteral = Literal["Person", "Company"]
SourceLiteral = Literal["declared", "document", "registry", "gleif", "screening"]


# ── Şemalar ──────────────────────────────────────────────────────────────────


class IdentifierWarningResponse(BaseModel):
    """Kimlik numarası uyarısı (kayıt yapıldı, dikkat çekiliyor)."""

    field: str
    value: str
    message: str


class EntityCreateRequest(BaseModel):
    """Yeni varlık (şirket ya da kişi)."""

    name: str = Field(min_length=1, max_length=512)
    schema_type: SchemaLiteral = "Company"
    tax_number: str | None = Field(default=None, max_length=32)
    mersis_number: str | None = Field(default=None, max_length=32)
    lei_code: str | None = Field(default=None, max_length=32)
    trade_registry_number: str | None = Field(default=None, max_length=64)
    national_id: str | None = Field(default=None, max_length=32)
    """TCKN — şifreli saklanır, yanıtlarda maskeli döner (ADR-0005)."""

    country: str | None = Field(default=None, max_length=8)
    address: str | None = None
    incorporation_date: date | None = None
    birth_date: date | None = None
    notes: str | None = None


class EntityUpdateRequest(BaseModel):
    """Varlık güncelleme — FtM öznitelik adlarıyla."""

    changes: dict[str, Any] = Field(default_factory=dict)
    source_type: SourceLiteral = "declared"
    source_ref: str | None = Field(default=None, max_length=1024)
    promote_to_current: bool = True
    """``false`` ise gözlem kaydedilir ama geçerli değer değişmez (karşılaştırma için)."""


class EntityResponse(BaseModel):
    """Varlık kaydı (kimlik numarası maskeli)."""

    id: uuid.UUID
    schema_type: str
    name: str
    name_normalized: str
    tax_number: str | None
    mersis_number: str | None
    lei_code: str | None
    trade_registry_number: str | None
    national_id_masked: str | None
    country: str | None
    address: str | None
    incorporation_date: date | None
    birth_date: date | None
    notes: str | None
    status: str
    merged_into_id: uuid.UUID | None
    created_at: datetime


class EntityWriteResponse(BaseModel):
    """Yazma sonucu: kayıt + uyarılar (uyarı, hata değildir)."""

    entity: EntityResponse
    identifier_warnings: list[IdentifierWarningResponse] = Field(default_factory=list)
    discrepancies_created: int = 0


class EntityListResponse(BaseModel):
    """Sayfalanmış varlık listesi."""

    total: int
    items: list[EntityResponse]


class AttributeResponse(BaseModel):
    """Bir öznitelik gözlemi (provenansıyla)."""

    id: uuid.UUID
    name: str
    value: str
    source_type: str
    source_ref: str | None
    document_id: uuid.UUID | None
    observed_at: datetime
    is_current: bool


class RelationshipCreateRequest(BaseModel):
    """İki varlık arasında bağ."""

    source_entity_id: uuid.UUID
    """Kişi/şirket — bağın kaynağı (ör. yönetici)."""

    rel_type: Literal["officer", "shareholder", "ubo", "family", "control", "representative"]
    role_title: str | None = Field(default=None, max_length=255)
    ownership_percent: float | None = Field(default=None, ge=0, le=100)
    start_date: date | None = None
    end_date: date | None = None
    source_type: SourceLiteral = "declared"
    source_ref: str | None = Field(default=None, max_length=1024)


class RelationshipResponse(BaseModel):
    """İlişki kaydı."""

    id: uuid.UUID
    source_entity_id: uuid.UUID
    source_entity_name: str | None
    target_entity_id: uuid.UUID
    target_entity_name: str | None
    rel_type: str
    role_title: str | None
    ownership_percent: float | None
    start_date: date | None
    end_date: date | None
    source_type: str
    source_ref: str | None
    document_id: uuid.UUID | None


class DiscrepancyResponse(BaseModel):
    """Beyan ile gözlem arasındaki fark."""

    id: uuid.UUID
    entity_id: uuid.UUID
    attribute_name: str
    declared_value: str
    declared_source_ref: str | None
    observed_value: str
    observed_source_type: str
    observed_source_ref: str | None
    document_id: uuid.UUID | None
    severity: str
    status: str
    resolution_note: str | None
    reviewed_at: datetime | None
    created_at: datetime


class DiscrepancyDecisionRequest(BaseModel):
    """Tutarsızlık kararı (gerekçe zorunlu)."""

    status: Literal["accepted", "resolved"]
    note: str = Field(min_length=1, max_length=2000)


class ResolutionCandidateResponse(BaseModel):
    """Çözümleme adayı."""

    entity_id: uuid.UUID
    name: str
    schema_type: str
    similarity: float
    reason: str
    conflicting_identifier: str | None


class ResolutionRequest(BaseModel):
    """Çözümleme sorgusu (kayıt oluşturmaz — yalnız sorar)."""

    name: str = Field(min_length=1, max_length=512)
    schema_type: SchemaLiteral = "Company"
    tax_number: str | None = None
    mersis_number: str | None = None
    lei_code: str | None = None
    national_id: str | None = None


class ResolutionResponse(BaseModel):
    """Çözümleme sonucu."""

    outcome: str
    matched_entity_id: uuid.UUID | None
    candidates: list[ResolutionCandidateResponse]


class MergeRequest(BaseModel):
    """Birleştirme: ``source_entity_id`` kaydı bu varlığa katılır."""

    source_entity_id: uuid.UUID
    note: str | None = Field(default=None, max_length=2000)


class GleifEnrichResponse(BaseModel):
    """GLEIF zenginleştirme sonucu."""

    lei: str
    legal_name: str | None
    country: str | None
    address: str | None
    status: str | None
    registration_authority_id: str | None
    source_url: str
    discrepancies_created: int


# ── Dönüştürücüler ───────────────────────────────────────────────────────────


def _entity_response(entity: Entity) -> EntityResponse:
    return EntityResponse(
        id=entity.id,
        schema_type=entity.schema_type,
        name=entity.name,
        name_normalized=entity.name_normalized,
        tax_number=entity.tax_number,
        mersis_number=entity.mersis_number,
        lei_code=entity.lei_code,
        trade_registry_number=entity.trade_registry_number,
        # TCKN asla düz metin dönmez — arayüz de görmemelidir.
        national_id_masked=(
            entity_service.mask_identifier(entity.national_id) if entity.national_id else None
        ),
        country=entity.country,
        address=entity.address,
        incorporation_date=entity.incorporation_date,
        birth_date=entity.birth_date,
        notes=entity.notes,
        status=entity.status,
        merged_into_id=entity.merged_into_id,
        created_at=entity.created_at,
    )


def _warning_responses(
    warnings: list[entity_service.IdentifierWarning],
) -> list[IdentifierWarningResponse]:
    return [
        IdentifierWarningResponse(field=item.field, value=item.value, message=item.message)
        for item in warnings
    ]


async def _relationship_response(
    session: TenantSessionDep, relationship: Relationship
) -> RelationshipResponse:
    source = await entity_service.get_entity(session, relationship.source_entity_id)
    target = await entity_service.get_entity(session, relationship.target_entity_id)
    return RelationshipResponse(
        id=relationship.id,
        source_entity_id=relationship.source_entity_id,
        source_entity_name=source.name if source else None,
        target_entity_id=relationship.target_entity_id,
        target_entity_name=target.name if target else None,
        rel_type=relationship.rel_type,
        role_title=relationship.role_title,
        ownership_percent=(
            float(relationship.ownership_percent)
            if relationship.ownership_percent is not None
            else None
        ),
        start_date=relationship.start_date,
        end_date=relationship.end_date,
        source_type=relationship.source_type,
        source_ref=relationship.source_ref,
        document_id=relationship.document_id,
    )


def _discrepancy_response(item: Any) -> DiscrepancyResponse:
    return DiscrepancyResponse(
        id=item.id,
        entity_id=item.entity_id,
        attribute_name=item.attribute_name,
        declared_value=item.declared_value,
        declared_source_ref=item.declared_source_ref,
        observed_value=item.observed_value,
        observed_source_type=item.observed_source_type,
        observed_source_ref=item.observed_source_ref,
        document_id=item.document_id,
        severity=item.severity,
        status=item.status,
        resolution_note=item.resolution_note,
        reviewed_at=item.reviewed_at,
        created_at=item.created_at,
    )


async def _require_entity(session: TenantSessionDep, entity_id: uuid.UUID) -> Entity:
    entity = await entity_service.get_entity(session, entity_id)
    if entity is None:
        raise NotFoundError("Varlık bulunamadı.")
    return entity


# ── Uçlar ────────────────────────────────────────────────────────────────────
# NOT: sabit yollar (/resolve, /discrepancies) parametreli yoldan ÖNCE tanımlanır.


@router.post("/resolve", response_model=ResolutionResponse)
async def resolve(
    body: ResolutionRequest, _principal: PrincipalDep, session: TenantSessionDep
) -> ResolutionResponse:
    """Bir varlık tanımının kütükte karşılığı var mı — **kayıt oluşturmaz**.

    Arayüz bunu "yeni dosya" formunda kullanır: kullanıcı unvanı yazarken aynı şirketin
    zaten kayıtlı olup olmadığını görür ve mükerrer kayıt açmaz.
    """
    fingerprint = (
        blind_index(
            entity_service.validate_identifiers(national_id=body.national_id)[0]["national_id"]
            or "",
            domain=NATIONAL_ID_DOMAIN,
        )
        if body.national_id
        else None
    )
    result = await resolve_entity(
        session,
        ResolutionQuery(
            name=body.name,
            schema_type=EntitySchema(body.schema_type),
            tax_number=(body.tax_number or "").strip() or None,
            mersis_number=(body.mersis_number or "").strip() or None,
            lei_code=(body.lei_code or "").strip().upper() or None,
            national_id_fingerprint=fingerprint,
        ),
    )
    return ResolutionResponse(
        outcome=result.outcome.value,
        matched_entity_id=result.matched.id if result.matched else None,
        candidates=[
            ResolutionCandidateResponse(
                entity_id=candidate.entity_id,
                name=candidate.name,
                schema_type=candidate.schema_type,
                similarity=candidate.similarity,
                reason=candidate.reason,
                conflicting_identifier=candidate.conflicting_identifier,
            )
            for candidate in result.candidates
        ],
    )


@router.get("/discrepancies", response_model=list[DiscrepancyResponse])
async def list_all_discrepancies(
    _principal: PrincipalDep,
    session: TenantSessionDep,
    open_only: Annotated[bool, Query()] = True,
) -> list[DiscrepancyResponse]:
    """Kiracının tüm tutarsızlıklarını listeler (panel için)."""
    rows = await entity_service.list_discrepancies(session, open_only=open_only)
    return [_discrepancy_response(row) for row in rows]


@router.post("", response_model=EntityWriteResponse, status_code=status.HTTP_201_CREATED)
async def create_entity(
    body: EntityCreateRequest,
    principal: RequireRegistryWrite,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> EntityWriteResponse:
    """Yeni varlık oluşturur (her alan beyan gözlemi olarak provenansla kaydedilir)."""
    try:
        entity, warnings = await entity_service.create_entity(
            session,
            tenant_id=principal.tenant_id,
            name=body.name,
            schema_type=EntitySchema(body.schema_type),
            tax_number=body.tax_number,
            mersis_number=body.mersis_number,
            lei_code=body.lei_code,
            trade_registry_number=body.trade_registry_number,
            national_id=body.national_id,
            country=body.country,
            address=body.address,
            incorporation_date=body.incorporation_date,
            birth_date=body.birth_date,
            notes=body.notes,
            source_type=SourceType.DECLARED,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
            retention_years=settings.document_retention_years,
        )
    except EntityInputError as exc:
        raise ValidationFailedError(str(exc)) from exc
    return EntityWriteResponse(
        entity=_entity_response(entity), identifier_warnings=_warning_responses(warnings)
    )


@router.get("", response_model=EntityListResponse)
async def list_entities(
    _principal: PrincipalDep,
    session: TenantSessionDep,
    q: Annotated[str | None, Query(max_length=512)] = None,
    schema_type: Annotated[SchemaLiteral | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EntityListResponse:
    """Varlıkları listeler / adına göre arar."""
    entities = await entity_service.list_entities(
        session,
        query=q,
        schema_type=EntitySchema(schema_type) if schema_type else None,
        limit=limit,
        offset=offset,
    )
    total = await entity_service.count_entities(session)
    return EntityListResponse(total=total, items=[_entity_response(entity) for entity in entities])


@router.get("/{entity_id}", response_model=EntityResponse)
async def get_entity(
    entity_id: uuid.UUID, _principal: PrincipalDep, session: TenantSessionDep
) -> EntityResponse:
    """Tek bir varlığı döndürür."""
    return _entity_response(await _require_entity(session, entity_id))


@router.patch("/{entity_id}", response_model=EntityWriteResponse)
async def update_entity(
    entity_id: uuid.UUID,
    body: EntityUpdateRequest,
    principal: RequireRegistryWrite,
    session: TenantSessionDep,
) -> EntityWriteResponse:
    """Varlığı günceller; beyanla çelişen gözlem tutarsızlık üretir."""
    entity = await _require_entity(session, entity_id)
    try:
        updated, warnings, discrepancies = await entity_service.update_entity(
            session,
            entity,
            changes=dict(body.changes),
            source_type=SourceType(body.source_type),
            source_ref=body.source_ref,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
            promote_to_current=body.promote_to_current,
        )
    except (EntityInputError, ValueError) as exc:
        raise ValidationFailedError(str(exc)) from exc
    return EntityWriteResponse(
        entity=_entity_response(updated),
        identifier_warnings=_warning_responses(warnings),
        discrepancies_created=len(discrepancies),
    )


@router.get("/{entity_id}/attributes", response_model=list[AttributeResponse])
async def list_attributes(
    entity_id: uuid.UUID, _principal: PrincipalDep, session: TenantSessionDep
) -> list[AttributeResponse]:
    """Varlığın öznitelik gözlemlerini kaynaklarıyla döndürür (provenans görünümü)."""
    await _require_entity(session, entity_id)
    rows = await entity_service.list_attributes(session, entity_id)
    return [
        AttributeResponse(
            id=row.id,
            name=row.name,
            value=row.value,
            source_type=row.source_type,
            source_ref=row.source_ref,
            document_id=row.document_id,
            observed_at=row.observed_at,
            is_current=row.is_current,
        )
        for row in rows
    ]


@router.get("/{entity_id}/discrepancies", response_model=list[DiscrepancyResponse])
async def list_entity_discrepancies(
    entity_id: uuid.UUID,
    _principal: PrincipalDep,
    session: TenantSessionDep,
    open_only: Annotated[bool, Query()] = False,
) -> list[DiscrepancyResponse]:
    """Bir varlığın tutarsızlıklarını döndürür."""
    await _require_entity(session, entity_id)
    rows = await entity_service.list_discrepancies(
        session, entity_id=entity_id, open_only=open_only
    )
    return [_discrepancy_response(row) for row in rows]


@router.post(
    "/{entity_id}/discrepancies/{discrepancy_id}/decision", response_model=DiscrepancyResponse
)
async def decide_discrepancy(
    entity_id: uuid.UUID,
    discrepancy_id: uuid.UUID,
    body: DiscrepancyDecisionRequest,
    principal: RequireComplianceDecision,
    session: TenantSessionDep,
) -> DiscrepancyResponse:
    """Tutarsızlığı karara bağlar (gerekçe zorunlu, denetim olayı yazılır)."""
    rows = await entity_service.list_discrepancies(session, entity_id=entity_id)
    discrepancy = next((row for row in rows if row.id == discrepancy_id), None)
    if discrepancy is None:
        raise NotFoundError("Tutarsızlık bulunamadı.")
    try:
        updated = await entity_service.decide_discrepancy(
            session,
            discrepancy,
            status=DiscrepancyStatus(body.status),
            note=body.note,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
        )
    except EntityInputError as exc:
        raise ValidationFailedError(str(exc)) from exc
    return _discrepancy_response(updated)


# ── İlişkiler ────────────────────────────────────────────────────────────────


@router.get("/{entity_id}/relationships", response_model=list[RelationshipResponse])
async def list_relationships(
    entity_id: uuid.UUID, _principal: PrincipalDep, session: TenantSessionDep
) -> list[RelationshipResponse]:
    """Varlığa bağlı ilişkileri (her iki yön) döndürür."""
    await _require_entity(session, entity_id)
    rows = await entity_service.list_relationships(session, entity_id)
    return [await _relationship_response(session, row) for row in rows]


@router.post(
    "/{entity_id}/relationships",
    response_model=RelationshipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_relationship(
    entity_id: uuid.UUID,
    body: RelationshipCreateRequest,
    principal: RequireRegistryWrite,
    session: TenantSessionDep,
) -> RelationshipResponse:
    """Varlığa bir bağ ekler (yönetici, ortak, UBO …)."""
    target = await _require_entity(session, entity_id)
    await _require_entity(session, body.source_entity_id)
    try:
        relationship = await entity_service.create_relationship(
            session,
            tenant_id=principal.tenant_id,
            source_entity_id=body.source_entity_id,
            target_entity_id=target.id,
            rel_type=RelationshipType(body.rel_type),
            role_title=body.role_title,
            ownership_percent=body.ownership_percent,
            start_date=body.start_date,
            end_date=body.end_date,
            source_type=SourceType(body.source_type),
            source_ref=body.source_ref,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
        )
    except EntityInputError as exc:
        raise ValidationFailedError(str(exc)) from exc
    return await _relationship_response(session, relationship)


@router.delete(
    "/{entity_id}/relationships/{relationship_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_relationship(
    entity_id: uuid.UUID,
    relationship_id: uuid.UUID,
    principal: RequireRegistryWrite,
    session: TenantSessionDep,
) -> None:
    """Bir bağı kaldırır (denetim izinde kalır)."""
    await _require_entity(session, entity_id)
    relationship = await entity_service.get_relationship(session, relationship_id)
    if relationship is None:
        raise NotFoundError("İlişki bulunamadı.")
    await entity_service.delete_relationship(
        session,
        relationship,
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
    )


# ── Birleştirme ve zenginleştirme ────────────────────────────────────────────


@router.post("/{entity_id}/merge", response_model=EntityResponse)
async def merge(
    entity_id: uuid.UUID,
    body: MergeRequest,
    principal: RequireComplianceDecision,
    session: TenantSessionDep,
) -> EntityResponse:
    """``source_entity_id`` kaydını bu varlığa birleştirir (kaynak kayıt silinmez)."""
    target = await _require_entity(session, entity_id)
    source = await _require_entity(session, body.source_entity_id)
    try:
        merged = await entity_service.merge_entities(
            session,
            source=source,
            target=target,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
            note=body.note,
        )
    except EntityInputError as exc:
        raise ConflictError(str(exc)) from exc
    return _entity_response(merged)


@router.post("/{entity_id}/enrich/gleif", response_model=GleifEnrichResponse)
async def enrich_gleif(
    entity_id: uuid.UUID,
    principal: RequireRegistryWrite,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> GleifEnrichResponse:
    """Varlığın LEI kodunu kamuya açık GLEIF kütüğünde sorgular.

    **KVKK:** dışarı çıkan tek şey LEI kodudur (kamuya açık tanımlayıcı); ad, adres,
    vergi no ya da TCKN gönderilmez. Sorgu bir denetim olayı yazar.

    Gelen değerler beyanın üstüne **yazılmaz**: ``gleif`` kaynaklı gözlem olarak
    kaydedilir; beyanla çelişirse tutarsızlık üretir.
    """
    if not settings.gleif_enabled:
        raise ValidationFailedError("GLEIF zenginleştirmesi bu kurulumda kapalı.")
    entity = await _require_entity(session, entity_id)
    if not entity.lei_code:
        raise ValidationFailedError("Varlığın LEI kodu yok; önce LEI kaydedin.")

    async with GleifClient(
        settings.gleif_api_url, timeout_seconds=settings.gleif_timeout_seconds
    ) as client:
        try:
            record = await client.fetch(entity.lei_code)
        except GleifNotFoundError as exc:
            raise NotFoundError(str(exc)) from exc
        except GleifError as exc:
            raise ValidationFailedError(str(exc)) from exc

    await audit_service.record_event(
        session,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
        action=AuditAction.ENRICHMENT_LOOKUP,
        object_type="entity",
        object_id=str(entity.id),
        source_ref=record.source_url,
        payload={
            "provider": "gleif",
            # İzde ne gönderdiğimiz açıkça durur: yalnız LEI.
            "sent_identifier": {"leiCode": entity.lei_code},
            "legal_name": record.legal_name,
            "status": record.status,
        },
    )

    changes: dict[str, Any] = {}
    if record.legal_name:
        changes["name"] = record.legal_name
    if record.address:
        changes["address"] = record.address
    if record.country:
        changes["country"] = record.country
    discrepancies: list[Any] = []
    if changes:
        _entity, _warnings, discrepancies = await entity_service.update_entity(
            session,
            entity,
            changes=changes,
            source_type=SourceType.GLEIF,
            source_ref=record.source_url,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
            promote_to_current=False,
        )

    return GleifEnrichResponse(
        lei=record.lei,
        legal_name=record.legal_name,
        country=record.country,
        address=record.address,
        status=record.status,
        registration_authority_id=record.registration_authority_id,
        source_url=record.source_url,
        discrepancies_created=len(discrepancies),
    )
