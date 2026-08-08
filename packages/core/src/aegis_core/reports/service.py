"""Rapor üretim akışı — topla → oluştur → sakla → denetle (E1.5).

Akış tek yerde durur ki hiçbir adım atlanamasın:

1. ``dossier.build_dossier`` içeriği toplar ve kural tabanlı risk özetini hesaplar.
2. ``render`` PDF ya da Word üretir (senkron kütüphaneler; ``asyncio.to_thread``).
3. Dosya nesne deposuna yazılır — veritabanına ASLA (bkz. ``documents.storage``).
4. ``report`` satırı, ``sha256`` bütünlük kanıtı + ``retention_until`` saklama saatiyle
   yazılır; risk özeti ve veri kümesi sürümleri **donar**.
5. Tam olarak **bir** ``report.export`` denetim olayı yazılır (Invariant 2): rapor dışa
   aktarma risk-etkileyen bir eylemdir, çünkü kurumun denetime sunduğu belge budur.

Olay ile ``report`` satırı aynı transaction'da commit olur (çağıranın
``get_tenant_session``'ı); dosya deposuna yazma bundan **önce** yapılır, böylece
"veritabanında kaydı var ama dosyası yok" durumu oluşmaz. Tersi (depoda öksüz nesne)
kabul edilebilir ve saklama süresi imhasında (E3.7) temizlenir.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.config import Settings
from aegis_core.documents.storage import (
    ensure_bucket,
    put_object,
    safe_filename,
    sha256_hex,
)
from aegis_core.logging import get_logger
from aegis_core.models import (
    REPORT_CONTENT_TYPES,
    AuditAction,
    Entity,
    Report,
    ReportFormat,
    ReportType,
)
from aegis_core.reports.dossier import DossierData, build_dossier
from aegis_core.reports.render import render_dossier_docx, render_dossier_pdf
from aegis_core.services import audit as audit_service

logger = get_logger("aegis.reports.service")

# ``risk_rationale`` kolonunun sınırı; özet cümlesi bundan uzun olamaz.
MAX_RATIONALE_LENGTH = 1024


def build_report_storage_key(
    tenant_id: uuid.UUID, report_id: uuid.UUID, subject_name: str, extension: str
) -> str:
    """Rapor için nesne anahtarı üretir (belgelerle aynı kiracı-önekli şema)."""
    now = datetime.now(UTC)
    slug = safe_filename(f"dosya-{subject_name}") or "dosya"
    return f"{tenant_id}/reports/{now:%Y}/{now:%m}/{report_id}-{slug}.{extension}"


def render_dossier(data: DossierData, report_format: ReportFormat) -> bytes:
    """İstenen biçimde rapor baytlarını üretir (senkron; iş parçacığında çağrılır)."""
    if report_format is ReportFormat.PDF:
        return render_dossier_pdf(data)
    return render_dossier_docx(data)


async def create_dossier_report(
    session: AsyncSession,
    entity: Entity,
    *,
    tenant_id: uuid.UUID,
    report_format: ReportFormat,
    settings: Settings,
    actor_user_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    generated_by: str | None = None,
    organization_name: str | None = None,
    retention_years: int = 5,
) -> Report:
    """Bir varlık için durum tespiti dosyasını üretir, saklar ve denetim olayı yazar.

    Oturum kiracı bağlamlı olmalıdır (RLS). Nesne deposu erişilemezse ``StorageError``
    yükselir ve **hiçbir satır yazılmaz** — kaydı olup dosyası olmayan rapor üretilmez.
    """
    data = await build_dossier(
        session,
        entity,
        generated_by=generated_by,
        organization_name=organization_name,
    )

    # reportlab/python-docx senkrondur; olay döngüsü bloke edilmez.
    payload = await asyncio.to_thread(render_dossier, data, report_format)

    report_id = uuid.uuid4()
    key = build_report_storage_key(tenant_id, report_id, entity.name, report_format.value)
    content_type = REPORT_CONTENT_TYPES[report_format.value]
    await asyncio.to_thread(ensure_bucket, settings)
    stored = await asyncio.to_thread(put_object, key, payload, content_type, settings)

    report = Report(
        id=report_id,
        tenant_id=tenant_id,
        entity_id=entity.id,
        report_type=ReportType.DOSSIER.value,
        report_format=report_format.value,
        title=data.title,
        risk_level=data.risk.level.value,
        risk_rationale=data.risk.rationale[:MAX_RATIONALE_LENGTH],
        risk_findings=data.risk.to_payload(),
        screening_ids=[str(item) for item in data.screening_ids],
        dataset_versions=data.dataset_versions,
        storage_key=stored.key,
        content_type=content_type,
        size_bytes=stored.size_bytes,
        sha256=sha256_hex(payload),
        generated_by_user_id=actor_user_id,
        retention_until=datetime.now(UTC) + timedelta(days=365 * retention_years),
    )
    session.add(report)
    await session.flush()

    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.REPORT_EXPORT,
        object_type="report",
        object_id=str(report.id),
        # Kaynak referansı bütünlük kanıtıdır: denetimde sunulan dosyanın bu satırla
        # aynı dosya olduğu özetten gösterilir.
        source_ref=f"sha256:{report.sha256}",
        payload={
            "entity_id": str(entity.id),
            "entity_name": entity.name,
            "report_type": report.report_type,
            "format": report.report_format,
            "risk_level": report.risk_level,
            "finding_codes": [str(finding.get("code")) for finding in report.risk_findings],
            "screening_ids": list(report.screening_ids),
            "dataset_versions": report.dataset_versions,
            "size_bytes": report.size_bytes,
        },
    )
    logger.info(
        "rapor_uretildi",
        report_id=str(report.id),
        entity_id=str(entity.id),
        format=report.report_format,
        risk_level=report.risk_level,
    )
    return report


async def get_report(session: AsyncSession, report_id: uuid.UUID) -> Report | None:
    """Tek bir raporu döndürür (RLS ile kiracıya sınırlı)."""
    report: Report | None = await session.scalar(select(Report).where(Report.id == report_id))
    return report


async def list_reports(
    session: AsyncSession,
    *,
    entity_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Report]:
    """Raporları en yeniden eskiye listeler (isteğe bağlı varlık süzgeciyle)."""
    statement = select(Report)
    if entity_id is not None:
        statement = statement.where(Report.entity_id == entity_id)
    result = await session.scalars(
        statement.order_by(Report.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result)


async def count_reports(session: AsyncSession, *, entity_id: uuid.UUID | None = None) -> int:
    """Rapor sayısı (sayfalama için)."""
    statement = select(func.count()).select_from(Report)
    if entity_id is not None:
        statement = statement.where(Report.entity_id == entity_id)
    total = await session.scalar(statement)
    return int(total or 0)
