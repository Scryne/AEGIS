"""Fatura dönemi Türkiye saatine göre ay (E2.6, ADR-0012)."""

from __future__ import annotations

from datetime import UTC, datetime

from aegis_core.billing.plans import DEFAULT_PLAN, get_plan
from aegis_core.billing.service import _period


def test_period_follows_istanbul_month_not_utc() -> None:
    # UTC'de 31 Ekim 22:30 = İstanbul'da 1 Kasım 01:30 → Kasım dönemi.
    start, end = _period(datetime(2026, 10, 31, 22, 30, tzinfo=UTC))
    assert (start.year, start.month, start.day, start.hour) == (2026, 11, 1, 0)
    assert start.astimezone(UTC) == datetime(2026, 10, 31, 21, 0, tzinfo=UTC)
    assert (end.month, end.day) == (12, 1)


def test_period_year_rollover() -> None:
    start, end = _period(datetime(2026, 12, 15, 9, 0, tzinfo=UTC))
    assert (start.month, end.year, end.month) == (12, 2027, 1)


def test_unknown_plan_falls_back_to_default() -> None:
    assert get_plan("yok").code == DEFAULT_PLAN
    assert get_plan(None).code == DEFAULT_PLAN
