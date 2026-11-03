"""Kiracı açma CLI'ı (E1.6, ``scripts/kiraci_ac.py``) — gerçek Postgres, uygulama rolü.

Doğrulananlar:
- kurum + parolasız sahip + üyelik + ``tenant.provision`` olayı tek seferde oluşur; davet
  ayrı ``tenant.invite`` olayıdır; olaylarda e-posta yoktur, zincir doğrulanır,
- sahip davet bağlantısıyla parola belirlemeden giriş yapamaz; belirledikten sonra
  **owner** olarak girer ve yalnız kendi kiracısını görür (RLS + uygulama katmanı),
- tekrar eden kısa ad / e-posta, geçersiz kısa ad ve SMTP'siz çağrı hiçbir satır bırakmaz,
- e-posta gitmezse hesap açık kalır, olay "teslim edilmedi" der, ``--yeniden-davet`` çalışır,
- uygulama rolü kiracı bağlamı olmadan yeni kiracının olaylarını göremez (fail-closed).
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from aegis_core.config import get_settings
from aegis_core.notifications.email import EmailSendError, OutgoingEmail

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[4]


def _load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("kiraci_ac", ROOT / "scripts" / "kiraci_ac.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kiraci_ac"] = module
    spec.loader.exec_module(module)
    return module


CLI = _load_cli()


class FakeSender:
    def __init__(self, *, configured: bool = True, fail: bool = False) -> None:
        self._configured = configured
        self.fail = fail
        self.sent: list[OutgoingEmail] = []

    @property
    def configured(self) -> bool:
        return self._configured

    async def send(self, message: OutgoingEmail) -> None:
        if self.fail:
            raise EmailSendError("SMTP gönderimi başarısız: ConnectionRefusedError")
        self.sent.append(message)


def _cli(argv: list[str], sender: FakeSender) -> int:
    code: int = asyncio.run(CLI.run(CLI.parse_args(argv), get_settings(), sender))
    return code


def _token_from(message: OutgoingEmail) -> str:
    match = re.search(r"/reset-password\?token=(\S+)", message.body)
    assert match, message.body
    return unquote(match.group(1))


def _count(url: str, sql: str, **params: object) -> int:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return int(conn.execute(text(sql), params).scalar_one())
    finally:
        engine.dispose()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_provision_invite_set_password_and_login(
    api_client: TestClient, app_database_url: str
) -> None:
    sender = FakeSender()
    code = _cli(
        [
            "--ad", "Örnek Mali Müşavirlik",
            "--slug", "prov-ornek",
            "--sahip-eposta", "sahip@prov-ornek.example",
            "--sahip-ad", "Kurgu Sahip",
            "--plan", "pilot",
        ],
        sender,
    )  # fmt: skip
    assert code == 0
    assert len(sender.sent) == 1
    assert sender.sent[0].to == ("sahip@prov-ornek.example",)

    # Parola belirlenmeden giriş yok.
    denied = api_client.post(
        "/api/v1/auth/login", json={"email": "sahip@prov-ornek.example", "password": "x" * 12}
    )
    assert denied.status_code == 401

    confirm = api_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": _token_from(sender.sent[0]), "new_password": "yeni-parola-1"},
    )
    assert confirm.status_code == 204, confirm.text
    login = api_client.post(
        "/api/v1/auth/login",
        json={"email": "sahip@prov-ornek.example", "password": "yeni-parola-1"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = api_client.get("/api/v1/auth/me", headers=_auth(token)).json()
    assert me["role"] == "owner"

    events = api_client.get("/api/v1/audit/events", headers=_auth(token)).json()["items"]
    actions = sorted((e["seq"], e["action"]) for e in events)
    assert actions == [(1, "tenant.provision"), (2, "tenant.invite")]
    provision = next(e for e in events if e["action"] == "tenant.provision")
    assert provision["actor_role"] == "operator"
    assert provision["payload"]["plan"] == "pilot"
    invite = next(e for e in events if e["action"] == "tenant.invite")
    assert invite["payload"]["channel"] == "smtp"
    assert invite["payload"]["delivered"] is True
    for event in events:
        assert "sahip@" not in str(event["payload"])

    verify = api_client.get("/api/v1/audit/verify", headers=_auth(token)).json()
    assert verify == {"ok": True, "events_checked": 2, "broken_seq": None, "reason": None}

    members = api_client.get("/api/v1/members", headers=_auth(token)).json()
    assert [m["email"] for m in members] == ["sahip@prov-ornek.example"]

    # Başka bir kiracı bu olayları ve üyeyi görmez.
    other = api_client.post(
        "/api/v1/auth/register",
        json={
            "org_name": "Diğer",
            "org_slug": "prov-diger",
            "email": "d@prov-diger.example",
            "password": "sifre-12345",
        },
    )
    assert other.status_code == 201
    other_token = api_client.post(
        "/api/v1/auth/login", json={"email": "d@prov-diger.example", "password": "sifre-12345"}
    ).json()["access_token"]
    other_events = api_client.get("/api/v1/audit/events", headers=_auth(other_token)).json()
    assert all(e["action"] != "tenant.provision" for e in other_events["items"])
    other_members = api_client.get("/api/v1/members", headers=_auth(other_token)).json()
    assert [m["email"] for m in other_members] == ["d@prov-diger.example"]

    # Uygulama rolü bağlamsız: sıfır satır (fail-closed).
    assert _count(app_database_url, "SELECT count(*) FROM audit_event") == 0


def test_rejections_leave_no_rows(api_client: TestClient, app_database_url: str) -> None:
    base = ["--ad", "Kurum", "--sahip-eposta", "ilk@prov-red.example"]
    assert _cli([*base, "--slug", "prov-red"], FakeSender()) == 0

    users_before = _count(app_database_url, "SELECT count(*) FROM user_account")
    orgs_before = _count(app_database_url, "SELECT count(*) FROM organization")

    # Aynı kısa ad, yeni e-posta → red; e-posta kullanılmamış kalır.
    sender = FakeSender()
    dup_slug = ["--ad", "K", "--slug", "prov-red", "--sahip-eposta", "yeni@prov-red.example"]
    assert _cli(dup_slug, sender) == 1
    # Aynı e-posta, yeni kısa ad → red; kurum açılmaz.
    assert _cli([*base, "--slug", "prov-red-2"], sender) == 1
    # Geçersiz kısa ad ve e-posta.
    assert _cli(["--ad", "K", "--slug", "Büyük Harf", "--sahip-eposta", "a@b.example"], sender) == 1
    assert _cli(["--ad", "K", "--slug", "prov-red-3", "--sahip-eposta", "gecersiz"], sender) == 1
    # SMTP yok, --baglantiyi-yazdir yok → hiçbir şey açılmaz.
    no_smtp = ["--ad", "K", "--slug", "prov-red-4", "--sahip-eposta", "s@prov-red.example"]
    assert _cli(no_smtp, FakeSender(configured=False)) == 2
    # Davet ömrü sınır dışı → açılmadan red.
    bad_hours = [*no_smtp, "--gecerlilik-saat", "1000"]
    assert _cli(bad_hours, FakeSender()) == 2

    assert sender.sent == []
    assert _count(app_database_url, "SELECT count(*) FROM user_account") == users_before
    assert _count(app_database_url, "SELECT count(*) FROM organization") == orgs_before


def test_failed_delivery_manual_link_and_reinvite(
    api_client: TestClient, app_database_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    failing = FakeSender(fail=True)
    argv = ["--ad", "Kurum", "--slug", "prov-hata", "--sahip-eposta", "s@prov-hata.example"]
    assert _cli(argv, failing) == 3  # hesap açık, davet gitmedi
    assert _count(app_database_url, "SELECT count(*) FROM organization WHERE slug='prov-hata'") == 1

    # Yeniden davet, bu kez SMTP'siz: bağlantı ekrana basılır (elle iletilir).
    capsys.readouterr()
    reinvite = ["--yeniden-davet", "--slug", "prov-hata", "--baglantiyi-yazdir"]
    assert _cli(reinvite, FakeSender(configured=False)) == 0
    printed = capsys.readouterr().out
    match = re.search(r"/reset-password\?token=(\S+)", printed)
    assert match
    confirm = api_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": unquote(match.group(1)), "new_password": "baska-parola-2"},
    )
    assert confirm.status_code == 204
    token = api_client.post(
        "/api/v1/auth/login",
        json={"email": "s@prov-hata.example", "password": "baska-parola-2"},
    ).json()["access_token"]
    items = api_client.get(
        "/api/v1/audit/events", params={"action": "tenant.invite"}, headers=_auth(token)
    ).json()["items"]
    payloads = sorted((e["seq"], e["payload"]["channel"], e["payload"]["delivered"]) for e in items)
    assert payloads == [(2, "smtp", False), (3, "manual", False)]
    assert api_client.get("/api/v1/audit/verify", headers=_auth(token)).json()["ok"] is True

    # Olmayan kurum için yeniden davet.
    assert _cli(["--yeniden-davet", "--slug", "prov-yok"], FakeSender()) == 1
