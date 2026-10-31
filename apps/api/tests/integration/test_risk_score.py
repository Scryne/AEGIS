"""Risk puanı uçları (E2.3): canlı döküm, anlık görüntü, değişim tetiği, RBAC, izolasyon."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from aegis_core.security.tokens import create_access_token

pytestmark = pytest.mark.integration


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, slug: str) -> tuple[str, str]:
    email = f"u@{slug}.com"
    register = client.post(
        "/api/v1/auth/register",
        json={"org_name": slug, "org_slug": slug, "email": email, "password": "sifre-12345"},
    )
    assert register.status_code == 201, register.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "sifre-12345"})
    return register.json()["tenant_id"], login.json()["access_token"]


def _entity(client: TestClient, token: str, name: str, schema: str, **extra: object) -> str:
    response = client.post(
        "/api/v1/entities",
        json={"name": name, "schema_type": schema, **extra},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["entity"]["id"])


def test_score_breakdown_snapshot_and_ubo_trigger(api_client: TestClient) -> None:
    tenant, token = _register(api_client, "puan1")
    sirket = _entity(api_client, token, "Northwind B.V.", "Company", country="NL")

    live = api_client.get(f"/api/v1/reports/score/{sirket}", headers=_auth(token))
    assert live.status_code == 200, live.text
    body = live.json()
    codes = {f["code"]: f["points"] for f in body["factors"]}
    assert codes == {"screening.missing": 15, "ubo.missing": 10, "jurisdiction.foreign": 5}
    assert (body["score"], body["band"], body["recorded"]) == (30, "medium", False)
    assert body["complete"] is False
    assert body["history"] == []
    assert all(f["reason"] for f in body["factors"])

    first = api_client.post(f"/api/v1/reports/score/{sirket}/snapshot", headers=_auth(token)).json()
    assert first["recorded"] is True
    assert len(first["history"]) == 1
    same = api_client.post(f"/api/v1/reports/score/{sirket}/snapshot", headers=_auth(token)).json()
    assert len(same["history"]) == 1  # döküm değişmedi → yeni satır yok

    kisi = _entity(api_client, token, "Jan de Vries", "Person")
    api_client.post(
        f"/api/v1/entities/{sirket}/relationships",
        json={"source_entity_id": kisi, "rel_type": "shareholder", "ownership_percent": 100},
        headers=_auth(token),
    )
    assert (
        api_client.post(f"/api/v1/entities/{sirket}/ubo", headers=_auth(token)).status_code == 201
    )

    after = api_client.get(f"/api/v1/reports/score/{sirket}", headers=_auth(token)).json()
    assert "ubo.missing" not in {f["code"] for f in after["factors"]}
    assert after["score"] == 20
    assert after["recorded"] is True  # UBO hesabı değişen puanı kendisi kayda geçirdi
    assert [h["reason"] for h in after["history"]] == ["ubo_compute", "manual"]
    assert [h["score"] for h in after["history"]] == [20, 30]

    events = api_client.get(
        "/api/v1/audit/events", params={"action": "risk_score.snapshot"}, headers=_auth(token)
    ).json()
    assert events["total"] == 2

    auditor = create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant),
        role="auditor",
        secret=os.environ["AUTH_SECRET"],
        expires_in_minutes=60,
    )
    assert (
        api_client.get(f"/api/v1/reports/score/{sirket}", headers=_auth(auditor)).status_code == 200
    )
    denied = api_client.post(f"/api/v1/reports/score/{sirket}/snapshot", headers=_auth(auditor))
    assert denied.status_code == 403


def test_score_is_tenant_isolated(api_client: TestClient) -> None:
    _a, token_a = _register(api_client, "puana")
    _b, token_b = _register(api_client, "puanb")
    sirket = _entity(api_client, token_a, "Gizli Ltd.", "Company", country="TR")
    assert (
        api_client.get(f"/api/v1/reports/score/{sirket}", headers=_auth(token_b)).status_code == 404
    )
