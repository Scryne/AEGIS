"""API anahtarı + webhook (E3.4) uçtan uca.

Faz 3 çıkış ölçütü 2: *"A customer integrates via API + webhooks using only public docs"*.
Bu test, belgelerdeki akışı izler: sahip anahtar açar → anahtarla tarama → ``screening.completed``
imzalı teslim → alıcı imzayı doğrular → ayrıntıyı API'den kimlikle çeker.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from aegis_core.config import get_settings
from aegis_core.screening.yente import YenteClient
from aegis_core.webhooks import signing

pytestmark = pytest.mark.integration


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


def _yente(client: TestClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        queries = json.loads(request.content)["queries"]
        return httpx.Response(
            200, json={"responses": {k: {"status": 200, "results": []} for k in queries}}
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://yente")
    client.app.state.yente_client = YenteClient("http://yente", client=http)  # type: ignore[attr-defined]


@pytest.fixture
def dev_webhooks() -> Any:
    """Testte webhook hedefi sahte bir yerel sunucudur: http + özel adres izni (geliştirme)."""
    s = get_settings()
    old = (s.webhook_allow_http, s.webhook_allow_private)
    s.webhook_allow_http, s.webhook_allow_private = True, True
    yield s
    s.webhook_allow_http, s.webhook_allow_private = old


def _deliver(handler: Any) -> dict[str, Any]:
    from aegis_worker.tasks.webhooks import _run

    async def go() -> dict[str, Any]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await _run(client=http)

    return asyncio.run(go())


def test_api_key_lifecycle_and_scope(api_client: TestClient) -> None:
    owner = _register(api_client, "entegre1")
    created = api_client.post(
        "/api/v1/api-keys", json={"name": "ERP", "role": "analyst"}, headers=_auth(owner)
    )
    assert created.status_code == 201, created.text
    full = created.json()["key"]
    listing = api_client.get("/api/v1/api-keys", headers=_auth(owner)).json()
    assert [k["prefix"] for k in listing] == [created.json()["prefix"]]
    assert "key" not in listing[0]  # tam anahtar bir daha gösterilmez

    key_headers = {"X-API-Key": full}
    assert api_client.get("/api/v1/entities", headers=key_headers).status_code == 200
    # Bearer biçimi de kabul edilir.
    assert api_client.get("/api/v1/entities", headers=_auth(full)).status_code == 200

    _yente(api_client)
    entity = api_client.post(
        "/api/v1/entities",
        json={"name": "Kuzey Enerji A.Ş.", "schema_type": "Company"},
        headers=key_headers,
    ).json()["entity"]
    run = api_client.post(f"/api/v1/screenings/from-entity/{entity['id']}", headers=key_headers)
    assert run.status_code == 201, run.text
    usage = api_client.get("/api/v1/billing/usage", headers=_auth(owner)).json()
    assert usage["used_queries"] == 1  # anahtarla yapılan tarama kotaya sayılır

    # Anahtar yönetim uçlarına giremez; denetçi anahtarı tarama yapamaz.
    assert api_client.get("/api/v1/api-keys", headers=key_headers).status_code == 403
    assert api_client.get("/api/v1/webhooks", headers=key_headers).status_code == 403
    auditor_key = api_client.post(
        "/api/v1/api-keys", json={"name": "Okur", "role": "auditor"}, headers=_auth(owner)
    ).json()["key"]
    denied = api_client.post(
        f"/api/v1/screenings/from-entity/{entity['id']}", headers={"X-API-Key": auditor_key}
    )
    assert denied.status_code == 403
    # Denetçi rollü anahtar bile entegrasyon ayarlarını okuyamaz (insan oturumu ister).
    assert api_client.get("/api/v1/api-keys", headers={"X-API-Key": auditor_key}).status_code == 403
    assert api_client.get("/api/v1/webhooks", headers={"X-API-Key": auditor_key}).status_code == 403
    owner_key = api_client.post(
        "/api/v1/api-keys", json={"name": "x", "role": "owner"}, headers=_auth(owner)
    )
    assert owner_key.status_code == 422

    # İptal → 401; uydurma anahtar → 401.
    revoked = api_client.delete(f"/api/v1/api-keys/{created.json()['id']}", headers=_auth(owner))
    assert revoked.json()["revoked_at"] is not None
    assert api_client.get("/api/v1/entities", headers=key_headers).status_code == 401
    fake = "aeg_" + "a" * 12 + "_" + "b" * 40
    assert api_client.get("/api/v1/entities", headers={"X-API-Key": fake}).status_code == 401

    # Başka kiracı anahtarları göremez ve iptal edemez.
    other = _register(api_client, "entegre1b")
    assert api_client.get("/api/v1/api-keys", headers=_auth(other)).json() == []
    stolen = api_client.delete(f"/api/v1/api-keys/{created.json()['id']}", headers=_auth(other))
    assert stolen.status_code == 404

    events = api_client.get(
        "/api/v1/audit/events", params={"object_type": "api_key"}, headers=_auth(owner)
    ).json()["items"]
    assert {e["action"] for e in events} == {"api_key.create", "api_key.revoke"}
    assert all(full not in json.dumps(e["payload"]) for e in events)


def test_api_key_rate_limit(api_client: TestClient) -> None:
    owner = _register(api_client, "entegre2")
    full = api_client.post(
        "/api/v1/api-keys", json={"name": "Sınır", "role": "auditor"}, headers=_auth(owner)
    ).json()["key"]
    s = get_settings()
    old = s.api_key_rate_limit_per_minute
    s.api_key_rate_limit_per_minute = 3
    try:
        codes = [
            api_client.get("/api/v1/entities", headers={"X-API-Key": full}).status_code
            for _ in range(5)
        ]
    finally:
        s.api_key_rate_limit_per_minute = old
    assert codes[:3] == [200, 200, 200]
    assert codes[3:] == [429, 429]


def test_webhook_signed_delivery_retry_and_isolation(
    api_client: TestClient, dev_webhooks: Any
) -> None:
    owner = _register(api_client, "entegre3")
    bad = api_client.post(
        "/api/v1/webhooks",
        json={"url": "https://x.test/h", "events": ["yok.boyle"]},
        headers=_auth(owner),
    )
    assert bad.status_code == 400
    hook = api_client.post(
        "/api/v1/webhooks",
        json={"url": "http://alici.test/aegis", "events": ["screening.completed", "case.updated"]},
        headers=_auth(owner),
    )
    assert hook.status_code == 201, hook.text
    secret = hook.json()["secret"]
    hook_id = hook.json()["id"]
    quiet = api_client.post(
        "/api/v1/webhooks",
        json={"url": "http://sessiz.test/h", "events": ["alert.raised"]},
        headers=_auth(owner),
    ).json()["id"]

    _yente(api_client)
    entity = api_client.post(
        "/api/v1/entities",
        json={"name": "Güney Madencilik A.Ş.", "schema_type": "Company"},
        headers=_auth(owner),
    ).json()["entity"]
    run = api_client.post(
        f"/api/v1/screenings/from-entity/{entity['id']}", headers=_auth(owner)
    ).json()

    received: list[httpx.Request] = []

    def ok(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(204)

    result = _deliver(ok)
    assert result["delivered"] == 1
    (req,) = received
    assert req.headers[signing.EVENT_HEADER] == "screening.completed"
    assert signing.verify(
        secret, req.content, req.headers[signing.SIGNATURE_HEADER], now=int(time.time())
    )
    body = json.loads(req.content)
    assert body["type"] == "screening.completed"
    assert body["data"]["screening_id"] == run["id"]
    assert "Güney" not in req.content.decode()  # yük kişisel/ticari ad taşımaz
    # Alıcı ayrıntıyı API'den kimlikle çeker.
    detail = api_client.get(
        f"/api/v1/screenings/{body['data']['screening_id']}", headers=_auth(owner)
    )
    assert detail.status_code == 200
    assert _deliver(ok)["attempted"] == 0  # teslim edilen yeniden gönderilmez
    # Abone olunmayan olay o uca hiç yazılmaz.
    assert api_client.get(f"/api/v1/webhooks/{quiet}/deliveries", headers=_auth(owner)).json() == []

    # Abone olunmayan olay kuyruğa girmez; abone olunan (vaka) girer. Alıcı 500 → yeniden deneme.
    api_client.post(
        "/api/v1/cases",
        json={"entity_id": entity["id"], "title": "Kontrol"},
        headers=_auth(owner),
    )

    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    failed = _deliver(down)
    assert failed == {"attempted": 1, "delivered": 0, "retrying": 1, "dead": 0}
    log = api_client.get(f"/api/v1/webhooks/{hook_id}/deliveries", headers=_auth(owner)).json()
    pending = next(d for d in log if d["event"] == "case.updated")
    assert pending["status"] == "pending"
    assert pending["attempts"] == 1
    assert pending["last_status_code"] == 500
    assert _deliver(ok)["attempted"] == 0  # 30 sn dolmadan yeniden denenmez

    redo = api_client.post(
        f"/api/v1/webhooks/deliveries/{pending['id']}/redeliver", headers=_auth(owner)
    )
    assert redo.json()["attempts"] == 0
    assert _deliver(ok)["delivered"] == 1

    # Test (ping), sır yenileme: eski sırla imza artık doğrulanmaz.
    api_client.post(f"/api/v1/webhooks/{hook_id}/test", headers=_auth(owner))
    new_secret = api_client.post(
        f"/api/v1/webhooks/{hook_id}/rotate-secret", headers=_auth(owner)
    ).json()["secret"]
    received.clear()
    _deliver(ok)
    ping = received[-1]
    assert ping.headers[signing.EVENT_HEADER] == "ping"
    now = int(time.time())
    assert signing.verify(new_secret, ping.content, ping.headers[signing.SIGNATURE_HEADER], now=now)
    assert not signing.verify(secret, ping.content, ping.headers[signing.SIGNATURE_HEADER], now=now)

    # Kapalı uç teslim almaz; başka kiracı bu ucu göremez.
    api_client.patch(f"/api/v1/webhooks/{hook_id}", json={"active": False}, headers=_auth(owner))
    other = _register(api_client, "entegre3b")
    assert (
        api_client.get(f"/api/v1/webhooks/{hook_id}/deliveries", headers=_auth(other)).status_code
        == 404
    )
    assert api_client.get("/api/v1/webhooks", headers=_auth(other)).json() == []


def test_webhook_refuses_private_targets_in_production_mode(api_client: TestClient) -> None:
    owner = _register(api_client, "entegre4")
    for url in ("http://alici.test/h", "https://127.0.0.1/h", "https://10.0.0.8/h"):
        res = api_client.post(
            "/api/v1/webhooks",
            json={"url": url, "events": ["alert.raised"]},
            headers=_auth(owner),
        )
        assert res.status_code == 400, url
