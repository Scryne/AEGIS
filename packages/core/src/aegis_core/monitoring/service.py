"""İzleme-lite servisi (E2.4): izleme bayrağı, yeniden tarama + fark, alarm, onay.

Akış (varlık başına, gece senkronundan sonra): kütükteki özneler ve kiracı eşikleriyle elle
taramayla **aynı** koşu (``screening.entity_run``) → aynı varlığın önceki tamamlanmış koşusuyla
yapısal fark (``monitoring.diff``) → önemliyse ``monitoring_alert`` + denetim olayı.

Önceki koşunun kararları: gece koşuları insan tarafından incelenmeyebilir; bu yüzden önceki
koşunun her adayına, o kaydın **en son insan kararı** (varlığın tüm geçmişinden) uygulanır.
Böylece bir kez elenen yanlış pozitif her gece yeniden alarm üretmez.

Eposta kanalı yoktur (projede SMTP altyapısı yok); alarm uygulama içinde listelenir.

Tam izleme (E3.1, ADR-0014): alarm yazılınca derecesi (``monitoring/severity.py``) belirlenir,
varlığın risk puanı yeniden kayda geçirilir (önceki/sonraki alarmda saklanır) ve ``critical`` /
``high`` alarm bir vaka açar (``critical`` → EDD işaretli). Hepsi aynı alt işlemde: biri
başarısız olursa alarm da yazılmaz, gece koşusu ertesi gün aynı farkı yeniden bulur.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.cases import service as case_service
from aegis_core.config import Settings
from aegis_core.logging import get_logger
from aegis_core.models import (
    AlertStatus,
    AuditAction,
    Entity,
    EntityStatus,
    MatchCandidate,
    MonitoringAlert,
    MonitoringRun,
    Screening,
    ScreeningStatus,
)
from aegis_core.monitoring.diff import CandidateView, diff_candidates
from aegis_core.monitoring.severity import RANK, Severity, alert_severity
from aegis_core.reports import score_service
from aegis_core.screening import service as screening_service
from aegis_core.screening.entity_run import load_thresholds, subjects_for_entity
from aegis_core.screening.yente import YenteClient
from aegis_core.services import audit as audit_service
from aegis_core.webhooks import service as webhook_service

logger = get_logger("aegis.monitoring")


async def set_monitored(
    session: AsyncSession,
    entity: Entity,
    monitored: bool,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
) -> Entity:
    if entity.monitored == monitored:
        return entity
    entity.monitored = monitored
    await session.flush()
    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.MONITORING_TOGGLE,
        object_type="entity",
        object_id=str(entity.id),
        payload={"monitored": monitored},
    )
    return entity


async def _human_decisions(
    session: AsyncSession, entity_id: uuid.UUID
) -> dict[tuple[str, str], str]:
    rows = await session.execute(
        select(MatchCandidate.subject_key, MatchCandidate.external_id, MatchCandidate.decision)
        .join(Screening, Screening.id == MatchCandidate.screening_id)
        .where(
            Screening.entity_id == entity_id,
            MatchCandidate.decided_automatically.is_(False),
            MatchCandidate.decision != "pending",
        )
        .order_by(MatchCandidate.reviewed_at.asc().nulls_first())
    )
    return {(key, ext): decision for key, ext, decision in rows}


async def _views(
    session: AsyncSession, screening_id: uuid.UUID, decisions: dict[tuple[str, str], str] | None
) -> list[CandidateView]:
    candidates = await screening_service.list_candidates(session, screening_id)
    views = []
    for c in candidates:
        decision = c.decision
        if decisions is not None and (c.subject_key, c.external_id) in decisions:
            decision = decisions[(c.subject_key, c.external_id)]
        views.append(
            CandidateView(
                subject_key=c.subject_key,
                subject_name=c.subject_name,
                external_id=c.external_id,
                caption=c.caption,
                score=c.score,
                topics=tuple(c.topics or ()),
                decision=decision,
                decided_automatically=c.decided_automatically,
            )
        )
    return views


async def _previous_completed(session: AsyncSession, entity_id: uuid.UUID) -> Screening | None:
    """Bu koşudan önceki son tamamlanmış koşu (yeni koşu başlamadan okunur)."""
    row: Screening | None = await session.scalar(
        select(Screening)
        .where(
            Screening.entity_id == entity_id,
            Screening.status == ScreeningStatus.COMPLETED.value,
        )
        .order_by(Screening.created_at.desc(), Screening.id.desc())
        .limit(1)
    )
    return row


class _Unavailable:
    """Varlık taranamadı: temiz sonuçtan ayrı tutulur, koşu kaydına yazılır."""


UNAVAILABLE = _Unavailable()


async def monitor_entity(
    session: AsyncSession,
    client: YenteClient,
    *,
    tenant_id: uuid.UUID,
    entity: Entity,
    settings: Settings,
) -> MonitoringAlert | _Unavailable | None:
    """Varlığı yeniden tarar; önceki koşuya göre önemli fark varsa alarm yazar."""
    previous = await _previous_completed(session, entity.id)
    screening = await screening_service.run_screening(
        session,
        client,
        tenant_id=tenant_id,
        subjects=await subjects_for_entity(session, entity),
        thresholds=await load_thresholds(session),
        dataset=settings.yente_dataset,
        algorithm=settings.yente_algorithm,
        requested_by_user_id=None,
        requested_by_role="monitoring",
        entity_id=entity.id,
        retention_years=settings.document_retention_years,
        limit=settings.screening_candidate_limit,
    )
    if screening.status != ScreeningStatus.COMPLETED.value:
        logger.warning("izleme_taramasi_basarisiz", entity_id=str(entity.id))
        # Sonuç YOK temiz demek değildir. Hata fırlatılmaz: başarısız tarama kaydı ve
        # denetim olayı savepoint geri alınınca kaybolurdu.
        return UNAVAILABLE
    if previous is None:
        logger.info("izleme_taban_koşusu", entity_id=str(entity.id))
        return None  # ilk koşu taban çizgisidir; karşılaştıracak bir şey yok

    decisions = await _human_decisions(session, entity.id)
    diff = diff_candidates(
        await _views(session, previous.id, decisions), await _views(session, screening.id, None)
    )
    if not diff.material:
        return None
    diff_dict = diff.to_dict()
    severity = alert_severity(diff_dict["items"])
    alert = MonitoringAlert(
        tenant_id=tenant_id,
        entity_id=entity.id,
        screening_id=screening.id,
        previous_screening_id=previous.id,
        diff=diff_dict,
        status=AlertStatus.OPEN.value,
        severity=severity.value,
    )
    session.add(alert)
    await session.flush()
    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        actor_role="monitoring",
        action=AuditAction.MONITORING_ALERT,
        object_type="monitoring_alert",
        object_id=str(alert.id),
        payload={
            "entity_id": str(entity.id),
            "screening_id": str(screening.id),
            "previous_screening_id": str(previous.id),
            "kinds": sorted({i.kind for i in diff.items}),
            "severity": severity.value,
        },
    )

    # Otomatik yeniden değerlendirme: puan kayda geçer, alarm önce/sonra farkını taşır.
    before = await score_service.latest_snapshot(session, entity.id)
    snap, created = await score_service.snapshot(
        session,
        tenant_id=tenant_id,
        entity=entity,
        reason="monitoring_alert",
        actor_user_id=None,
        actor_role="monitoring",
        high_risk_countries=settings.high_risk_countries,
        retention_years=settings.document_retention_years,
    )
    alert.reassessment = {
        "snapshot_id": str(snap.id),
        "score_before": before.score if before else None,
        "band_before": before.band if before else None,
        "score_after": snap.score,
        "band_after": snap.band,
        "recorded_new": created,
    }

    case = None
    if RANK[severity] >= RANK[Severity.HIGH]:
        case = await case_service.open_from_alert(
            session, tenant_id=tenant_id, alert=alert, entity=entity, severity=severity.value
        )
    await webhook_service.emit(
        session,
        tenant_id=tenant_id,
        event="alert.raised",
        data={
            "alert_id": str(alert.id),
            "entity_id": str(entity.id),
            "severity": severity.value,
            "kinds": sorted({i.kind for i in diff.items}),
            "case_id": str(case.id) if case else None,
        },
    )
    await session.flush()
    return alert


async def monitored_entities(session: AsyncSession) -> list[Entity]:
    rows = await session.scalars(
        select(Entity)
        .where(Entity.monitored.is_(True), Entity.status == EntityStatus.ACTIVE.value)
        .order_by(Entity.created_at)
    )
    return list(rows)


async def _recently_checked(
    session: AsyncSession, entity_id: uuid.UUID, *, since: datetime
) -> bool:
    found = await session.scalar(
        select(Screening.id)
        .where(
            Screening.entity_id == entity_id,
            # Kullanıcısız koşu izleme ya da sistem taramasıdır; elle tarama tekrarı engellemez.
            Screening.requested_by_user_id.is_(None),
            Screening.status == ScreeningStatus.COMPLETED.value,
            Screening.created_at >= since,
        )
        .limit(1)
    )
    return found is not None


async def _attempt(
    session: AsyncSession,
    client: YenteClient,
    *,
    tenant_id: uuid.UUID,
    entity: Entity,
    settings: Settings,
) -> tuple[bool, str | None]:
    """Tek varlık, tek deneme: (alarm üretti mi, hata nedeni)."""
    try:
        async with session.begin_nested():
            alert = await monitor_entity(
                session, client, tenant_id=tenant_id, entity=entity, settings=settings
            )
        if isinstance(alert, _Unavailable):
            return False, "Tarama motoruna ulaşılamadı; sonuç yok."
        return alert is not None, None
    except Exception:  # bir varlığın hatası diğerlerini durdurmaz
        logger.exception("izleme_varlik_hatasi", entity_id=str(entity.id))
        return False, "Beklenmeyen hata; ayrıntı sunucu kaydında."


async def run_for_tenant(
    session: AsyncSession,
    client: YenteClient,
    *,
    tenant_id: uuid.UUID,
    settings: Settings,
    trigger: str = "manual",
) -> dict[str, int]:
    """İzlenen varlıkları tarar, koşu kaydını yazar.

    Gece koşusu görev yeniden teslim edilirse aynı varlığı iki kez taramaz; elle koşu hep tarar.
    Düşen varlıklar döngü sonunda bir kez daha denenir: geçici motor kesintisi dosyayı kaçırmasın.
    Kalıcı hata ``failures`` içinde kalır (işlenemeyen iş kuyruğu); sonraki koşu yeniden dener.
    """
    started = datetime.now(UTC)
    clock = time.monotonic()
    since = started - timedelta(hours=settings.monitoring_recheck_after_hours)
    checked = alerts = skipped = 0
    pending: list[tuple[Entity, str]] = []
    for entity in await monitored_entities(session):
        if trigger == "nightly" and await _recently_checked(session, entity.id, since=since):
            skipped += 1
            continue
        checked += 1
        raised, reason = await _attempt(
            session, client, tenant_id=tenant_id, entity=entity, settings=settings
        )
        alerts += int(raised)
        if reason is not None:
            pending.append((entity, reason))
    first_pass_ms = int((time.monotonic() - clock) * 1000)

    retried = len(pending)
    failures: list[dict[str, str]] = []
    for entity, _first_reason in pending:
        raised, reason = await _attempt(
            session, client, tenant_id=tenant_id, entity=entity, settings=settings
        )
        alerts += int(raised)
        if reason is not None:
            failures.append(
                {"entity_id": str(entity.id), "entity_name": entity.name, "reason": reason}
            )

    finished = datetime.now(UTC)
    duration_ms = int((time.monotonic() - clock) * 1000)
    session.add(
        MonitoringRun(
            tenant_id=tenant_id,
            trigger=trigger,
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
            checked=checked,
            skipped=skipped,
            alerts=alerts,
            failed=len(failures),
            retried=retried,
            failures=failures,
            stages={"first_pass_ms": first_pass_ms, "retry_ms": duration_ms - first_pass_ms},
        )
    )
    await session.flush()
    logger.info(
        "izleme_kosusu",
        tenant_id=str(tenant_id),
        trigger=trigger,
        checked=checked,
        skipped=skipped,
        alerts=alerts,
        failed=len(failures),
        retried=retried,
        duration_ms=duration_ms,
    )
    return {"checked": checked, "alerts": alerts, "failed": len(failures), "skipped": skipped}


async def latest_runs(session: AsyncSession, *, limit: int = 7) -> list[MonitoringRun]:
    rows = await session.scalars(
        select(MonitoringRun).order_by(MonitoringRun.started_at.desc()).limit(limit)
    )
    return list(rows)


def severity_of(alert: MonitoringAlert) -> Severity:
    """Kayıtlı derece; 0012 öncesi satırda farktan yeniden hesaplanır."""
    if alert.severity:
        return Severity(alert.severity)
    return alert_severity(alert.diff.get("items", []))


async def list_alerts(
    session: AsyncSession,
    *,
    status: str | None,
    entity_id: uuid.UUID | None,
    limit: int,
    severity: str | None = None,
) -> list[MonitoringAlert]:
    query = select(MonitoringAlert).order_by(MonitoringAlert.created_at.desc()).limit(limit)
    if status:
        query = query.where(MonitoringAlert.status == status)
    if severity:
        query = query.where(MonitoringAlert.severity == severity)
    if entity_id:
        query = query.where(MonitoringAlert.entity_id == entity_id)
    return list(await session.scalars(query))


async def count_open(session: AsyncSession) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(MonitoringAlert)
            .where(MonitoringAlert.status == AlertStatus.OPEN.value)
        )
        or 0
    )


async def acknowledge(
    session: AsyncSession,
    alert: MonitoringAlert,
    *,
    tenant_id: uuid.UUID,
    note: str,
    actor_user_id: uuid.UUID,
    actor_role: str | None,
) -> MonitoringAlert:
    if alert.status == AlertStatus.ACKNOWLEDGED.value:
        return alert
    alert.status = AlertStatus.ACKNOWLEDGED.value
    alert.acknowledged_by_user_id = actor_user_id
    alert.acknowledged_at = datetime.now(UTC)
    alert.acknowledge_note = note
    await session.flush()
    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.MONITORING_ACK,
        object_type="monitoring_alert",
        object_id=str(alert.id),
        payload={"note": note},
    )
    return alert
