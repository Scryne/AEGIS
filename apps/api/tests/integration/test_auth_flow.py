"""Kimlik akışı: kayıt → giriş → me → refresh → parola sıfırlama (API üzerinden)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_login_me_refresh(api_client: TestClient) -> None:
    register = api_client.post(
        "/api/v1/auth/register",
        json={
            "org_name": "Deneme Ofisi",
            "org_slug": "deneme-ofisi",
            "email": "owner@deneme.com",
            "password": "cok-gizli-123",
            "full_name": "Scryne",
        },
    )
    assert register.status_code == 201, register.text
    assert register.json()["role"] == "owner"

    # Aynı slug/e-posta ikinci kez → 409
    dup = api_client.post(
        "/api/v1/auth/register",
        json={
            "org_name": "Deneme Ofisi",
            "org_slug": "deneme-ofisi",
            "email": "baska@deneme.com",
            "password": "cok-gizli-123",
        },
    )
    assert dup.status_code == 409

    login = api_client.post(
        "/api/v1/auth/login", json={"email": "owner@deneme.com", "password": "cok-gizli-123"}
    )
    assert login.status_code == 200, login.text
    tokens = login.json()
    access, refresh = tokens["access_token"], tokens["refresh_token"]

    me = api_client.get("/api/v1/auth/me", headers=_auth(access))
    assert me.status_code == 200
    assert me.json()["email"] == "owner@deneme.com"
    assert me.json()["role"] == "owner"

    # Yanlış parola → 401
    bad = api_client.post(
        "/api/v1/auth/login", json={"email": "owner@deneme.com", "password": "yanlis"}
    )
    assert bad.status_code == 401

    # Refresh token yeni erişim token'ı verir; refresh token erişim yerine kullanılamaz
    refreshed = api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert refreshed.status_code == 200, refreshed.text
    new_access = refreshed.json()["access_token"]
    assert api_client.get("/api/v1/auth/me", headers=_auth(new_access)).status_code == 200
    # refresh token'ı access olarak kullanmak reddedilir (tür doğrulaması)
    assert api_client.get("/api/v1/auth/me", headers=_auth(refresh)).status_code == 401


def test_password_reset_flow(api_client: TestClient) -> None:
    api_client.post(
        "/api/v1/auth/register",
        json={
            "org_name": "Sifirlama",
            "org_slug": "sifirlama",
            "email": "reset@deneme.com",
            "password": "eski-parola-1",
        },
    )
    # development ortamında token yanıtta gelir (e-posta teslimi E1.6'da bağlanır)
    req = api_client.post("/api/v1/auth/password-reset/request", json={"email": "reset@deneme.com"})
    assert req.status_code == 202, req.text
    token = req.json()["reset_token"]
    assert token is not None

    confirm = api_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "yeni-parola-9"},
    )
    assert confirm.status_code == 204

    # Eski parola artık geçmez, yeni parola geçer
    assert (
        api_client.post(
            "/api/v1/auth/login", json={"email": "reset@deneme.com", "password": "eski-parola-1"}
        ).status_code
        == 401
    )
    assert (
        api_client.post(
            "/api/v1/auth/login", json={"email": "reset@deneme.com", "password": "yeni-parola-9"}
        ).status_code
        == 200
    )

    # Bilinmeyen e-posta da 202 döner ama token üretmez (numaralandırmayı önler)
    unknown = api_client.post(
        "/api/v1/auth/password-reset/request", json={"email": "yok@deneme.com"}
    )
    assert unknown.status_code == 202
    assert unknown.json()["reset_token"] is None
