"""Olumsuz haber betası (E2.5, ADR-0013): bayrak, toplama, tekrar yok, insan kararı, oran sınırı.

Haber kaynağı taklitle değiştirilir (``app.state.news_provider``); ağ yok.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from aegis_core.adverse_media.source import NewsHit

pytestmark = pytest.mark.integration


class SahteKaynak:
    name = "sahte"

    def __init__(self, hits: list[NewsHit], fail_on: str | None = None) -> None:
        self.hits = hits
        self.fail_on = fail_on
        self.queries: list[str] = []

    async def search(self, query: str, limit: int) -> list[NewsHit]:
        self.queries.append(query)
        if self.fail_on and self.fail_on in query:
            raise RuntimeError("kaynak düştü")
        return self.hits[:limit]


HITS = [
    NewsHit(
        "Deniz Ticaret yöneticisi gözaltına alındı",
        "https://h.example/1",
        "Gazete A",
        datetime(2025, 10, 16, tzinfo=UTC),
    ),
    NewsHit("Deniz Ticaret ihracat rekoru kırdı", "https://h.example/2", "Gazete B", None),
]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, slug: str) -> str:
    email = f"u@{slug}.com"
    client.post(
        "/api/v1/auth/register",
        json={"org_name": slug, "org_slug": slug, "email": email, "password": "sifre-12345"},
    )
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "sifre-12345"})
    return str(login.json()["access_token"])


def _entity(client: TestClient, token: str) -> str:
    return str(
        client.post(
            "/api/v1/entities",
            json={"name": "Deniz Ticaret A.Ş.", "schema_type": "Company"},
            headers=_auth(token),
        ).json()["entity"]["id"]
    )


def test_beta_flag_scan_dedupe_and_review(api_client: TestClient) -> None:
    token = _register(api_client, "haber1")
    eid = _entity(api_client, token)
    kaynak = SahteKaynak(HITS)
    api_client.app.state.news_provider = kaynak  # type: ignore[attr-defined]

    kapali = api_client.post(f"/api/v1/entities/{eid}/adverse-media/scan", headers=_auth(token))
    assert kapali.status_code == 409  # beta kapalı
    assert kaynak.queries == []  # kapalıyken dış kaynağa gidilmez

    ac = api_client.put("/api/v1/adverse-media/beta", json={"enabled": True}, headers=_auth(token))
    assert ac.json() == {"enabled": True}

    r = api_client.post(f"/api/v1/entities/{eid}/adverse-media/scan", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["queries"][0] == '"Deniz Ticaret"'  # hukuki ek atıldı
    assert (r.json()["fetched"], r.json()["new"]) == (4, 2)  # iki sorgu, aynı iki haber

    liste = api_client.get(f"/api/v1/entities/{eid}/adverse-media", headers=_auth(token)).json()
    assert liste["counts"] == {"aday": 2, "ilgili": 0, "ilgisiz": 0}
    first = liste["items"][0]
    assert first["negative_terms"] == ["gözaltı"]  # olumsuz terimli aday önce

    cok_kisa = api_client.post(
        f"/api/v1/adverse-media/{first['id']}/review",
        json={"decision": "ilgili", "note": "evet"},
        headers=_auth(token),
    )
    assert cok_kisa.status_code == 422  # gerekçe zorunlu
    karar = api_client.post(
        f"/api/v1/adverse-media/{first['id']}/review",
        json={"decision": "ilgili", "note": "Şirketin genel müdürü, haberde adıyla geçiyor."},
        headers=_auth(token),
    )
    assert karar.json()["status"] == "ilgili"

    # Hemen yeniden tarama oran sınırına takılır.
    tekrar = api_client.post(f"/api/v1/entities/{eid}/adverse-media/scan", headers=_auth(token))
    assert tekrar.status_code == 429
    assert "Retry-After" in tekrar.headers

    events = api_client.get(
        "/api/v1/audit/events", params={"action": "adverse_media.review"}, headers=_auth(token)
    ).json()
    assert events["total"] == 1

    # Risk puanına girmez: aday/karar puan girdilerini değiştirmez.
    puan = api_client.get(f"/api/v1/entities/{eid}/risk-score", headers=_auth(token))
    assert "adverse" not in puan.text.lower()


def test_partial_source_failure_keeps_other_query(api_client: TestClient) -> None:
    token = _register(api_client, "haber2")
    eid = _entity(api_client, token)
    api_client.put("/api/v1/adverse-media/beta", json={"enabled": True}, headers=_auth(token))
    api_client.app.state.news_provider = SahteKaynak(HITS, fail_on="OR")  # type: ignore[attr-defined]

    r = api_client.post(f"/api/v1/entities/{eid}/adverse-media/scan", headers=_auth(token))
    assert r.status_code == 200
    assert (r.json()["new"], len(r.json()["failed_queries"])) == (
        2,
        1,
    )  # biri düştü, diğeri yazıldı
