"""Saklama süresi kuru çalışma raporu (E3.7): sayar, kayda geçirir, hiçbir şey silmez."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration


def test_dry_run_counts_expired_and_deletes_nothing(
    api_client: TestClient, admin_database_url: str
) -> None:
    from aegis_worker.tasks.retention import _run

    email = "u@saklama.com"
    reg = api_client.post(
        "/api/v1/auth/register",
        json={"org_name": "s", "org_slug": "saklama1", "email": email, "password": "sifre-12345"},
    )
    tenant = reg.json()["tenant_id"]
    token = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "sifre-12345"}
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    ids = [
        api_client.post(
            "/api/v1/entities", json={"name": n, "schema_type": "Company"}, headers=h
        ).json()["entity"]["id"]
        for n in ("Eski Kayıt A.Ş.", "Güncel Kayıt A.Ş.")
    ]
    # Birinin saklama süresini geçmişe çek (ayrıcalıklı bağlantı; uygulama rolü RLS'ye tabi).
    engine = create_engine(admin_database_url)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE entity SET retention_until = now() - interval '1 day' WHERE id = :i"),
            {"i": ids[0]},
        )

    result = asyncio.run(_run())
    assert result["disposed"] == 0
    assert result["failed"] == 0

    with engine.connect() as conn:
        still = conn.execute(
            text("SELECT count(*) FROM entity WHERE tenant_id = :t"), {"t": tenant}
        ).scalar()
    engine.dispose()
    assert still == 2  # hiçbir şey silinmedi

    events = api_client.get(
        "/api/v1/audit/events", params={"action": "retention.dry_run"}, headers=h
    ).json()["items"]
    assert len(events) == 1
    payload = events[0]["payload"]
    assert payload["mode"] == "dry_run"
    assert payload["candidates"]["entity"] == 1
    assert payload["total"] == 1
