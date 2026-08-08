"""Kiracılar-arası izolasyon kapısı (Invariant 1).

İki kiracı tohumlanır ve SIFIR sızıntı iddia edilir — hem **her uç** üzerinden (API)
hem de **app rolü altında doğrudan SQL** ile. Bu test CI'da her push'ta koşar; kırmızıya
düşerse merge engellenir. Ayrıca RBAC (salt-okunur denetçi yazamaz) doğrulanır.
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
    token: str = login.json()["access_token"]
    return tenant_id, token


def test_cross_tenant_isolation_api_and_direct_sql(
    api_client: TestClient, app_database_url: str
) -> None:
    tenant_a, token_a = _register_and_login(api_client, slug="ofis-a", email="a@ofisa.com")
    tenant_b, token_b = _register_and_login(api_client, slug="ofis-b", email="b@ofisb.com")
    assert tenant_a != tenant_b

    # ── API katmanı: RLS'li veri ucu (/settings) ─────────────────────────────
    put_a = api_client.put(
        "/api/v1/settings/risk-esigi", json={"value": {"threshold": 0.85}}, headers=_auth(token_a)
    )
    assert put_a.status_code == 200, put_a.text
    put_b = api_client.put(
        "/api/v1/settings/risk-esigi", json={"value": {"threshold": 0.5}}, headers=_auth(token_b)
    )
    assert put_b.status_code == 200

    # A yalnızca kendi ayarını görür; B yalnızca kendini
    list_a = api_client.get("/api/v1/settings", headers=_auth(token_a))
    assert list_a.status_code == 200
    assert [(s["key"], s["value"]) for s in list_a.json()] == [("risk-esigi", {"threshold": 0.85})]
    list_b = api_client.get("/api/v1/settings", headers=_auth(token_b))
    assert [s["value"] for s in list_b.json()] == [{"threshold": 0.5}]

    # A, B'nin kaydını anahtarla dahi göremez (RLS → 404, sadece A'nın kiracısında arar)
    # (Aynı anahtar iki kiracıda da var; her biri yalnız kendininkini çözer.)
    get_a = api_client.get("/api/v1/settings/risk-esigi", headers=_auth(token_a))
    assert get_a.json()["value"] == {"threshold": 0.85}

    # ── API katmanı: kimlik/kontrol düzlemi ucu (/members) ───────────────────
    members_a = api_client.get("/api/v1/members", headers=_auth(token_a))
    assert members_a.status_code == 200
    assert [m["email"] for m in members_a.json()] == ["a@ofisa.com"]
    members_b = api_client.get("/api/v1/members", headers=_auth(token_b))
    assert [m["email"] for m in members_b.json()] == ["b@ofisb.com"]

    # ── RBAC: salt-okunur denetçi (auditor) yazamaz; analist de yazamaz ──────
    secret = os.environ["AUTH_SECRET"]
    for role in ("auditor", "analyst"):
        token = create_access_token(
            user_id=uuid.uuid4(),
            tenant_id=uuid.UUID(tenant_a),
            role=role,
            secret=secret,
            expires_in_minutes=60,
        )
        forbidden = api_client.put(
            "/api/v1/settings/x", json={"value": {"a": 1}}, headers=_auth(token)
        )
        assert forbidden.status_code == 403, f"{role} yazabildi!"
        assert forbidden.json()["error"]["code"] == "forbidden"
        # Ama okuma serbest (auditor salt-okunur, analist okur)
        assert api_client.get("/api/v1/settings", headers=_auth(token)).status_code == 200

    # ── DB katmanı: app rolü altında DOĞRUDAN SQL (RLS gerçekten zorluyor mu) ─
    # E1.3'te gelen tarama tabloları da aynı iddiaya tabidir: kiracıya-özel HER veri
    # tablosu bu listeye eklenir (CLAUDE.md: "tablo eklemek = tenant_id + RLS +
    # izolasyon iddiası, aynı değişiklikte").
    rls_tables = (
        "tenant_setting",
        "audit_event",
        # E1.3 tarama
        "screening",
        "match_candidate",
        # E1.4 varlık kütüğü
        "entity",
        "entity_attribute",
        "relationship",
        "document",
        "extraction_proposal",
        "discrepancy",
    )
    engine = create_engine(app_database_url)
    try:
        for table in rls_tables:
            # A bağlamı → yalnız A'nın satırları (ya da hiç)
            with engine.begin() as conn:
                conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_a}
                )
                rows = conn.execute(text(f"SELECT tenant_id FROM {table}")).fetchall()
            assert {str(r[0]) for r in rows} <= {tenant_a}, f"{table}: A'ya sızıntı"

            # B bağlamı → yalnız B'nin satırları
            with engine.begin() as conn:
                conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_b}
                )
                rows = conn.execute(text(f"SELECT tenant_id FROM {table}")).fetchall()
            assert {str(r[0]) for r in rows} <= {tenant_b}, f"{table}: B'ye sızıntı"

            # Bağlam YOK → fail-closed (sıfır satır)
            with engine.begin() as conn:
                rows = conn.execute(text(f"SELECT tenant_id FROM {table}")).fetchall()
            assert rows == [], f"{table}: bağlamsız okuma satır döndürdü"

        # tenant_setting'de her iki kiracının da satırı VAR; yukarıdaki alt-küme
        # iddiasının boş sonuçla trivially geçmediğini burada doğrularız.
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_a})
            rows = conn.execute(text("SELECT tenant_id FROM tenant_setting")).fetchall()
        assert {str(r[0]) for r in rows} == {tenant_a}

        # WITH CHECK: A bağlamında B'ye ait satır YAZILAMAZ (politika reddeder)
        with pytest.raises(DBAPIError), engine.begin() as conn:  # noqa: PT012
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_a})
            conn.execute(
                text(
                    "INSERT INTO tenant_setting (tenant_id, key, value) "
                    "VALUES (:t, 'sizinti', '{}'::jsonb)"
                ),
                {"t": tenant_b},
            )
    finally:
        engine.dispose()
