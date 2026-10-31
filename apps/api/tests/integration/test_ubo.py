"""UBO uçları (E2.1): CTE ile zincir toplama, döngü, anlık görüntü, denetim olayı, RBAC.

Saf hesabın kenar durumları ``packages/core/tests/test_ubo_compute.py``'dedir; burada
veritabanı yolu sınanır: CTE'nin katmanları ve döngüyü doğru toplaması, bitmiş bağların
hesaba girmemesi, sonucun girdileriyle saklanması ve olay zincirine yazılması.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

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


def _entity(client: TestClient, token: str, name: str, schema: str, **extra: Any) -> str:
    response = client.post(
        "/api/v1/entities",
        json={"name": name, "schema_type": schema, **extra},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["entity"]["id"]


def _owns(
    client: TestClient, token: str, owner: str, owned: str, pct: float | None, **extra: Any
) -> None:
    body: dict[str, Any] = {"source_entity_id": owner, "rel_type": "shareholder", **extra}
    if pct is not None:
        body["ownership_percent"] = pct
    response = client.post(
        f"/api/v1/entities/{owned}/relationships", json=body, headers=_auth(token)
    )
    assert response.status_code == 201, response.text


def test_layered_structure_with_cycle(api_client: TestClient) -> None:
    _tenant, token = _register(api_client, "ubo1")
    hedef = _entity(api_client, token, "Hedef A.Ş.", "Company")
    holding = _entity(api_client, token, "Anadolu Holding A.Ş.", "Company")
    capraz = _entity(api_client, token, "Çapraz Yatırım Ltd. Şti.", "Company")
    ali = _entity(api_client, token, "Ali Veli", "Person")
    ayse = _entity(api_client, token, "Ayşe Kaya", "Person")
    eski = _entity(api_client, token, "Eski Ortak", "Person")

    _owns(api_client, token, holding, hedef, 70)
    _owns(api_client, token, ayse, hedef, 30)
    _owns(api_client, token, ali, holding, 60)
    _owns(api_client, token, capraz, holding, 40)
    _owns(api_client, token, holding, capraz, 100)  # döngü: Holding ↔ Çapraz
    _owns(api_client, token, eski, hedef, 90, end_date="2020-01-01")  # bitmiş bağ sayılmaz

    response = api_client.post(f"/api/v1/entities/{hedef}/ubo", headers=_auth(token))
    assert response.status_code == 201, response.text
    body = response.json()

    shares = {u["entity_id"]: u["effective_percent"] for u in body["ubos"]}
    assert shares == {ali: "42", ayse: "30"}  # 0,7·0,6 = %42
    # 0,7·0,4 = %28 döngüde kalır ve eşiği aşar: bulunanlar tam liste olmayabilir.
    assert body["status"] == "not_determinable"
    assert body["unattributed_percent"] == "28"
    assert body["cycles"]
    assert set(body["cycles"][0]) == {holding, capraz}
    assert eski not in {n["id"] for n in body["nodes"]}
    assert sorted(body["unscreened_ubo_ids"]) == sorted([ali, ayse])
    assert len(body["input_sha256"]) == 64

    again = api_client.get(f"/api/v1/entities/{hedef}/ubo", headers=_auth(token)).json()
    assert again["id"] == body["id"]

    # Aynı girdi → aynı özet; yeni hesap yeni satır (eski karar korunur).
    second = api_client.post(f"/api/v1/entities/{hedef}/ubo", headers=_auth(token)).json()
    assert second["id"] != body["id"]
    assert second["input_sha256"] == body["input_sha256"]
    history = api_client.get(f"/api/v1/entities/{hedef}/ubo/history", headers=_auth(token)).json()
    assert [h["id"] for h in history] == [second["id"], body["id"]]

    events = api_client.get(
        "/api/v1/audit/events", params={"action": "ubo.compute"}, headers=_auth(token)
    )
    assert events.status_code == 200, events.text
    assert events.json()["total"] == 2
    assert {e["object_id"] for e in events.json()["items"]} == {body["id"], second["id"]}


def test_inclusive_threshold_and_not_determinable(api_client: TestClient) -> None:
    _tenant, token = _register(api_client, "ubo2")
    hedef = _entity(api_client, token, "Sınır A.Ş.", "Company")
    yabanci = _entity(api_client, token, "Foreign Parent B.V.", "Company", country="NL")
    kisiler = [_entity(api_client, token, f"Ortak {i}", "Person") for i in range(3)]
    for kisi in kisiler:
        _owns(api_client, token, kisi, hedef, 25)
    _owns(api_client, token, yabanci, hedef, 25)

    strict = api_client.post(f"/api/v1/entities/{hedef}/ubo", headers=_auth(token)).json()
    assert strict["ubos"] == []
    # Kesin yorumda yabancı şirketin arkasındaki kişi en çok %25 tutabilir: eşiği aşamaz.
    assert strict["status"] == "none_found"
    assert strict["unresolved"][0]["entity_id"] == yabanci
    assert "yabancı" in strict["unresolved"][0]["reason"]

    inclusive = api_client.post(
        f"/api/v1/entities/{hedef}/ubo",
        json={"threshold_percent": 25, "inclusive": True},
        headers=_auth(token),
    ).json()
    assert len(inclusive["ubos"]) == 3
    # Yabancı ana şirketin %25'i eşiğe eşit: kapsayıcı yorumda tek başına UBO çıkarabilir.
    assert inclusive["status"] == "not_determinable"


def test_person_target_rejected_and_auditor_cannot_compute(api_client: TestClient) -> None:
    tenant, token = _register(api_client, "ubo3")
    kisi = _entity(api_client, token, "Tek Kişi", "Person")
    assert api_client.post(f"/api/v1/entities/{kisi}/ubo", headers=_auth(token)).status_code == 400

    sirket = _entity(api_client, token, "Denetim A.Ş.", "Company")
    auditor = create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant),
        role="auditor",
        secret=os.environ["AUTH_SECRET"],
        expires_in_minutes=60,
    )
    assert (
        api_client.post(f"/api/v1/entities/{sirket}/ubo", headers=_auth(auditor)).status_code == 403
    )
    assert (
        api_client.get(f"/api/v1/entities/{sirket}/ubo", headers=_auth(auditor)).status_code == 404
    )


def test_other_tenant_cannot_see_computation(api_client: TestClient) -> None:
    _a, token_a = _register(api_client, "uboa")
    _b, token_b = _register(api_client, "ubob")
    sirket = _entity(api_client, token_a, "Gizli A.Ş.", "Company")
    kisi = _entity(api_client, token_a, "Gizli Ortak", "Person")
    _owns(api_client, token_a, kisi, sirket, 100)
    assert (
        api_client.post(f"/api/v1/entities/{sirket}/ubo", headers=_auth(token_a)).status_code == 201
    )
    assert (
        api_client.get(f"/api/v1/entities/{sirket}/ubo", headers=_auth(token_b)).status_code == 404
    )
