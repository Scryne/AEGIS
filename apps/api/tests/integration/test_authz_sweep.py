"""Yetki taraması (E3.7): uygulamadaki **her** /api/v1 ucu kimliksiz isteği reddeder.

Yeni bir uç eklenip kimlik bağımlılığı unutulursa bu test düşer; liste elle tutulmaz, router'dan
okunur. Kimliksiz olması bilinçli olan uçlar aşağıda gerekçesiyle sayılır. Ayrıca yalnız okuyan
denetçinin hiçbir yazma ucunda 2xx alamadığı denetlenir (gövde geçersiz olsa bile 2xx dönmemeli).
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from aegis_core.security.tokens import create_access_token

pytestmark = pytest.mark.integration

PUBLIC = {
    ("POST", "/api/v1/auth/register"),  # kayıt: kimlik henüz yok (oran sınırlı)
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),  # yenileme jetonuyla
    ("POST", "/api/v1/auth/password-reset/request"),
    ("POST", "/api/v1/auth/password-reset/confirm"),
    ("GET", "/api/v1/system/version"),  # sürüm bilgisi, kiracı verisi yok
}


def _routes(client: TestClient) -> list[tuple[str, str]]:
    """Uçlar OpenAPI şemasından okunur (bu FastAPI sürümünde ``app.routes`` dahil edilen
    router'ları sarmalı tutar; şema ise herkese açık sözleşmenin kendisidir)."""
    spec = client.app.openapi()  # type: ignore[attr-defined]
    out = []
    for path, item in spec["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            if method in item:
                out.append((method.upper(), path))
    return sorted(out)


def _concrete(path: str) -> str:
    out = []
    for part in path.split("/"):
        if part.startswith("{") and part.endswith("}"):
            out.append("ping" if part == "{key}" else str(uuid.uuid4()))
        else:
            out.append(part)
    return "/".join(out)


def test_every_endpoint_requires_auth(api_client: TestClient) -> None:
    routes = _routes(api_client)
    assert len(routes) > 80  # tarama gerçekten uygulamanın uçlarını görüyor
    leaks = []
    for method, path in routes:
        if (method, path) in PUBLIC:
            continue
        res = api_client.request(method, _concrete(path))
        if res.status_code != 401:
            leaks.append(f"{method} {path} → {res.status_code}")
    assert leaks == []


def test_auditor_cannot_write_anywhere(api_client: TestClient) -> None:
    reg = api_client.post(
        "/api/v1/auth/register",
        json={
            "org_name": "yetki",
            "org_slug": "yetki-tarama",
            "email": "u@yetki.com",
            "password": "sifre-12345",
        },
    )
    tenant = uuid.UUID(reg.json()["tenant_id"])
    auditor = create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=tenant,
        role="auditor",
        secret=os.environ["AUTH_SECRET"],
        expires_in_minutes=60,
    )
    headers = {"Authorization": f"Bearer {auditor}"}
    wrote = []
    writes = [r for r in _routes(api_client) if r[0] != "GET"]
    assert len(writes) > 50  # tarama gerçekten yazma uçlarını görüyor
    for method, path in _routes(api_client):
        if method == "GET" or (method, path) in PUBLIC or path.startswith("/api/v1/auth/"):
            continue
        res = api_client.request(method, _concrete(path), headers=headers, json={})
        if 200 <= res.status_code < 300:
            wrote.append(f"{method} {path} → {res.status_code}")
    assert wrote == []
