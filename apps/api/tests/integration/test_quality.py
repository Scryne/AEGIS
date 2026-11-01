"""Eşleşme kalitesi programı (E3.6) uçtan uca: insan kararı → ölçüm → kayıt → eğilim."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from aegis_core.screening.yente import YenteClient
from aegis_core.security.tokens import create_access_token

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


def _yente(client: TestClient, scores: list[float]) -> None:
    results: list[dict[str, Any]] = [
        {
            "id": f"Q-{i}",
            "caption": f"Aday {i}",
            "schema": "Company",
            "score": s,
            "match": s >= 0.85,
            "datasets": ["default"],
            "properties": {},
        }
        for i, s in enumerate(scores)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        queries = json.loads(request.content)["queries"]
        return httpx.Response(
            200, json={"responses": {k: {"status": 200, "results": results} for k in queries}}
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://yente")
    client.app.state.yente_client = YenteClient("http://yente", client=http)  # type: ignore[attr-defined]


def test_quality_measures_human_decisions_and_tracks_trend(api_client: TestClient) -> None:
    token, tenant = _register(api_client, "kalite1")
    empty = api_client.get("/api/v1/quality/matching", headers=_auth(token)).json()
    assert empty["matching"]["total"] == 0
    assert empty["matching"]["recommendation"]["status"] == "insufficient"

    _yente(api_client, [0.95, 0.88, 0.72, 0.68, 0.55])
    entity = api_client.post(
        "/api/v1/entities",
        json={"name": "Batı Kimya A.Ş.", "schema_type": "Company"},
        headers=_auth(token),
    ).json()["entity"]
    run = api_client.post(
        f"/api/v1/screenings/from-entity/{entity['id']}", headers=_auth(token)
    ).json()
    by_ext = {c["external_id"]: c for c in run["candidates"]}

    def decide(ext: str, decision: str) -> None:
        res = api_client.post(
            f"/api/v1/screenings/{run['id']}/candidates/{by_ext[ext]['id']}/decision",
            json={"decision": decision, "note": "Belge karşılaştırması yapıldı."},
            headers=_auth(token),
        )
        assert res.status_code == 200, res.text

    decide("Q-0", "confirmed")
    decide("Q-1", "dismissed")
    q = api_client.get("/api/v1/quality/matching", headers=_auth(token)).json()
    m = q["matching"]
    # 0.55 aday otomatik elendi (eşik 0.65): doğrusu bilinmez, metriğe girmez.
    assert (m["total"], m["auto_dismissed"], m["confirmed"], m["dismissed"], m["pending"]) == (
        5,
        1,
        1,
        1,
        2,
    )
    assert m["false_positive_rate"] == 0.5
    assert m["flag_precision"] == 0.5
    assert q["thresholds"]["auto_dismiss_below"] == 0.65
    assert len(m["sweep"]) == 19

    first = api_client.post("/api/v1/quality/matching/snapshot", headers=_auth(token))
    assert first.status_code == 201
    # Geri besleme: yeni eleme kararı bir sonraki ölçüme kendiliğinden girer.
    decide("Q-2", "dismissed")
    decide("Q-3", "dismissed")
    api_client.post("/api/v1/quality/matching/snapshot", headers=_auth(token))
    hist = api_client.get("/api/v1/quality/matching", headers=_auth(token)).json()["history"]
    assert [h["label_count"] for h in hist] == [2, 4]
    assert hist[0]["metrics"]["false_positive_rate"] == 0.5
    assert hist[1]["metrics"]["false_positive_rate"] == 0.75
    assert "sweep" not in hist[1]["metrics"]

    events = api_client.get(
        "/api/v1/audit/events", params={"action": "quality.snapshot"}, headers=_auth(token)
    ).json()["items"]
    assert len(events) == 2

    analyst = create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant),
        role="analyst",
        secret=os.environ["AUTH_SECRET"],
        expires_in_minutes=60,
    )
    assert api_client.get("/api/v1/quality/matching", headers=_auth(analyst)).status_code == 403
    other, _ = _register(api_client, "kalite1b")
    assert api_client.get("/api/v1/quality/matching", headers=_auth(other)).json()["history"] == []


def test_weekly_worker_snapshot(api_client: TestClient) -> None:
    import asyncio

    from aegis_worker.tasks.quality import _run

    token, _ = _register(api_client, "kalite2")
    result = asyncio.run(_run())
    assert result["failed"] == 0
    assert result["tenants"] >= 1
    hist = api_client.get("/api/v1/quality/matching", headers=_auth(token)).json()["history"]
    assert [h["reason"] for h in hist] == ["weekly"]
