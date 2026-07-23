"""Denetim hash zinciri birim testleri: kanonik row_hash determinizmi + hassasiyet.

Docker gerektirmez — ORM örneği oturumsuz kurulur ve saf hash fonksiyonu sınanır.
Amaç: kanonik biçmi kilitlemek (yazım↔doğrulama kayması regresyonunu yakalamak).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from aegis_core.models import AuditEvent
from aegis_core.services.audit import GENESIS_HASH, _compute_row_hash


def _event(**overrides: object) -> AuditEvent:
    base: dict[str, object] = {
        "tenant_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "seq": 1,
        "actor_user_id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
        "actor_role": "owner",
        "action": "tenant_setting.update",
        "object_type": "tenant_setting",
        "object_id": "risk-esigi",
        "source_ref": None,
        "payload": {"value": {"threshold": 0.85}},
        "occurred_at": datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC),
        "prev_hash": GENESIS_HASH,
    }
    base.update(overrides)
    return AuditEvent(**base)


def test_hash_is_deterministic_and_sha256_hex() -> None:
    digest = _compute_row_hash(_event())
    assert digest == _compute_row_hash(_event())  # aynı girdi → aynı hash
    assert len(digest) == 64  # SHA-256 hex
    assert int(digest, 16) >= 0  # geçerli hex


def test_payload_change_breaks_hash() -> None:
    assert _compute_row_hash(_event()) != _compute_row_hash(
        _event(payload={"value": {"threshold": 999}})
    )


def test_prev_hash_links_the_chain() -> None:
    # prev_hash farklıysa row_hash da farklı olmalı (halkalar birbirine bağlanır).
    assert _compute_row_hash(_event()) != _compute_row_hash(_event(prev_hash="a" * 64))


def test_payload_key_order_is_irrelevant() -> None:
    # sort_keys sayesinde anahtar sırası hash'i etkilemez (JSONB round-trip'e dayanıklı).
    a = _compute_row_hash(_event(payload={"a": 1, "b": 2}))
    b = _compute_row_hash(_event(payload={"b": 2, "a": 1}))
    assert a == b


def test_timezone_normalized_to_utc() -> None:
    # Aynı an, farklı tzinfo ofsetiyle verilse de aynı hash (astimezone(UTC) normalize).
    from datetime import timedelta, timezone

    utc_event = _event(occurred_at=datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC))
    plus3 = _event(occurred_at=datetime(2026, 7, 23, 15, 0, 0, tzinfo=timezone(timedelta(hours=3))))
    assert _compute_row_hash(utc_event) == _compute_row_hash(plus3)
