"""Denetim izi servisi — hash zinciri yazımı ve doğrulaması (CLAUDE.md Invariant 2).

Her olay, kiracı-başına bir hash zincirinin halkasıdır::

    row_hash = SHA256( canonical( seq, aktör, eylem, hedef, kaynak, payload,
                                  occurred_at, prev_hash ) )

``prev_hash`` ilk halkada ``GENESIS_HASH``tir. Kurcalama tespiti: ``verify_chain`` tüm
zinciri baştan yeniden hesaplar; tek bir alan bile değişmişse ilgili halka (ve sonrası)
tutmaz. Bu, UPDATE/DELETE trigger'ını devre dışı bırakabilen bir DBA'ya karşı savunmadır.

**Eşzamanlılık:** ``record_event`` kiracı başına bir transaction-scoped advisory kilit
alır; böylece ``seq`` ve ``prev_hash`` ataması yarışa girmez. Kilit, çağıranın
transaction'ı commit edince serbest kalır (olay, iş değişikliğiyle atomiktir).

**Determinizm notu:** ``payload`` JSON round-trip'e dayanıklı olmalıdır (Decimal/NaN
değil; standart str/int/float/bool/dict/list). Değerler Python → JSONB → Python
dönüşünde korunur ve ``sort_keys`` anahtar sırasını sabitler, bu yüzden yazım ve
doğrulama aynı hash'i üretir.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.models import AuditAction, AuditEvent

# Zincirin ilk halkasının prev_hash'i (64 hex sıfır) ve kanonik biçim sürümü.
GENESIS_HASH = "0" * 64
CHAIN_VERSION = 1


@dataclass(frozen=True)
class ChainVerification:
    """``verify_chain`` sonucu."""

    ok: bool
    events_checked: int
    broken_seq: int | None = None
    reason: str | None = None


def _compute_row_hash(event: AuditEvent) -> str:
    """Bir olayın saklanan alanlarından kanonik row_hash'i (yeniden) hesaplar.

    Yazım ve doğrulama TEK bu fonksiyonu kullanır → biçim kayması olamaz.
    ``occurred_at`` UTC'ye normalize edilir; ``ensure_ascii=False`` (proje dili Türkçe).
    """
    canonical = json.dumps(
        {
            "v": CHAIN_VERSION,
            "seq": event.seq,
            "tenant_id": str(event.tenant_id),
            "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
            "actor_role": event.actor_role,
            "action": event.action,
            "object_type": event.object_type,
            "object_id": event.object_id,
            "source_ref": event.source_ref,
            "payload": event.payload,
            "occurred_at": event.occurred_at.astimezone(UTC).isoformat(),
            "prev_hash": event.prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def record_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    action: AuditAction,
    object_type: str,
    object_id: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    source_ref: str | None = None,
    payload: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> AuditEvent:
    """Zincire bir denetim olayı ekler (kiracı bağlamı ayarlı, transaction'lı oturumda).

    Çağıranın açık transaction'ı içinde çalışmalıdır (ör. ``get_tenant_session``); olay,
    denetlenen iş değişikliğiyle aynı transaction'da commit olur.
    """
    # Kiracı başına seri hale getir: seq/prev_hash ataması yarışmasın.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"aegis.audit:{tenant_id}"},
    )

    # Son halka (RLS zaten yalnız bu kiracının satırlarını gösterir).
    last = (
        await session.execute(
            select(AuditEvent.seq, AuditEvent.row_hash).order_by(AuditEvent.seq.desc()).limit(1)
        )
    ).first()
    if last is None:
        seq = 1
        prev_hash = GENESIS_HASH
    else:
        seq = last.seq + 1
        prev_hash = last.row_hash

    event = AuditEvent(
        tenant_id=tenant_id,
        seq=seq,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action.value,
        object_type=object_type,
        object_id=object_id,
        source_ref=source_ref,
        payload=payload or {},
        occurred_at=occurred_at or datetime.now(UTC),
        prev_hash=prev_hash,
        row_hash="",  # hemen aşağıda hesaplanır
    )
    event.row_hash = _compute_row_hash(event)
    session.add(event)
    await session.flush()
    return event


async def list_events(
    session: AsyncSession,
    *,
    action: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditEvent]:
    """Denetim olaylarını en yeniden eskiye listeler (E1.5 denetim görüntüleyicisi).

    Sıralama ``seq`` üzerindendir, ``occurred_at`` üzerinden değil: ``seq`` zincirin
    gerçek sırasıdır ve aynı saniyeye düşen iki olayı da kesin sıralar.
    """
    statement = select(AuditEvent)
    if action:
        statement = statement.where(AuditEvent.action == action)
    if object_type:
        statement = statement.where(AuditEvent.object_type == object_type)
    if object_id:
        statement = statement.where(AuditEvent.object_id == object_id)
    if actor_user_id is not None:
        statement = statement.where(AuditEvent.actor_user_id == actor_user_id)
    if occurred_from is not None:
        statement = statement.where(AuditEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        statement = statement.where(AuditEvent.occurred_at <= occurred_to)
    result = await session.scalars(
        statement.order_by(AuditEvent.seq.desc()).limit(limit).offset(offset)
    )
    return list(result)


async def count_events(
    session: AsyncSession,
    *,
    action: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
) -> int:
    """Süzgeçlere uyan olay sayısı (sayfalama için)."""
    statement = select(func.count()).select_from(AuditEvent)
    if action:
        statement = statement.where(AuditEvent.action == action)
    if object_type:
        statement = statement.where(AuditEvent.object_type == object_type)
    if object_id:
        statement = statement.where(AuditEvent.object_id == object_id)
    if actor_user_id is not None:
        statement = statement.where(AuditEvent.actor_user_id == actor_user_id)
    if occurred_from is not None:
        statement = statement.where(AuditEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        statement = statement.where(AuditEvent.occurred_at <= occurred_to)
    total = await session.scalar(statement)
    return int(total or 0)


async def verify_chain(session: AsyncSession) -> ChainVerification:
    """Aktif kiracının hash zincirini baştan doğrular (RLS ile o kiracıyla sınırlı).

    ``seq`` 1'den başlamalı ve boşluksuz olmalı; her halkanın ``prev_hash``'i öncekinin
    ``row_hash``'ine eşit olmalı; her ``row_hash`` saklanan alanlardan yeniden
    hesaplananla birebir tutmalıdır. İlk kopuşta durur ve nedenini bildirir.
    """
    events = list(await session.scalars(select(AuditEvent).order_by(AuditEvent.seq)))
    expected_prev = GENESIS_HASH
    expected_seq = 1
    for index, event in enumerate(events):
        if event.seq != expected_seq:
            return ChainVerification(
                ok=False, events_checked=index, broken_seq=event.seq, reason="seq_gap"
            )
        if event.prev_hash != expected_prev:
            return ChainVerification(
                ok=False, events_checked=index, broken_seq=event.seq, reason="prev_hash_mismatch"
            )
        if _compute_row_hash(event) != event.row_hash:
            return ChainVerification(
                ok=False, events_checked=index, broken_seq=event.seq, reason="row_hash_mismatch"
            )
        expected_prev = event.row_hash
        expected_seq += 1
    return ChainVerification(ok=True, events_checked=len(events))
