"""Yazının commit'i yanıt istemciye gitmeden ÖNCE olur.

FastAPI'nin yield bağımlılıklarında varsayılan kapsam ("request") çıkış kodunu yanıt
gönderildikten sonra çalıştırır. Oturum bağımlılığı o kapsamda kalırsa istemci 201'i alır,
hemen ardından attığı istek yazıyı göremez (demo betiğinde ilişki ekleme 404) ve commit
düşerse istemci yine başarı görmüş olur. Bu test uygulamayı ASGI düzeyinde sürer ve yanıt
gövdesi gönderildiği anda ayrı bir bağlantıdan satırın görünür olduğunu doğrular.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration


def _register_and_login(client: TestClient) -> tuple[str, str]:
    kimlik = {"email": "commit@kapsam.com", "password": "sifre-12345"}
    r = client.post(
        "/api/v1/auth/register", json={"org_name": "kapsam", "org_slug": "kapsam", **kimlik}
    )
    assert r.status_code == 201, r.text
    login = client.post("/api/v1/auth/login", json=kimlik)
    assert login.status_code == 200, login.text
    return r.json()["tenant_id"], login.json()["access_token"]


def test_commit_yanit_gonderilmeden_once_olur(
    api_client: TestClient, app_database_url: str
) -> None:
    tenant, token = _register_and_login(api_client)
    govde = json.dumps({"name": "Kapsam Deneme A.Ş.", "schema_type": "Company"}).encode()
    gorunur: list[bool] = []
    engine = create_engine(app_database_url)

    def satir_gorunur_mu(entity_id: str) -> bool:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
            return (
                conn.execute(text("SELECT 1 FROM entity WHERE id = :i"), {"i": entity_id}).first()
                is not None
            )

    async def cagir() -> None:
        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/entities",
            "raw_path": b"/api/v1/entities",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"testserver"),
                (b"content-type", b"application/json"),
                (b"authorization", f"Bearer {token}".encode()),
                (b"content-length", str(len(govde)).encode()),
            ],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
            "state": {},
        }
        gonderildi = False

        async def receive() -> dict[str, Any]:
            nonlocal gonderildi
            if not gonderildi:
                gonderildi = True
                return {"type": "http.request", "body": govde, "more_body": False}
            return {"type": "http.disconnect"}

        parca = bytearray()

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.body":
                parca.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    entity_id = json.loads(bytes(parca))["entity"]["id"]
                    # İstemci yanıtı tam bu anda alır: yazı artık başka bağlantıdan görünmeli.
                    gorunur.append(satir_gorunur_mu(entity_id))

        await api_client.app(scope, receive, send)  # type: ignore[attr-defined]

    try:
        api_client.portal.call(cagir)  # type: ignore[attr-defined]
    finally:
        engine.dispose()
    assert gorunur == [True]
