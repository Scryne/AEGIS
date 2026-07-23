"""Append-only denetim izi + kiracı-başına hash zinciri kapısı (Invariant 2).

Doğrulanan garantiler:
- risk-etkileyen eylem (ayar güncelleme) tam bir denetim olayı yayar,
- hash zinciri kiracı başına sıralıdır ve ``verify_chain`` ile tutar,
- zincir kiracılar-arası izole edilir (RLS),
- tablo append-only'dir: app rolü UPDATE/DELETE yapamaz (izin) **ve** superuser dahil
  herkes için BEFORE trigger mutasyonu reddeder,
- trigger'ı devre dışı bırakabilen bir DBA'nın kurcalaması hash zinciriyle yakalanır,
- verifier RBAC ile korunur (analist erişemez; auditor salt-okunur erişir).
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from aegis_core.security.tokens import create_access_token

pytestmark = pytest.mark.integration

GENESIS_HASH = "0" * 64


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login(client: TestClient, *, slug: str, email: str) -> tuple[str, str]:
    register = client.post(
        "/api/v1/auth/register",
        json={"org_name": slug, "org_slug": slug, "email": email, "password": "sifre-12345"},
    )
    assert register.status_code == 201, register.text
    tenant_id: str = register.json()["tenant_id"]
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "sifre-12345"})
    assert login.status_code == 200, login.text
    return tenant_id, login.json()["access_token"]


def _put_setting(client: TestClient, token: str, key: str, value: dict[str, object]) -> None:
    resp = client.put(f"/api/v1/settings/{key}", json={"value": value}, headers=_auth(token))
    assert resp.status_code == 200, resp.text


def test_emission_chain_and_cross_tenant_isolation(
    api_client: TestClient, app_database_url: str
) -> None:
    tenant_a, token_a = _register_and_login(api_client, slug="audit-a", email="a@audit.com")
    _tenant_b, token_b = _register_and_login(api_client, slug="audit-b", email="b@audit.com")

    # A iki risk-etkileyen değişiklik yapar → iki olay; B bir tane.
    _put_setting(api_client, token_a, "risk-esigi", {"threshold": 0.85})
    _put_setting(api_client, token_a, "pep-esigi", {"threshold": 0.60})
    _put_setting(api_client, token_b, "risk-esigi", {"threshold": 0.50})

    # Verifier: her kiracının zinciri tutar ve yalnız kendi olaylarını sayar (izolasyon).
    ver_a = api_client.get("/api/v1/audit/verify", headers=_auth(token_a))
    assert ver_a.status_code == 200, ver_a.text
    assert ver_a.json() == {"ok": True, "events_checked": 2, "broken_seq": None, "reason": None}
    ver_b = api_client.get("/api/v1/audit/verify", headers=_auth(token_b))
    assert ver_b.json()["events_checked"] == 1

    # DB katmanı: app rolü altında A bağlamı yalnız A'nın zincirini görür; seq 1'den
    # başlar ve genesis'e bağlanır.
    engine = create_engine(app_database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_a})
            rows = conn.execute(
                text("SELECT seq, prev_hash, tenant_id FROM audit_event ORDER BY seq")
            ).fetchall()
        assert [r.seq for r in rows] == [1, 2]
        assert {str(r.tenant_id) for r in rows} == {tenant_a}
        assert rows[0].prev_hash == GENESIS_HASH
        assert rows[1].prev_hash != GENESIS_HASH  # ikinci halka birinciye zincirlenir

        # Append-only (izin katmanı): app rolü UPDATE/DELETE yapamaz.
        for statement in (
            "UPDATE audit_event SET action = 'kurcalama'",
            "DELETE FROM audit_event",
        ):
            with pytest.raises(DBAPIError), engine.begin() as conn:  # noqa: PT012
                conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_a}
                )
                conn.execute(text(statement))
    finally:
        engine.dispose()


def test_append_only_trigger_blocks_even_superuser(
    api_client: TestClient, admin_database_url: str
) -> None:
    _, token = _register_and_login(api_client, slug="audit-trig", email="t@audit.com")
    _put_setting(api_client, token, "risk-esigi", {"threshold": 0.85})

    # Superuser (aegis) izin engeline takılmaz ama BEFORE trigger mutasyonu reddeder.
    engine = create_engine(admin_database_url)
    try:
        for statement in (
            "UPDATE audit_event SET action = 'kurcalama'",
            "DELETE FROM audit_event",
        ):
            with pytest.raises(DBAPIError) as exc_info, engine.begin() as conn:
                conn.execute(text(statement))
            assert "append-only" in str(exc_info.value)
    finally:
        engine.dispose()


def test_hash_chain_detects_dba_tampering(api_client: TestClient, admin_database_url: str) -> None:
    tenant, token = _register_and_login(api_client, slug="audit-tamper", email="x@audit.com")
    _put_setting(api_client, token, "risk-esigi", {"threshold": 0.85})
    _put_setting(api_client, token, "pep-esigi", {"threshold": 0.60})
    assert api_client.get("/api/v1/audit/verify", headers=_auth(token)).json()["ok"] is True

    # Trigger'ı devre dışı bırakabilen bir DBA, geçmişi sessizce değiştirmeyi dener:
    # ilk olayın payload'ını değiştirir ama row_hash'i güncelleyemez (zinciri bilmiyor).
    disable_sql = "ALTER TABLE audit_event DISABLE TRIGGER audit_event_no_update_delete"
    enable_sql = "ALTER TABLE audit_event ENABLE TRIGGER audit_event_no_update_delete"
    engine = create_engine(admin_database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(disable_sql))
            conn.execute(
                text(
                    'UPDATE audit_event SET payload = \'{"value": {"threshold": 999}}\'::jsonb '
                    "WHERE tenant_id = :t AND seq = 1"
                ),
                {"t": tenant},
            )
            conn.execute(text(enable_sql))
    finally:
        engine.dispose()

    # Verifier kurcalamayı yakalar: ilk halka artık tutmuyor.
    ver = api_client.get("/api/v1/audit/verify", headers=_auth(token))
    assert ver.status_code == 200
    assert ver.json() == {
        "ok": False,
        "events_checked": 0,
        "broken_seq": 1,
        "reason": "row_hash_mismatch",
    }


def test_verify_endpoint_rbac(api_client: TestClient) -> None:
    tenant, _ = _register_and_login(api_client, slug="audit-rbac", email="r@audit.com")
    secret = os.environ["AUTH_SECRET"]

    # Analist zincir doğrulamasına erişemez (403).
    analyst = create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant),
        role="analyst",
        secret=secret,
        expires_in_minutes=60,
    )
    forbidden = api_client.get("/api/v1/audit/verify", headers=_auth(analyst))
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "forbidden"

    # Salt-okunur denetçi (auditor) erişebilir.
    auditor = create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant),
        role="auditor",
        secret=secret,
        expires_in_minutes=60,
    )
    allowed = api_client.get("/api/v1/audit/verify", headers=_auth(auditor))
    assert allowed.status_code == 200
    assert allowed.json()["ok"] is True
