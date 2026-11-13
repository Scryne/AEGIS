"""Ekip yönetimi (/members): davet, rol değişikliği, yetki, kiracı yalıtımı, denetim izi.

Doğrulanan garantiler:
- yalnız sahip davet eder / rol değiştirir (uyum uzmanı, analist, denetçi 403),
- davet edilen parolasız açılır; bağlantıyla parola belirleyip **davet edilen rolle** girer,
- SMTP yokken bağlantı yanıtta döner, varken e-postayla gider ve yanıtta dönmez,
- başka kiracının üyesi görünmez ve değiştirilemez (404), var olan adres davet edilemez (409),
- son sahip düşürülemez; rol değişikliği yenilenen jetonda geçerli olur,
- her davet ve rol değişikliği denetim izine düşer; olay yükünde e-posta yoktur.
"""

from __future__ import annotations

import os
import uuid
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from fastapi.testclient import TestClient

from aegis_core.notifications.email import OutgoingEmail
from aegis_core.security.tokens import create_access_token

pytestmark = pytest.mark.integration


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[OutgoingEmail] = []

    @property
    def configured(self) -> bool:
        return True

    async def send(self, message: OutgoingEmail) -> None:
        self.sent.append(message)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, slug: str, email: str) -> tuple[str, str, str]:
    reg = client.post(
        "/api/v1/auth/register",
        json={"org_name": slug, "org_slug": slug, "email": email, "password": "sifre-12345"},
    )
    assert reg.status_code == 201, reg.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "sifre-12345"})
    assert login.status_code == 200, login.text
    body = login.json()
    return reg.json()["tenant_id"], body["access_token"], body["refresh_token"]


def _token_from_link(link: str) -> str:
    return unquote(parse_qs(urlparse(link).query)["token"][0])


def _role_token(tenant_id: str, role: str) -> str:
    return create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant_id),
        role=role,
        secret=os.environ["AUTH_SECRET"],
        expires_in_minutes=60,
    )


def test_invite_set_password_login_and_role_change(api_client: TestClient) -> None:
    tenant, owner, _ = _register(api_client, "ekip-a", "sahip@ekip-a.example")

    davet = api_client.post(
        "/api/v1/members",
        json={"email": "analist@ekip-a.example", "full_name": "Ada Analist", "role": "analyst"},
        headers=_auth(owner),
    )
    assert davet.status_code == 201, davet.text
    body = davet.json()
    assert body["member"]["role"] == "analyst"
    assert body["member"]["pending"] is True
    # Test ortamında SMTP yok → bağlantı yanıtta, sahip kendisi iletir.
    assert (body["channel"], body["delivered"]) == ("manual", False)
    assert body["invite_link"].startswith("http")
    uid = body["member"]["user_id"]

    # Parola belirlenmeden giriş yok.
    erken = api_client.post(
        "/api/v1/auth/login", json={"email": "analist@ekip-a.example", "password": "x" * 10}
    )
    assert erken.status_code == 401

    onay = api_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": _token_from_link(body["invite_link"]), "new_password": "analist-parola-1"},
    )
    assert onay.status_code == 204, onay.text
    giris = api_client.post(
        "/api/v1/auth/login",
        json={"email": "analist@ekip-a.example", "password": "analist-parola-1"},
    )
    assert giris.status_code == 200, giris.text
    me = api_client.get("/api/v1/auth/me", headers=_auth(giris.json()["access_token"]))
    assert me.json()["role"] == "analyst"
    assert me.json()["tenant_id"] == tenant

    liste = api_client.get("/api/v1/members", headers=_auth(owner)).json()
    assert {(m["email"], m["role"], m["pending"]) for m in liste} == {
        ("sahip@ekip-a.example", "owner", False),
        ("analist@ekip-a.example", "analyst", False),
    }

    # Etkin hesabın daveti yeniden üretilemez (parola sıfırlamanın arka kapısı olurdu).
    tekrar = api_client.post(f"/api/v1/members/{uid}/invite", headers=_auth(owner))
    assert tekrar.status_code == 409

    # Rol değişikliği: yeni rol yenilenen jetonda geçerli.
    degis = api_client.patch(
        f"/api/v1/members/{uid}", json={"role": "compliance_officer"}, headers=_auth(owner)
    )
    assert degis.status_code == 200, degis.text
    assert degis.json()["role"] == "compliance_officer"
    yenile = api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": giris.json()["refresh_token"]}
    )
    assert yenile.status_code == 200, yenile.text
    me2 = api_client.get("/api/v1/auth/me", headers=_auth(yenile.json()["access_token"]))
    assert me2.json()["role"] == "compliance_officer"

    olaylar = api_client.get(
        "/api/v1/audit/events", params={"object_id": uid}, headers=_auth(owner)
    ).json()["items"]
    by_action = {e["action"]: e for e in olaylar}
    assert by_action["member.invite"]["payload"] == {
        "role": "analyst",
        "channel": "manual",
        "delivered": False,
        "valid_hours": 72,
    }
    assert by_action["member.role_change"]["payload"] == {
        "from": "analyst",
        "to": "compliance_officer",
    }
    for e in olaylar:
        assert "@" not in str(e["payload"])  # e-posta denetim yüküne girmez
    assert api_client.get("/api/v1/audit/verify", headers=_auth(owner)).json()["ok"] is True


