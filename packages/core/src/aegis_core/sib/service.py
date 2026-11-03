"""ŞİB taslağı servisi: dosyadan ön doldurma, kaydetme, dışa aktarma, iptal (E2.2, ADR-0011).

**Ön doldurma yalnız kayıtlı olguları taşır.** Kişi bölümleri kütükten (kimlik, adres, doğum
tarihi, şirketin vergi/sicil numaraları) ve son gerçek faydalanıcı hesabından gelir; açıklama
alanına dosyanın risk bulguları madde madde konur ama metin **iskelet** olarak işaretlenir:
yer tutucular doldurulmadan ve metin değiştirilmeden dışa aktarılamaz (rehber §4.2.7: özgün
açıklama). Şüphe kategorisi, bildirim kategorisi ve şüpheli işlemler **seçilmez**: bunlar
yükümlünün yargısıdır; ürün önermez, boş bırakır ve doğrulama eksikliği gösterir.

Her değiştiren eylem tam bir denetim olayı yazar (Invariant 2); dışa aktarma ayrıca sayılır.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Text, func, select, text, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from aegis_core.logging import get_logger
from aegis_core.models import AuditAction, Entity, Organization, SibDraft, SibStatus
from aegis_core.models.entity import EntitySchema
from aegis_core.reports.dossier import build_dossier
from aegis_core.security.encryption import DecryptionError, get_secret_box
from aegis_core.services.audit import record_event
from aegis_core.sib.form import (
    YER_TUTUCU,
    YONERGE,
    Denetim,
    GercekKisi,
    SibFormu,
    TuzelKisi,
    Yukumlu,
    denetle,
    metin_ozeti,
)
from aegis_core.sib.kodlar import REHBER
from aegis_core.ubo import service as ubo_service

OBJECT_TYPE = "sib_draft"

logger = get_logger(__name__)


class SibStateError(ValueError):
    """Taslağın durumu bu işleme izin vermiyor (ör. iptal edilmiş taslak düzenlenemez)."""


class SibExportBlockedError(ValueError):
    """Doğrulama hataları varken dışa aktarma istendi."""

    def __init__(self, denetim: Denetim) -> None:
        super().__init__("Taslakta dışa aktarmayı engelleyen hatalar var.")
        self.denetim = denetim


def _ad_soyad(tam: str) -> tuple[str, str]:
    parcalar = tam.split()
    if len(parcalar) < 2:
        return tam, ""
    return " ".join(parcalar[:-1]), parcalar[-1]


def _ulke(kod: str | None) -> str:
    return {"TR": "Türkiye"}.get((kod or "").upper(), kod or "")


def _gercek_kisi(e: Entity, *, baglanti: str, ek_bilgi: str = "") -> GercekKisi:
    ad, soyad = _ad_soyad(e.name)
    return GercekKisi(
        baglanti=baglanti,  # type: ignore[arg-type]
        ad=ad,
        soyad=soyad,
        tckn=e.national_id or "",
        vkn=e.tax_number or "",
        uyruk=_ulke(e.country),
        adres=e.address or "",
        dogum_tarihi=e.birth_date,
        ek_bilgi=ek_bilgi,
        kaynak_varlik_id=str(e.id),
    )


def _tuzel_kisi(e: Entity) -> TuzelKisi:
    yurt_ici = (e.country or "TR").upper() == "TR"
    return TuzelKisi(
        baglanti="adina_yapilan",
        kurulus_nevi="ticaret_sicili" if yurt_ici else "yurt_disi",
        unvan=e.name,
        vkn=e.tax_number or "",
        sicil_no=e.mersis_number or e.trade_registry_number or "",
        kurulus_ulkesi=_ulke(e.country) or "Türkiye",
        kurulus_tarihi=e.incorporation_date,
        adres=e.address or "",
        kaynak_varlik_id=str(e.id),
    )


def iskelet_aciklama(konu: str, olgular: list[str]) -> str:
    """Açıklama için başlangıç metni: kayıtlı olgular + doldurulması gereken yer tutucular."""
    satirlar = [YONERGE, "", f"Bildirime konu: {konu}.", "", "Dosyada kayıtlı olgular:"]
    satirlar += [f"- {o}" for o in olgular] or [f"- {YER_TUTUCU}"]
    satirlar += [
        "",
        f"Şüpheyi doğuran işlem veya davranış: {YER_TUTUCU}",
        f"Yapılan araştırma ve sonuçları: {YER_TUTUCU}",
        f"Fonların kaynağı ve işlemin amacı hakkında edinilen bilgi: {YER_TUTUCU}",
    ]
    return "\n".join(satirlar)


async def onden_doldur(
    session: AsyncSession, entity: Entity, organization: Organization
) -> SibFormu:
    """Kütük, gerçek faydalanıcı hesabı ve dosyanın risk bulgularından taslak formu kurar."""
    form = SibFormu(yukumlu=Yukumlu(ad_unvan=organization.name))
    if entity.schema_type == EntitySchema.PERSON.value:
        form.gercek_kisiler.append(_gercek_kisi(entity, baglanti="kendisi_adina"))
    else:
        form.tuzel_kisiler.append(_tuzel_kisi(entity))

    olgular: list[str] = []
    ubo = await ubo_service.latest(session, entity.id)
    if ubo is not None:
        for kisi in ubo.result.get("ubos", []):
            try:
                kaynak = await session.get(Entity, uuid.UUID(kisi["entity_id"]))
            except (KeyError, ValueError):
                kaynak = None
            if kaynak is None:
                continue
            form.gercek_kisiler.append(
                _gercek_kisi(
                    kaynak,
                    baglanti="gercek_faydalanici",
                    ek_bilgi=(
                        f"Etkin pay %{kisi.get('effective_percent', '?')} "
                        "(AEGIS gerçek faydalanıcı hesabı)."
                    ),
                )
            )
        if ubo.result.get("status") == "not_determinable":
            olgular.append("Gerçek faydalanıcı mevcut kayıtlarla belirlenemedi.")

    dosya = await build_dossier(session, entity)
    olgular = [f"{b.title}: {b.rationale}" for b in dosya.risk.findings] + olgular
    form.aciklama = iskelet_aciklama(f"{entity.name} ({dosya.subject_kind_label})", olgular)
    return form


async def _referans_no(session: AsyncSession, tenant_id: uuid.UUID, yil: int) -> str:
    # Kiracı başına seri hale getir: aynı numara iki taslağa verilmesin (UNIQUE de korur).
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"aegis.sib:{tenant_id}"},
    )
    adet = await session.scalar(
        select(func.count()).select_from(SibDraft).where(SibDraft.reference_no.like(f"SIB-{yil}-%"))
    )
    return f"SIB-{yil}-{(adet or 0) + 1:04d}"


def form_oku(taslak: SibDraft) -> SibFormu:
    return SibFormu.model_validate_json(taslak.form_encrypted)


def taslak_denetle(taslak: SibDraft) -> Denetim:
    return denetle(form_oku(taslak), iskelet_ozeti=taslak.skeleton_sha256)


async def olustur(
    session: AsyncSession,
    entity: Entity,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
    retention_years: int,
) -> SibDraft:
    organization = await session.get(Organization, tenant_id)
    if organization is None:  # kimlik akışında oluşur; burada yoksa veri bozuktur
        raise SibStateError("Kuruluş kaydı bulunamadı.")
    form = await onden_doldur(session, entity, organization)
    simdi = datetime.now(UTC)
    taslak = SibDraft(
        tenant_id=tenant_id,
        entity_id=entity.id,
        reference_no=await _referans_no(session, tenant_id, simdi.year),
        status=SibStatus.DRAFT.value,
        category=None,
        form_encrypted=form.model_dump_json(),
        skeleton_sha256=metin_ozeti(form.aciklama),
        guide_version=REHBER["kod"],
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
        retention_until=simdi + timedelta(days=365 * retention_years),
    )
    session.add(taslak)
    await session.flush()
    await record_event(
        session,
        tenant_id=tenant_id,
        action=AuditAction.SIB_CREATE,
        object_type=OBJECT_TYPE,
        object_id=str(taslak.id),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        source_ref=f"entity:{entity.id}",
        payload={"reference_no": taslak.reference_no, "guide_version": taslak.guide_version},
    )
    return taslak


async def guncelle(
    session: AsyncSession,
    taslak: SibDraft,
    form: SibFormu,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
) -> Denetim:
    """Formu kaydeder (hatalı da olsa: yarım taslak kaybolmamalı). Dışa aktarılmış taslak
    düzenlenince yeniden ``taslak`` olur: son dışa aktarılan belge artık güncel değildir."""
    if taslak.status == SibStatus.CANCELLED.value:
        raise SibStateError("İptal edilmiş taslak düzenlenemez.")
    onceki_durum = taslak.status
    taslak.form_encrypted = form.model_dump_json()
    taslak.category = form.bildirim.kategori
    taslak.status = SibStatus.DRAFT.value
    taslak.updated_by_user_id = actor_user_id
    taslak.updated_at = datetime.now(UTC)
    denetim = denetle(form, iskelet_ozeti=taslak.skeleton_sha256)
    await record_event(
        session,
        tenant_id=tenant_id,
        action=AuditAction.SIB_UPDATE,
        object_type=OBJECT_TYPE,
        object_id=str(taslak.id),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        # Değer yazılmaz (kişisel veri, ve bildirimin içeriği gizlidir); yalnız durum ve sayılar.
        payload={
            "reference_no": taslak.reference_no,
            "previous_status": onceki_durum,
            "errors": len(denetim.hatalar),
            "warnings": len(denetim.uyarilar),
        },
    )
    return denetim


async def disa_aktar(
    session: AsyncSession,
    taslak: SibDraft,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
) -> tuple[bytes, str]:
    """Doğrulamadan geçen taslağı düzenlenebilir DOCX'e çevirir; (içerik, dosya adı) döner."""
    from aegis_core.sib.render import render_docx

    if taslak.status == SibStatus.CANCELLED.value:
        raise SibStateError("İptal edilmiş taslak dışa aktarılamaz.")
    form = form_oku(taslak)
    denetim = denetle(form, iskelet_ozeti=taslak.skeleton_sha256)
    if denetim.hatalar:
        raise SibExportBlockedError(denetim)
    simdi = datetime.now(UTC)
    icerik = render_docx(form, taslak.reference_no, simdi)
    taslak.status = SibStatus.EXPORTED.value
    taslak.export_count += 1
    taslak.last_exported_at = simdi
    # Açık yazılır: sunucu tarafı onupdate değeri flush'ta bayatlatır, yanıt hazırlanırken
    # async oturumda tembel yükleme MissingGreenlet verir (iptal testinde yakalandı).
    taslak.updated_at = simdi
    await record_event(
        session,
        tenant_id=tenant_id,
        action=AuditAction.SIB_EXPORT,
        object_type=OBJECT_TYPE,
        object_id=str(taslak.id),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        payload={"reference_no": taslak.reference_no, "export_count": taslak.export_count},
    )
    return icerik, f"{taslak.reference_no}-taslak.docx"


