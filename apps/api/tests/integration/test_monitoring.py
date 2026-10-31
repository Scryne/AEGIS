"""İzleme-lite (E2.4): taban koşusu, sentetik veri kümesi değişikliği → tam bir doğru alarm, onay.

ROADMAP E2.4 kabul ölçütü: *"Synthetic diff test (injected dataset change produces exactly one
correct alert)"*. yente ``httpx.MockTransport`` ile taklit edilir; iki koşu arasında taklidin
döndürdüğü liste değiştirilir.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from aegis_core.screening.yente import YenteClient

pytestmark = pytest.mark.integration

BASE_RESULTS: list[dict[str, Any]] = [
    {
        "id": "NK-PEP",
        "caption": "Deniz Ticaret",
        "schema": "Company",
        "score": 0.72,
        "match": False,
        "datasets": ["default"],
        "properties": {"topics": ["role.pep"]},
    },
    {
        "id": "NK-LOW",
        "caption": "Denizli Ticaret",
        "schema": "Company",
        "score": 0.55,
        "match": False,
        "datasets": ["default"],
        "properties": {},
    },
]


def _install(client: TestClient, results: list[dict[str, Any]]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"responses": {f"s{i}": {"status": 200, "results": results} for i in range(4)}},
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://yente")
    client.app.state.yente_client = YenteClient("http://yente", client=http)


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


def test_injected_dataset_change_produces_exactly_one_alert(api_client: TestClient) -> None:
    token = _register(api_client, "izleme1")
    entity = api_client.post(
        "/api/v1/entities",
        json={"name": "Deniz Ticaret A.Ş.", "schema_type": "Company"},
        headers=_auth(token),
    ).json()["entity"]
    watched = api_client.put(
        f"/api/v1/entities/{entity['id']}/monitoring",
        json={"monitored": True},
        headers=_auth(token),
    )
    assert watched.json()["monitored"] is True
    assert api_client.get(f"/api/v1/entities/{entity['id']}", headers=_auth(token)).json()[
        "monitored"
    ]

    _install(api_client, BASE_RESULTS)
    first = api_client.post("/api/v1/monitoring/run", headers=_auth(token)).json()
    assert first == {"checked": 1, "alerts": 0, "failed": 0}  # taban koşusu

    again = api_client.post("/api/v1/monitoring/run", headers=_auth(token)).json()
    assert again["alerts"] == 0  # değişiklik yok → alarm yok

    changed = [
        *BASE_RESULTS,
        {
            "id": "NK-SANCTION-NEW",
            "caption": "Deniz Ticaret Ltd",
            "schema": "Company",
            "score": 0.93,
            "match": True,
            "datasets": ["default"],
            "properties": {"topics": ["sanction"]},
        },
    ]
    _install(api_client, changed)
    third = api_client.post("/api/v1/monitoring/run", headers=_auth(token)).json()
    assert third["alerts"] == 1

    listing = api_client.get("/api/v1/monitoring/alerts", headers=_auth(token)).json()
    assert listing["open_count"] == 1
    (alert,) = listing["items"]
    assert [(i["kind"], i["external_id"]) for i in alert["items"]] == [
        ("new_match", "NK-SANCTION-NEW")
    ]
    assert alert["entity_name"] == "Deniz Ticaret A.Ş."

    short = api_client.post(
        f"/api/v1/monitoring/alerts/{alert['id']}/acknowledge",
        json={"note": "x"},
        headers=_auth(token),
    )
    assert short.status_code in (400, 422)
    ack = api_client.post(
        f"/api/v1/monitoring/alerts/{alert['id']}/acknowledge",
        json={"note": "Eşleşme incelemeye alındı."},
        headers=_auth(token),
    ).json()
    assert ack["status"] == "acknowledged"
    assert (
        api_client.get("/api/v1/monitoring/alerts", headers=_auth(token)).json()["open_count"] == 0
    )

    fourth = api_client.post("/api/v1/monitoring/run", headers=_auth(token)).json()
    assert fourth["alerts"] == 0  # aynı yeni kayıt tekrar alarm üretmez

    events = api_client.get(
        "/api/v1/audit/events", params={"action": "monitoring.alert"}, headers=_auth(token)
    ).json()
    assert events["total"] == 1


def test_unwatched_entities_are_not_screened(api_client: TestClient) -> None:
    token = _register(api_client, "izleme2")
    api_client.post(
        "/api/v1/entities",
        json={"name": "İzlenmeyen A.Ş.", "schema_type": "Company"},
        headers=_auth(token),
    )
    _install(api_client, BASE_RESULTS)
    assert api_client.post("/api/v1/monitoring/run", headers=_auth(token)).json()["checked"] == 0
