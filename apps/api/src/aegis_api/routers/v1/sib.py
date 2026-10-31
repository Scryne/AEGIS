"""ŞİB taslağı uçları (E2.2, ADR-0011).

Yalnız ``owner`` ve ``compliance_officer``: bildirimin varlığı bile gizlidir (5549 s.K. m.4/2),
``analyst`` ve ``auditor`` bu uçları 403 ile görür. Taslak hatalıyken kaydedilir; dışa aktarma
hatalar giderilene kadar 409 döner ve hataları ayrıntıda listeler.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_api.dependencies import Principal, SettingsDep, TenantSessionDep, require_role
from aegis_api.errors import ConflictError, NotFoundError
from aegis_core.entities import service as entity_service
from aegis_core.models import Role, SibDraft
from aegis_core.sib import kodlar
from aegis_core.sib import service as sib_service
from aegis_core.sib.form import Bulgu, SibFormu

router = APIRouter(tags=["sib"])

RequireSib = Annotated[Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER))]
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class SibOzet(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    entity_name: str
    reference_no: str
    status: str
    category: str | None
    errors: int
    warnings: int
    export_count: int
    last_exported_at: datetime | None
    updated_at: datetime
    created_at: datetime


class SibListe(BaseModel):
    items: list[SibOzet]


class SibDetay(SibOzet):
    form: SibFormu
    hatalar: list[Bulgu]
    uyarilar: list[Bulgu]
    guide_version: str
    cancel_reason: str | None


class IptalIstegi(BaseModel):
    neden: str = Field(min_length=10, max_length=2000)


class Kodlar(BaseModel):
    rehber: dict[str, str]
    aciklama_en_az: int
    aciklama_en_cok: int
    sk_en_az: int
    sk_en_cok: int
    kategoriler: dict[str, str]
    teror_orgut_turleri: dict[str, str]
    aciliyet: dict[str, str]
    gercek_baglanti: dict[str, str]
    tuzel_baglanti: dict[str, str]
    kurulus_nevi: dict[str, str]
    kimlik_belgeleri: dict[str, str]
    islem_durumu: dict[str, str]
    islem_cesidi: dict[str, str]
    sk_kodlari: dict[str, str]
    kategori_zorunlu_sk: dict[str, list[str]]


async def _taslak(session: AsyncSession, draft_id: uuid.UUID) -> SibDraft:
    taslak = await session.get(SibDraft, draft_id)  # RLS: yalnız kendi kiracısı
    if taslak is None:
        raise NotFoundError("ŞİB taslağı bulunamadı.")
    return taslak


async def _detay(session: AsyncSession, taslak: SibDraft) -> SibDetay:
    entity = await entity_service.get_entity(session, taslak.entity_id)
    ozet = sib_service.ozet(taslak, entity.name if entity else "—")
    denetim = sib_service.taslak_denetle(taslak)
    return SibDetay(
        **ozet,
        form=sib_service.form_oku(taslak),
        hatalar=denetim.hatalar,
        uyarilar=denetim.uyarilar,
        guide_version=taslak.guide_version,
        cancel_reason=taslak.cancel_reason,
    )


@router.get("/sib/kodlar", response_model=Kodlar)
async def kod_listeleri(_principal: RequireSib) -> Kodlar:
    """Formun seçmeli alanları (rehberdeki etiketleriyle) ve sınırları."""
    return Kodlar(
        rehber=dict(kodlar.REHBER),
        aciklama_en_az=kodlar.ACIKLAMA_EN_AZ,
        aciklama_en_cok=kodlar.ACIKLAMA_EN_COK,
        sk_en_az=kodlar.SK_EN_AZ,
        sk_en_cok=kodlar.SK_EN_COK,
        kategoriler=dict(kodlar.KATEGORILER),
        teror_orgut_turleri=dict(kodlar.TEROR_ORGUT_TURLERI),
        aciliyet=dict(kodlar.ACILIYET),
        gercek_baglanti=dict(kodlar.GERCEK_BAGLANTI),
        tuzel_baglanti=dict(kodlar.TUZEL_BAGLANTI),
        kurulus_nevi=dict(kodlar.KURULUS_NEVI),
        kimlik_belgeleri=dict(kodlar.KIMLIK_BELGELERI),
        islem_durumu=dict(kodlar.ISLEM_DURUMU),
        islem_cesidi=dict(kodlar.ISLEM_CESIDI),
        sk_kodlari=dict(kodlar.SK_KODLARI),
        kategori_zorunlu_sk={k: sorted(v) for k, v in kodlar.KATEGORI_ZORUNLU_SK.items()},
    )


@router.post(
    "/entities/{entity_id}/sib-drafts", response_model=SibDetay, status_code=status.HTTP_201_CREATED
)
async def olustur(
    entity_id: uuid.UUID, principal: RequireSib, session: TenantSessionDep, settings: SettingsDep
) -> SibDetay:
    """Varlığın dosyasından ön doldurulmuş yeni bir taslak açar."""
    entity = await entity_service.get_entity(session, entity_id)
    if entity is None:
        raise NotFoundError("Varlık bulunamadı.")
    taslak = await sib_service.olustur(
        session,
        entity,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
        retention_years=settings.document_retention_years,
    )
    return await _detay(session, taslak)


@router.get("/sib-drafts", response_model=SibListe)
async def listele(
    _principal: RequireSib,
    session: TenantSessionDep,
    entity_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> SibListe:
    satirlar = await sib_service.listele(session, entity_id=entity_id, limit=limit)
    return SibListe(items=[SibOzet(**sib_service.ozet(t, ad)) for t, ad in satirlar])


@router.get("/sib-drafts/{draft_id}", response_model=SibDetay)
async def detay(draft_id: uuid.UUID, _principal: RequireSib, session: TenantSessionDep) -> SibDetay:
    return await _detay(session, await _taslak(session, draft_id))


@router.put("/sib-drafts/{draft_id}", response_model=SibDetay)
async def guncelle(
    draft_id: uuid.UUID, form: SibFormu, principal: RequireSib, session: TenantSessionDep
) -> SibDetay:
    """Formu kaydeder; hatalar yanıtta döner (kayıt engellenmez)."""
    taslak = await _taslak(session, draft_id)
    try:
        await sib_service.guncelle(
            session,
            taslak,
            form,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
        )
    except sib_service.SibStateError as exc:
        raise ConflictError(str(exc)) from exc
    return await _detay(session, taslak)


@router.post("/sib-drafts/{draft_id}/export", response_class=Response)
async def disa_aktar(
    draft_id: uuid.UUID, principal: RequireSib, session: TenantSessionDep
) -> Response:
    """Doğrulanmış taslağı düzenlenebilir Word belgesi olarak indirir (denetim izine yazılır)."""
    taslak = await _taslak(session, draft_id)
    try:
        icerik, ad = await sib_service.disa_aktar(
            session,
            taslak,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
        )
    except sib_service.SibExportBlockedError as exc:
        raise ConflictError(
            "Taslakta dışa aktarmayı engelleyen hatalar var.",
            details=[b.model_dump() for b in exc.denetim.hatalar],
        ) from exc
    except sib_service.SibStateError as exc:
        raise ConflictError(str(exc)) from exc
    return Response(
        content=icerik,
        media_type=DOCX,
        headers={
            "Content-Disposition": f'attachment; filename="{ad}"',
            # Gizli belge: ara katmanlarda ve tarayıcıda önbelleğe alınmaz.
            "Cache-Control": "no-store",
        },
    )


@router.post("/sib-drafts/{draft_id}/cancel", response_model=SibDetay)
async def iptal(
    draft_id: uuid.UUID, body: IptalIstegi, principal: RequireSib, session: TenantSessionDep
) -> SibDetay:
    """Taslağı gerekçeyle iptal eder; silmez (saklama yükümlülüğü)."""
    taslak = await _taslak(session, draft_id)
    try:
        await sib_service.iptal_et(
            session,
            taslak,
            body.neden,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
        )
    except sib_service.SibStateError as exc:
        raise ConflictError(str(exc)) from exc
    return await _detay(session, taslak)