async def iptal_et(
    session: AsyncSession,
    taslak: SibDraft,
    neden: str,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
) -> None:
    """Taslak silinmez (saklama yükümlülüğü); gerekçeyle iptal edilir."""
    if taslak.status == SibStatus.CANCELLED.value:
        raise SibStateError("Taslak zaten iptal edilmiş.")
    taslak.status = SibStatus.CANCELLED.value
    taslak.cancel_reason = neden
    taslak.cancelled_at = taslak.updated_at = datetime.now(UTC)
    await record_event(
        session,
        tenant_id=tenant_id,
        action=AuditAction.SIB_CANCEL,
        object_type=OBJECT_TYPE,
        object_id=str(taslak.id),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        payload={"reference_no": taslak.reference_no, "reason": neden},
    )


async def listele(
    session: AsyncSession, *, entity_id: uuid.UUID | None = None, limit: int = 100
) -> list[tuple[SibDraft, str]]:
    # Form satır satır çözülür (ozetler): okunamayan tek taslak listeyi düşürmesin.
    sorgu = (
        select(SibDraft, Entity.name)
        .options(defer(SibDraft.form_encrypted))
        .join(Entity, Entity.id == SibDraft.entity_id)
        .order_by(SibDraft.updated_at.desc())
        .limit(limit)
    )
    if entity_id is not None:
        sorgu = sorgu.where(SibDraft.entity_id == entity_id)
    return [(t, ad) for t, ad in (await session.execute(sorgu)).all()]


