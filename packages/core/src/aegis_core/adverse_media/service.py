"""Olumsuz haber betası servisi (E2.5, ADR-0013): sorgu kurma, toplama, ayıklama.

Zaman kutusu kuralı (ROADMAP E2.5): LLM hattı (kimlik ayrımı → olumsuzluk sınıflaması → kanıt
cümlesi) Phase 3'e kaldı; bu sürüm **toplama + elle ayıklama**dır. Başlıktaki olumsuz terimler
yalnız sıralama ipucudur, karar değildir. Hiçbir aday risk puanına girmez; dosyaya ancak bir
insan "ilgili" dediğinde bağlanır.

Bayrak: kiracı ayarı ``adverse_media_beta`` (``{"enabled": true}``); kapalıyken uçlar 409 döner.
Aynı varlık için arka arkaya tarama dış kaynağı yormasın diye 5 dakikalık aralık uygulanır.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.adverse_media.source import NewsProvider
from aegis_core.models import (
    AdverseMediaItem,
    AdverseMediaStatus,
    AuditAction,
    AuditEvent,
    Entity,
    EntitySchema,
    TenantSetting,
)
from aegis_core.screening.normalization import turkish_lower
from aegis_core.services.audit import record_event

BETA_KEY = "adverse_media_beta"
SCAN_INTERVAL = timedelta(minutes=5)
PER_QUERY_LIMIT = 30
OBJECT_TYPE = "adverse_media"

# Kök biçimler (Türkçe küçük harf): başlıkta alt dize olarak aranır.
NEGATIVE_TERMS: tuple[str, ...] = (
    "dolandır",
    "gözaltı",
    "tutukla",
    "soruşturma",
    "iddianame",
    "kara para",
    "aklama",
    "rüşvet",
    "yolsuzluk",
    "kaçakçılık",
    "vergi kaçır",
    "sahte",
    "iflas",
    "konkordato",
    "yaptırım",
    "terör",
    "suç örgütü",
    "hapis",
    "operasyon",
    "el kondu",
    "el koy",
    "kayyum",
    "haciz",
    "firari",
    "zimmet",
    "ihaleye fesat",
    "hakkında dava",
    "mahkûm",
    "mahkum",
)
_ARAMA_TERIMLERI = (
    "dolandırıcılık",
    "gözaltı",
    "tutuklandı",
    "soruşturma",
    "kara para",
    "rüşvet",
    "yolsuzluk",
    "kaçakçılık",
    "iflas",
    "yaptırım",
)
_SIRKET_EKI = re.compile(
    r"(\s+(anonim|limited|kollektif|komandit)\s+şirketi|\s+a\.?\s?ş\.?|\s+ltd\.?(\s+şti\.?)?"
    r"|\s+şti\.?|\s+san\.?(\s+ve)?\s+tic\.?|\s+sanayi\s+ve\s+ticaret|\s+holding)+\s*$",
    re.IGNORECASE,
)


class BetaDisabledError(Exception):
    """Kiracı betayı açmamış."""


class ScanTooSoonError(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"Bu varlık az önce tarandı; {retry_after} sn sonra yeniden deneyin.")
        self.retry_after = retry_after


@dataclass(frozen=True)
class ScanResult:
    queries: list[str]
    fetched: int
    new: int
    failed_queries: list[str]


def core_name(name: str, schema_type: str) -> str:
    """Şirket adından hukuki ekleri atar (arama için); kişi adı olduğu gibi kalır."""
    ad = " ".join(name.split())
    if schema_type == EntitySchema.COMPANY.value:
        kisa = _SIRKET_EKI.sub("", ad).strip(" ,.")
        if len(kisa) >= 4:
            return kisa
    return ad


def build_queries(name: str, schema_type: str) -> list[str]:
    """İki sorgu: adın kendisi (güncel haber) ve ad + olumsuz terim grubu (hedefli)."""
    ad = core_name(name, schema_type)
    grup = " OR ".join(f'"{t}"' if " " in t else t for t in _ARAMA_TERIMLERI)
    return [f'"{ad}"', f'"{ad}" ({grup})']


def negative_terms(title: str) -> list[str]:
    alt = turkish_lower(title)
    return [t for t in NEGATIVE_TERMS if t in alt]


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


async def beta_enabled(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    ayar = await session.scalar(
        select(TenantSetting).where(
            TenantSetting.tenant_id == tenant_id, TenantSetting.key == BETA_KEY
        )
    )
    return bool(ayar and ayar.value.get("enabled"))


async def set_beta(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    enabled: bool,
    actor_user_id: uuid.UUID,
    actor_role: str,
) -> None:
    ayar = await session.scalar(
        select(TenantSetting).where(
            TenantSetting.tenant_id == tenant_id, TenantSetting.key == BETA_KEY
        )
    )
    if ayar is None:
        session.add(TenantSetting(tenant_id=tenant_id, key=BETA_KEY, value={"enabled": enabled}))
    else:
        ayar.value = {"enabled": enabled}
    await session.flush()
    await record_event(
        session,
        tenant_id=tenant_id,
        action=AuditAction.ADVERSE_MEDIA_BETA,
        object_type=OBJECT_TYPE,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        payload={"enabled": enabled},
    )


async def _last_scan(session: AsyncSession, entity_id: uuid.UUID) -> datetime | None:
    son: datetime | None = await session.scalar(
        select(AuditEvent.occurred_at)
        .where(
            AuditEvent.action == AuditAction.ADVERSE_MEDIA_SCAN.value,
            AuditEvent.object_id == str(entity_id),
        )
        .order_by(AuditEvent.occurred_at.desc())
        .limit(1)
    )
    return son


async def scan(
    session: AsyncSession,
    provider: NewsProvider,
    entity: Entity,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    actor_role: str,
    now: datetime | None = None,
) -> ScanResult:
    if not await beta_enabled(session, tenant_id):
        raise BetaDisabledError
    now = now or datetime.now(UTC)
    son = await _last_scan(session, entity.id)
    if son is not None and now - son < SCAN_INTERVAL:
        raise ScanTooSoonError(int((SCAN_INTERVAL - (now - son)).total_seconds()) + 1)

    queries = build_queries(entity.name, entity.schema_type)
    fetched = new = 0
    failed: list[str] = []
    for q in queries:
        try:
            hits = await provider.search(q, PER_QUERY_LIMIT)
        except Exception:
            failed.append(q)
            continue
        fetched += len(hits)
        for h in hits:
            sonuc = await session.execute(
                pg_insert(AdverseMediaItem)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    entity_id=entity.id,
                    url=h.url,
                    url_hash=url_hash(h.url),
                    title=h.title,
                    source_name=h.source_name,
                    published_at=h.published_at,
                    query=q,
                    provider=provider.name,
                    negative_terms=negative_terms(h.title),
                )
                .on_conflict_do_nothing(constraint="uq_adverse_media_item_url")
                .returning(AdverseMediaItem.id)
            )
            if sonuc.scalar() is not None:
                new += 1
    await record_event(
        session,
        tenant_id=tenant_id,
        action=AuditAction.ADVERSE_MEDIA_SCAN,
        object_type="entity",
        object_id=str(entity.id),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        source_ref=f"provider:{provider.name}",
        payload={"queries": queries, "fetched": fetched, "new": new, "failed": failed},
        occurred_at=now,
    )
    return ScanResult(queries, fetched, new, failed)


async def list_items(
    session: AsyncSession, entity_id: uuid.UUID, status: str | None = None
) -> list[AdverseMediaItem]:
    stmt = select(AdverseMediaItem).where(AdverseMediaItem.entity_id == entity_id)
    if status:
        stmt = stmt.where(AdverseMediaItem.status == status)
    # İlgili önce, sonra olumsuz terim taşıyan adaylar, sonra en yeni.
    rows = list((await session.execute(stmt)).scalars().all())
    sira = {AdverseMediaStatus.RELEVANT.value: 0, AdverseMediaStatus.CANDIDATE.value: 1}
    rows.sort(
        key=lambda i: (
            sira.get(i.status, 2),
            -len(i.negative_terms),
            -(i.published_at.timestamp() if i.published_at else 0),
        )
    )
    return rows


async def review(
    session: AsyncSession,
    item: AdverseMediaItem,
    *,
    decision: AdverseMediaStatus,
    note: str,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    actor_role: str,
) -> AdverseMediaItem:
    onceki = item.status
    item.status = decision.value
    item.review_note = note
    item.reviewed_by_user_id = actor_user_id
    item.reviewed_at = datetime.now(UTC)
    await session.flush()
    await record_event(
        session,
        tenant_id=tenant_id,
        action=AuditAction.ADVERSE_MEDIA_REVIEW,
        object_type=OBJECT_TYPE,
        object_id=str(item.id),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        source_ref=f"entity:{item.entity_id}",
        payload={"from": onceki, "to": decision.value, "url_hash": item.url_hash},
    )
    return item
