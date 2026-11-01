"""Kullanım ölçümü ve ay sonu dökümü (E3.5) uçtan uca.

Faz 3 çıkış ölçütü 3'ün "doğru kota hesabı" kısmı: ekran, API anahtarı ve toplu taramanın sorguları
kaynağına göre sayılır, toplam mevcut kota sayacıyla aynıdır, dönem kapanınca döküm donar.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from aegis_core.billing import metering
from aegis_core.billing.metering import warning_level
from aegis_core.billing.service import _period
from aegis_core.db.tenant import set_tenant_context
from aegis_core.screening.yente import YenteClient

pytestmark = pytest.mark.integration


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, slug: str) -> tuple[str, str]:
    email = f"u@{slug}.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={"org_name": slug, "org_slug": slug, "email": email, "password": "sifre-12345"},
    )
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "sifre-12345"})
    return str(login.json()["access_token"]), str(reg.json()["tenant_id"])


def _yente(client: TestClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        queries = json.loads(request.content)["queries"]
        return httpx.Response(
            200, json={"responses": {k: {"status": 200, "results": []} for k in queries}}
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://yente")
    client.app.state.yente_client = YenteClient("http://yente", client=http)  # type: ignore[attr-defined]


def _entity(client: TestClient, headers: dict[str, str], name: str) -> str:
    return str(
        client.post(
            "/api/v1/entities", json={"name": name, "schema_type": "Company"}, headers=headers
        ).json()["entity"]["id"]
    )


async def _close(app_url: str, tenant: str, now: datetime) -> Any:
    engine = create_async_engine(app_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session, session.begin():
            await set_tenant_context(session, uuid.UUID(tenant))
            return await metering.close_previous_period(session, uuid.UUID(tenant), now=now)
    finally:
        await engine.dispose()


def test_usage_breakdown_by_source_and_period_close(
    api_client: TestClient, app_database_url: str
) -> None:
    token, tenant = _register(api_client, "olcum1")
    _yente(api_client)
    h = _auth(token)

    # Ekran: 1 tarama (1 özne).
    api_client.post(
        f"/api/v1/screenings/from-entity/{_entity(api_client, h, 'Ekran A.Ş.')}", headers=h
    )
    # API anahtarı: 1 tarama.
    key = api_client.post(
        "/api/v1/api-keys", json={"name": "ERP", "role": "analyst"}, headers=h
    ).json()["key"]
    kh = {"X-API-Key": key}
    api_client.post(
        f"/api/v1/screenings/from-entity/{_entity(api_client, kh, 'Api Ltd.')}", headers=kh
    )
    # Toplu: 2 satır.
    body = "Ad\r\nToplu Bir A.Ş.\r\nToplu İki Ltd.\r\n".encode()
    bid = api_client.post(
        "/api/v1/batches",
        files={"file": ("t.csv", body, "text/csv")},
        data={"mapping": json.dumps({"name": "Ad"})},
        headers=h,
    ).json()["id"]
    api_client.post(f"/api/v1/batches/{bid}/start", headers=h)
    api_client.post(f"/api/v1/batches/{bid}/process", headers=h)

    # Motor kapalıyken denenen tarama "yapılamadı" kaydedilir ama hak tüketmez.
    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    http = httpx.AsyncClient(transport=httpx.MockTransport(down), base_url="http://yente")
    api_client.app.state.yente_client = YenteClient("http://yente", client=http)  # type: ignore[attr-defined]
    failed = api_client.post(
        f"/api/v1/screenings/from-entity/{_entity(api_client, h, 'Kesinti A.Ş.')}", headers=h
    )
    assert failed.status_code == 502

    usage = api_client.get("/api/v1/billing/usage", headers=h).json()
    assert usage["used_queries"] == 4
    assert usage["breakdown"] == {
        "queries_total": 4,
        "queries_screen": 1,
        "queries_api": 1,
        "queries_batch": 2,
        "batch_rows": 2,
    }
    assert usage["warning"] == "ok"

    # Dönem kapanışı: sonraki ayın içinden bakınca bu ay "önceki dönem"dir; ikinci kez kapanmaz.
    start, end = _period(datetime.now(UTC))
    next_month = end + timedelta(days=3)
    row = asyncio.run(_close(app_database_url, tenant, next_month))
    assert row is not None
    assert (row.used_queries, row.included_queries, row.overage_queries) == (4, 300, 0)
    assert row.period_start == start
    assert row.breakdown["queries_batch"] == 2
    assert asyncio.run(_close(app_database_url, tenant, next_month)) is None

    stmts = api_client.get("/api/v1/billing/statements", headers=h).json()
    assert [s["used_queries"] for s in stmts] == [4]
    assert api_client.get("/api/v1/billing/statements", headers=kh).status_code == 403
    other, _ = _register(api_client, "olcum1b")
    assert api_client.get("/api/v1/billing/statements", headers=_auth(other)).json() == []


def test_warning_levels() -> None:
    assert warning_level(0, 300, False) == "ok"
    assert warning_level(239, 300, False) == "ok"
    assert warning_level(240, 300, False) == "near"
    assert warning_level(300, 300, False) == "exhausted"
    assert warning_level(310, 300, True) == "overage"
    assert warning_level(5, 0, True) == "ok"