def test_only_owner_manages_team(api_client: TestClient) -> None:
    tenant, owner, _ = _register(api_client, "ekip-yetki", "sahip@ekip-yetki.example")
    hedef = api_client.post(
        "/api/v1/members",
        json={"email": "denetci@ekip-yetki.example", "role": "auditor"},
        headers=_auth(owner),
    ).json()["member"]["user_id"]
    for role in ("compliance_officer", "analyst", "auditor"):
        token = _role_token(tenant, role)
        assert (
            api_client.post(
                "/api/v1/members",
                json={"email": f"{role}@ekip-yetki.example", "role": "owner"},
                headers=_auth(token),
            ).status_code
            == 403
        ), f"{role} davet edebildi"
        assert (
            api_client.patch(
                f"/api/v1/members/{hedef}", json={"role": "owner"}, headers=_auth(token)
            ).status_code
            == 403
        ), f"{role} rol değiştirebildi"
        assert (
            api_client.post(f"/api/v1/members/{hedef}/invite", headers=_auth(token)).status_code
            == 403
        )
        # Listeyi herkes okur (vaka atama vb. için).
        assert api_client.get("/api/v1/members", headers=_auth(token)).status_code == 200


def test_cross_tenant_isolation_and_conflicts(api_client: TestClient) -> None:
    _ta, owner_a, _ = _register(api_client, "ekip-x", "sahip@ekip-x.example")
    _tb, owner_b, _ = _register(api_client, "ekip-y", "sahip@ekip-y.example")
    b_uye = api_client.post(
        "/api/v1/members",
        json={"email": "uye@ekip-y.example", "role": "analyst"},
        headers=_auth(owner_b),
    ).json()["member"]["user_id"]

    # A, B'nin üyesini ne görür ne değiştirir ne de davetini yeniler.
    assert "uye@ekip-y.example" not in str(
        api_client.get("/api/v1/members", headers=_auth(owner_a)).json()
    )
    assert (
        api_client.patch(
            f"/api/v1/members/{b_uye}", json={"role": "owner"}, headers=_auth(owner_a)
        ).status_code
        == 404
    )
    assert (
        api_client.post(f"/api/v1/members/{b_uye}/invite", headers=_auth(owner_a)).status_code
        == 404
    )
    # B'deki üye hâlâ analist.
    b_liste = api_client.get("/api/v1/members", headers=_auth(owner_b)).json()
    assert {m["email"]: m["role"] for m in b_liste}["uye@ekip-y.example"] == "analyst"

    # Var olan adres (başka kurumda bile, büyük/küçük harf farkıyla) davet edilemez.
    for adres in ("uye@ekip-y.example", "UYE@ekip-y.example", "sahip@ekip-x.example"):
        r = api_client.post(
            "/api/v1/members", json={"email": adres, "role": "analyst"}, headers=_auth(owner_a)
        )
        assert r.status_code == 409, adres
    # Geçersiz rol reddedilir.
    assert (
        api_client.post(
            "/api/v1/members",
            json={"email": "yeni@ekip-x.example", "role": "superadmin"},
            headers=_auth(owner_a),
        ).status_code
        == 422
    )


def test_last_owner_cannot_be_demoted(api_client: TestClient) -> None:
    _t, owner, _ = _register(api_client, "ekip-sahip", "sahip@ekip-sahip.example")
    me = api_client.get("/api/v1/auth/me", headers=_auth(owner)).json()
    tek = api_client.patch(
        f"/api/v1/members/{me['id']}", json={"role": "analyst"}, headers=_auth(owner)
    )
    assert tek.status_code == 400  # ValidationFailedError (proje kuralı)
    # İkinci sahip eklenince ilki düşürülebilir.
    ikinci = api_client.post(
        "/api/v1/members",
        json={"email": "ikinci@ekip-sahip.example", "role": "owner"},
        headers=_auth(owner),
    )
    assert ikinci.status_code == 201
    ok = api_client.patch(
        f"/api/v1/members/{me['id']}", json={"role": "compliance_officer"}, headers=_auth(owner)
    )
    assert ok.status_code == 200, ok.text


def test_invite_by_email_hides_link_and_resend_works(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sender = FakeSender()
    monkeypatch.setattr("aegis_api.routers.v1.members.default_sender", lambda _s: sender)
    _t, owner, _ = _register(api_client, "ekip-posta", "sahip@ekip-posta.example")
    r = api_client.post(
        "/api/v1/members",
        json={"email": "uzman@ekip-posta.example", "role": "compliance_officer"},
        headers=_auth(owner),
    )
    assert r.status_code == 201, r.text
    assert (r.json()["channel"], r.json()["delivered"], r.json()["invite_link"]) == (
        "smtp",
        True,
        None,
    )
    assert len(sender.sent) == 1
    assert sender.sent[0].to == ("uzman@ekip-posta.example",)
    assert "sahip@ekip-posta.example" in sender.sent[0].body  # davet edeni bilir
    uid = r.json()["member"]["user_id"]
    yeniden = api_client.post(f"/api/v1/members/{uid}/invite", headers=_auth(owner))
    assert yeniden.status_code == 200, yeniden.text
    assert len(sender.sent) == 2
