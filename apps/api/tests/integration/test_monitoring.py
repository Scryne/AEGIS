"""İzleme-lite (E2.4): taban koşusu, sentetik veri kümesi değişikliği → tam bir doğru alarm, onay.

ROADMAP E2.4 kabul ölçütü: *"Synthetic diff test (injected dataset change produces exactly one
correct alert)"*. yente ``httpx.MockTransport`` ile taklit edilir; iki koşu arasında taklidin
döndürdüğü liste değiştirilir.
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from aegis_core.config import get_settings
from aegis_core.db.tenant import set_tenant_context
from aegis_core.monitoring import notify as monitoring_notify
from aegis_core.monitoring import service as monitoring_service
from aegis_core.notifications.email import EmailSendError, OutgoingEmail
from aegis_core.screening.yente import YenteClient

pytestmark = pytest.mark.integration

BASE_RESULTS: list[dict[str, Any]] = [
    {
        "id": "NK-PEP",
        "caption": "Deniz Ticaret",
        "schema": "Company",
        "score": 0.72,
        "match": False,
        "datasets": ["default"],
        "properties": {"topics": ["role.pep"]},
    },
    {
        "id": "NK-LOW",
        "caption": "Denizli Ticaret",
        "schema": "Company",
        "score": 0.55,
        "match": False,
        "datasets": ["default"],
        "properties": {},
    },
]


def _install(client: TestClient, results: list[dict[str, Any]]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"responses": {f"s{i}": {"status": 200, "results": results} for i in range(4)}},
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://yente")
    client.app.state.yente_client = YenteClient("http://yente", client=http)


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


def test_injected_dataset_change_produces_exactly_one_alert(api_client: TestClient) -> None:
    token = _register(api_client, "izleme1")
    entity = api_client.post(
        "/api/v1/entities",
        json={"name": "Deniz Ticaret A.Ş.", "schema_type": "Company"},
        headers=_auth(token),
    ).json()["entity"]
    watched = api_client.put(
        f"/api/v1/entities/{entity['id']}/monitoring",
        json={"monitored": True},
        headers=_auth(token),
    )
    assert watched.json()["monitored"] is True
    assert api_client.get(f"/api/v1/entities/{entity['id']}", headers=_auth(token)).json()[
        "monitored"
    ]

    _install(api_client, BASE_RESULTS)
    first = api_client.post("/api/v1/monitoring/run", headers=_auth(token)).json()
    assert first == {"checked": 1, "alerts": 0, "failed": 0}  # taban koşusu

    again = api_client.post("/api/v1/monitoring/run", headers=_auth(token)).json()
    assert again["alerts"] == 0  # değişiklik yok → alarm yok

    changed = [
        *BASE_RESULTS,
        {
            "id": "NK-SANCTION-NEW",
            "caption": "Deniz Ticaret Ltd",
            "schema": "Company",
            "score": 0.93,
            "match": True,
            "datasets": ["default"],
            "properties": {"topics": ["sanction"]},
        },
    ]
    _install(api_client, changed)
    third = api_client.post("/api/v1/monitoring/run", headers=_auth(token)).json()
    assert third["alerts"] == 1

    listing = api_client.get("/api/v1/monitoring/alerts", headers=_auth(token)).json()
    assert listing["open_count"] == 1
    (alert,) = listing["items"]
    assert [(i["kind"], i["external_id"]) for i in alert["items"]] == [
        ("new_match", "NK-SANCTION-NEW")
    ]
    assert alert["entity_name"] == "Deniz Ticaret A.Ş."

    short = api_client.post(
        f"/api/v1/monitoring/alerts/{alert['id']}/acknowledge",
        json={"note": "x"},
        headers=_auth(token),
    )
    assert short.status_code in (400, 422)
    ack = api_client.post(
        f"/api/v1/monitoring/alerts/{alert['id']}/acknowledge",
        json={"note": "Eşleşme incelemeye alındı."},
        headers=_auth(token),
    ).json()
    assert ack["status"] == "acknowledged"
    assert (
        api_client.get("/api/v1/monitoring/alerts", headers=_auth(token)).json()["open_count"] == 0
    )

    fourth = api_client.post("/api/v1/monitoring/run", headers=_auth(token)).json()
    assert fourth["alerts"] == 0  # aynı yeni kayıt tekrar alarm üretmez

    events = api_client.get(
        "/api/v1/audit/events", params={"action": "monitoring.alert"}, headers=_auth(token)
    ).json()
    assert events["total"] == 1


def test_unwatched_entities_are_not_screened(api_client: TestClient) -> None:
    token = _register(api_client, "izleme2")
    api_client.post(
        "/api/v1/entities",
        json={"name": "İzlenmeyen A.Ş.", "schema_type": "Company"},
        headers=_auth(token),
    )
    _install(api_client, BASE_RESULTS)
    assert api_client.post("/api/v1/monitoring/run", headers=_auth(token)).json()["checked"] == 0


def test_taranamayan_varlik_kosu_kaydinda_gorunur(api_client: TestClient) -> None:
    """Motor düşünce sonuç "temiz" sayılmaz: koşu kaydı varlığı ve nedeni taşır."""
    token = _register(api_client, "izleme-hata")
    entity = api_client.post(
        "/api/v1/entities",
        json={"name": "Kapalı Motor A.Ş.", "schema_type": "Company"},
        headers=_auth(token),
    ).json()["entity"]
    api_client.put(
        f"/api/v1/entities/{entity['id']}/monitoring",
        json={"monitored": True},
        headers=_auth(token),
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "kapalı"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://yente")
    api_client.app.state.yente_client = YenteClient("http://yente", client=http)

    sonuc = api_client.post("/api/v1/monitoring/run", headers=_auth(token)).json()
    assert sonuc["failed"] == 1
    assert sonuc["alerts"] == 0

    kosu = api_client.get("/api/v1/monitoring/runs", headers=_auth(token)).json()["items"][0]
    assert kosu["failed"] == 1
    assert kosu["retried"] == 1  # bir kez yeniden denendi
    assert kosu["failures"][0]["entity_id"] == entity["id"]
    assert "sonuç yok" in kosu["failures"][0]["reason"]
    # Başarısız tarama kaydı kaybolmaz: "tarama yapılamadı" dosyada görünür.
    taramalar = api_client.get("/api/v1/screenings", headers=_auth(token)).json()["items"]
    assert len(taramalar) == 2
    assert {s["status"] for s in taramalar} == {"failed"}


def test_bildirim_tercihi_rol_kapili_ve_izde(api_client: TestClient) -> None:
    token = _register(api_client, "izleme-tercih")
    varsayilan = api_client.get("/api/v1/monitoring/notifications", headers=_auth(token)).json()
    assert varsayilan["critical"] == "immediate"
    assert varsayilan["info"] == "digest"
    assert varsayilan["email_configured"] is False

    yeni = {"critical": "immediate", "high": "digest", "info": "digest", "roles": ["owner"]}
    kayit = api_client.put("/api/v1/monitoring/notifications", json=yeni, headers=_auth(token))
    assert kayit.status_code == 200, kayit.text
    assert kayit.json()["high"] == "digest"
    assert (
        api_client.put(
            "/api/v1/monitoring/notifications",
            json={**yeni, "roles": []},
            headers=_auth(token),
        ).status_code
        == 422
    )
    olaylar = api_client.get(
        "/api/v1/audit/events", params={"action": "tenant_setting.update"}, headers=_auth(token)
    ).json()
    assert olaylar["total"] == 1


class _SahteGonderici:
    configured = True

    def __init__(self, hata: Exception | None = None) -> None:
        self.gidenler: list[OutgoingEmail] = []
        self.hata = hata

    async def send(self, message: OutgoingEmail) -> None:
        if self.hata is not None:
            raise self.hata
        self.gidenler.append(message)


def test_gece_kosusu_tekrar_taramaz_ve_bildirim_bir_kez_gider(
    api_client: TestClient, app_database_url: str
) -> None:
    """Gerçek veritabanında: görev yeniden teslimi, SMTP hatası ve "bildirildi" işareti."""
    token = _register(api_client, "izleme-gece")
    govde = token.split(".")[1]
    tenant = uuid.UUID(json.loads(base64.urlsafe_b64decode(govde + "==="))["tenant_id"])
    entity = api_client.post(
        "/api/v1/entities",
        json={"name": "Deniz Ticaret A.Ş.", "schema_type": "Company"},
        headers=_auth(token),
    ).json()["entity"]
    api_client.put(
        f"/api/v1/entities/{entity['id']}/monitoring",
        json={"monitored": True},
        headers=_auth(token),
    )
    _install(api_client, BASE_RESULTS)
    assert api_client.post("/api/v1/monitoring/run", headers=_auth(token)).json()["failed"] == 0
    yeni_aday = {
        "id": "NK-GECE",
        "caption": "Deniz Ticaret Ltd",
        "schema": "Company",
        "score": 0.93,
        "match": True,
        "datasets": ["default"],
        "properties": {"topics": ["sanction"]},
    }
    _install(api_client, [*BASE_RESULTS, yeni_aday])
    assert api_client.post("/api/v1/monitoring/run", headers=_auth(token)).json()["alerts"] == 1

    async def senaryo() -> dict[str, Any]:
        engine = create_async_engine(app_database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        settings = get_settings()
        try:
            client = api_client.app.state.yente_client
            async with factory() as session, session.begin():
                await set_tenant_context(session, tenant)
                # Elle koşu biraz önce tamamlandı: yeniden teslim edilen gece görevi atlamalı.
                gece = await monitoring_service.run_for_tenant(
                    session, client, tenant_id=tenant, settings=settings, trigger="nightly"
                )
            bozuk = _SahteGonderici(EmailSendError("kapalı"))
            async with factory() as session, session.begin():
                await set_tenant_context(session, tenant)
                dusen = await monitoring_notify.deliver(
                    session, tenant_id=tenant, settings=settings, sender=bozuk, mode="immediate"
                )
            saglam = _SahteGonderici()
            async with factory() as session, session.begin():
                await set_tenant_context(session, tenant)
                giden = await monitoring_notify.deliver(
                    session, tenant_id=tenant, settings=settings, sender=saglam, mode="immediate"
                )
            async with factory() as session, session.begin():
                await set_tenant_context(session, tenant)
                ikinci = await monitoring_notify.deliver(
                    session, tenant_id=tenant, settings=settings, sender=saglam, mode="digest"
                )
            return {
                "gece": gece,
                "dusen": dusen,
                "giden": giden,
                "ikinci": ikinci,
                "posta": saglam.gidenler,
            }
        finally:
            await engine.dispose()

    sonuc = asyncio.run(senaryo(), loop_factory=asyncio.SelectorEventLoop)
    assert sonuc["gece"]["skipped"] == 1
    assert sonuc["gece"]["checked"] == 0
    assert sonuc["dusen"]["status"] == "failed"  # SMTP düştü: bildirildi sayılmaz
    assert sonuc["giden"] == {"status": "sent", "alerts": 1}  # sonraki tur yeniden dener
    assert sonuc["ikinci"]["status"] == "nothing"  # ikinci kez gitmez
    posta = sonuc["posta"][0]
    assert posta.to == ("u@izleme-gece.com",)
    assert "Deniz Ticaret" not in posta.body  # kişisel/müşteri verisi yok
