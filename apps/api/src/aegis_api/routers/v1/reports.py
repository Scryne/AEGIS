"""/api/v1/reports — risk özeti ve durum tespiti dosyası (E1.5).

İki ayrı şey vardır ve ayrı kalmaları önemlidir:

- ``GET /reports/risk/{entity_id}`` — **canlı** risk özeti. Her çağrıda kurallar yeniden
  koşar, hiçbir şey saklanmaz, denetim olayı **yazılmaz**: bu bir okuma işlemidir ve
  denetim izini gürültüyle doldurmamalıdır.
- ``POST /reports/dossier`` — **dışa aktarma**. Dosya üretilir, nesne deposunda donar,
  ``report`` satırı bütünlük özetiyle yazılır ve tam olarak bir ``report.export`` olayı
  düşer. Kurumun denetime sunduğu belge budur.

Salt-okunur denetçi (``auditor``) rapor **okuyabilir** ama üretemez: üretim, kütüğe satır
yazan ve denetim olayı doğuran bir eylemdir.

İndirme, belgelerdeki gibi **kısa ömürlü imzalı URL** ile yapılır; dosya API üzerinden
akıtılmaz.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from aegis_api.dependencies import (
    Principal,
    PrincipalDep,
    SessionDep,
    SettingsDep,
    TenantSessionDep,
    require_role,
)
from aegis_api.errors import NotFoundError, ValidationFailedError
from aegis_core.documents.storage import StorageError, presigned_url
from aegis_core.entities import service as entity_service
from aegis_core.models import Organization, Report, ReportFormat, Role, User
from aegis_core.reports import service as report_service
from aegis_core.reports.dossier import build_dossier
from aegis_core.reports.render import ReportRenderError
from aegis_core.reports.risk import RISK_LEVEL_LABELS, RiskAssessment, RiskLevel

router = APIRouter(prefix="/reports", tags=["reports"])

RequireReportWrite = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.ANALYST))
]


# ── Şemalar ──────────────────────────────────────────────────────────────────


class RiskFindingResponse(BaseModel):
    """Kuralın ürettiği tek bulgu (arayüzde madde olarak gösterilir)."""

    code: str
    title: str
    rationale: str
    level: str | None
    """``null`` = bulgu risk seviyesini yükseltmez, yalnız işaret eder."""

    needs_action: bool
    source_refs: list[str]


class RiskSummaryResponse(BaseModel):
    """Kural tabanlı risk özeti (şeffaf, öğrenmesiz — bkz. ADR-0008)."""

    entity_id: uuid.UUID
    level: str
    level_label: str
    rationale: str
    complete: bool
    """Karar bekleyen bulgu yoksa ``true``; dosyanın tamamlanıp tamamlanmadığı."""

    findings: list[RiskFindingResponse]


class ReportResponse(BaseModel):
    """Üretilmiş rapor kaydı."""

    id: uuid.UUID
    entity_id: uuid.UUID | None
    report_type: str
    report_format: str
    title: str
    risk_level: str
    risk_level_label: str
    risk_rationale: str
    risk_findings: list[dict[str, Any]]
    screening_ids: list[str]
    dataset_versions: dict[str, Any]
    content_type: str
    size_bytes: int
    sha256: str
    """Bütünlük kanıtı: indirilen dosyanın bu raporla aynı olduğu buradan doğrulanır."""

    retention_until: datetime | None
    created_at: datetime


class ReportDownloadResponse(BaseModel):
    """Kısa ömürlü indirme bağlantısı."""

    url: str
    expires_in_seconds: int
    sha256: str


class DossierRequest(BaseModel):
    """Dosya dışa aktarma isteği."""

    entity_id: uuid.UUID
    report_format: Literal["pdf", "docx"] = "pdf"


# ── Dönüştürücüler ───────────────────────────────────────────────────────────


def _risk_response(entity_id: uuid.UUID, assessment: RiskAssessment) -> RiskSummaryResponse:
    return RiskSummaryResponse(
        entity_id=entity_id,
        level=assessment.level.value,
        level_label=assessment.level_label,
        rationale=assessment.rationale,
        complete=assessment.complete,
        findings=[
            RiskFindingResponse(
                code=finding.code,
                title=finding.title,
                rationale=finding.rationale,
                level=finding.level.value if finding.level else None,
                needs_action=finding.needs_action,
                source_refs=list(finding.source_refs),
            )
            for finding in assessment.findings
        ],
    )


def _report_response(report: Report) -> ReportResponse:
    level = RiskLevel(report.risk_level)
    return ReportResponse(
        id=report.id,
        entity_id=report.entity_id,
        report_type=report.report_type,
        report_format=report.report_format,
        title=report.title,
        risk_level=report.risk_level,
        risk_level_label=RISK_LEVEL_LABELS[level],
        risk_rationale=report.risk_rationale,
        risk_findings=list(report.risk_findings),
        screening_ids=list(report.screening_ids),
        dataset_versions=dict(report.dataset_versions),
        content_type=report.content_type,
        size_bytes=report.size_bytes,
        sha256=report.sha256,
        retention_until=report.retention_until,
        created_at=report.created_at,
    )


async def _actor_label(session: AsyncSession, user_id: uuid.UUID) -> str | None:
    """Raporun kapağına yazılacak "üreten" bilgisi (ad, yoksa e-posta)."""
    row = (
        await session.execute(select(User.full_name, User.email).where(User.id == user_id))
    ).first()
    if row is None:
        return None
    label: str | None = row.full_name or row.email
    return label


async def _organization_name(session: AsyncSession, tenant_id: uuid.UUID) -> str | None:
    """Raporu üreten kurumun adı (kimlik düzlemi tablosu, RLS'siz)."""
    name: str | None = await session.scalar(
        select(Organization.name).where(Organization.id == tenant_id)
    )
    return name


# ── Uçlar ────────────────────────────────────────────────────────────────────


@router.get("/risk/{entity_id}", response_model=RiskSummaryResponse)
async def get_risk_summary(
    entity_id: uuid.UUID, _principal: PrincipalDep, session: TenantSessionDep
) -> RiskSummaryResponse:
    """Varlığın canlı risk özetini döndürür (kurallar her çağrıda yeniden koşar).

    Hiçbir şey saklanmaz ve denetim olayı yazılmaz — bu bir okuma işlemidir. Dosyanın
    kanıt niteliğindeki hâli için ``POST /reports/dossier`` kullanılır.
    """
    entity = await entity_service.get_entity(session, entity_id)
    if entity is None:
        raise NotFoundError("Varlık bulunamadı.")
    data = await build_dossier(session, entity)
    return _risk_response(entity_id, data.risk)


@router.post("/dossier", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def export_dossier(
    body: DossierRequest,
    principal: RequireReportWrite,
    session: TenantSessionDep,
    identity_session: SessionDep,
    settings: SettingsDep,
) -> ReportResponse:
    """Durum tespiti dosyasını PDF ya da Word olarak üretir, saklar ve denetime yazar."""
    entity = await entity_service.get_entity(session, body.entity_id)
    if entity is None:
        raise NotFoundError("Varlık bulunamadı.")

    try:
        report = await report_service.create_dossier_report(
            session,
            entity,
            tenant_id=principal.tenant_id,
            report_format=ReportFormat(body.report_format),
            settings=settings,
            actor_user_id=principal.user_id,
            actor_role=principal.role.value,
            generated_by=await _actor_label(identity_session, principal.user_id),
            organization_name=await _organization_name(identity_session, principal.tenant_id),
            retention_years=settings.document_retention_years,
        )
    except ReportRenderError as exc:
        raise ValidationFailedError(f"Rapor üretilemedi: {exc}") from exc
    except StorageError as exc:
        # Depoya yazılamadıysa hiçbir satır yazılmaz: kaydı olup dosyası olmayan
        # rapor üretmeyiz (bkz. reports.service modül başlığı).
        raise ValidationFailedError(f"Rapor saklanamadı: {exc}") from exc
    return _report_response(report)


@router.get("", response_model=list[ReportResponse])
async def list_reports(
    _principal: PrincipalDep,
    session: TenantSessionDep,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ReportResponse]:
    """Üretilmiş raporları en yeniden eskiye listeler."""
    rows = await report_service.list_reports(
        session, entity_id=entity_id, limit=limit, offset=offset
    )
    return [_report_response(row) for row in rows]


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: uuid.UUID, _principal: PrincipalDep, session: TenantSessionDep
) -> ReportResponse:
    """Tek bir raporun kaydını döndürür."""
    report = await report_service.get_report(session, report_id)
    if report is None:
        raise NotFoundError("Rapor bulunamadı.")
    return _report_response(report)


@router.get("/{report_id}/download", response_model=ReportDownloadResponse)
async def download_report(
    report_id: uuid.UUID,
    _principal: PrincipalDep,
    session: TenantSessionDep,
    settings: SettingsDep,
) -> ReportDownloadResponse:
    """Rapor için kısa ömürlü imzalı indirme bağlantısı üretir.

    ``sha256`` birlikte döner: indirilen dosyanın kayıtla aynı olduğu doğrulanabilir.
    """
    report = await report_service.get_report(session, report_id)
    if report is None:
        raise NotFoundError("Rapor bulunamadı.")
    ttl = settings.document_download_url_ttl_seconds
    try:
        url = await run_in_threadpool(
            presigned_url, report.storage_key, expires_in=ttl, settings=settings
        )
    except StorageError as exc:
        raise ValidationFailedError(f"İndirme bağlantısı üretilemedi: {exc}") from exc
    return ReportDownloadResponse(url=url, expires_in_seconds=ttl, sha256=report.sha256)