async def ozetler(
    session: AsyncSession, satirlar: list[tuple[SibDraft, str]]
) -> list[dict[str, Any]]:
    """Liste özetleri. Çözülemeyen taslak yalnız kendi satırında işaretlenir, loglanır."""
    if not satirlar:
        return []
    ham = dict(
        (
            await session.execute(
                select(SibDraft.id, type_coerce(SibDraft.form_encrypted, Text)).where(
                    SibDraft.id.in_([t.id for t, _ in satirlar])
                )
            )
        )
        .tuples()
        .all()
    )
    sonuc: list[dict[str, Any]] = []
    for taslak, ad in satirlar:
        try:
            form = SibFormu.model_validate_json(get_secret_box().decrypt(ham[taslak.id]))
        except DecryptionError:
            logger.error("sib_formu_cozulemedi", draft_id=str(taslak.id))
            sonuc.append(ozet(taslak, ad, okunamadi=True))
            continue
        sonuc.append(ozet(taslak, ad, denetim=denetle(form, iskelet_ozeti=taslak.skeleton_sha256)))
    return sonuc


def ozet(
    taslak: SibDraft,
    entity_name: str,
    *,
    denetim: Denetim | None = None,
    okunamadi: bool = False,
) -> dict[str, Any]:
    if denetim is None and not okunamadi:
        denetim = taslak_denetle(taslak)
    return {
        "id": taslak.id,
        "entity_id": taslak.entity_id,
        "entity_name": entity_name,
        "reference_no": taslak.reference_no,
        "status": taslak.status,
        "category": taslak.category,
        "errors": len(denetim.hatalar) if denetim else 0,
        "warnings": len(denetim.uyarilar) if denetim else 0,
        "unreadable": okunamadi,
        "export_count": taslak.export_count,
        "last_exported_at": taslak.last_exported_at,
        "updated_at": taslak.updated_at,
        "created_at": taslak.created_at,
    }
