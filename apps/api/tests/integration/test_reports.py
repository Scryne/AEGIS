"""Rapor akışı — risk özeti → dosya dışa aktarma → denetim izi (E1.5).

**Nesne deposu taklit edilir** (bellek içi sözlük), belge testindeki gerekçeyle: testin
konusu boto3'ün S3 ile konuşması değil, bizim akışımızdır. PDF/Word gerçekten üretilir.

Bu dosyadaki iddialar ürünün savunulabilirliğine dairdir:

- Rapor dışa aktarma **tam olarak bir** ``report.export`` olayı yazar ve olay dosyanın
  ``sha256``ını kaynak referansı olarak taşır (Invariant 2 + 4).
- Salt-okunur denetçi rapor **okur ama üretemez**; analist denetim izini göremez.
- Risk özeti taramasız varlıkta "Belirsiz"dir — asla "Standart" değil.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aegis_core.documents.storage import StoredObject, sha256_hex
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
    return tenant_id, login.json()["access_token"]


def _role_token(tenant_id: str, role: str) -> str:
    return create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant_id),
        role=role,
        secret=os.environ["AUTH_SECRET"],
        expires_in_minutes=60,
    )


@pytest.fixture
def fake_storage(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """Nesne deposunu bellek içi bir sözlükle değiştirir."""
    store: dict[str, bytes] = {}

    def _put(key: str, data: bytes, content_type: str, settings: Any = None) -> StoredObject:
        store[key] = data
        return StoredObject(key=key, size_bytes=len(data), sha256=sha256_hex(data))

    # Servis modülü depoyu doğrudan import ettiği için yamalar orada yapılır.
    monkeypatch.setattr("aegis_core.reports.service.put_object", _put)
    monkeypatch.setattr("aegis_core.reports.service.ensure_bucket", lambda settings=None: None)
    monkeypatch.setattr(
        "aegis_api.routers.v1.reports.presigned_url",
        lambda key, expires_in=300, settings=None: f"https://depo.test/{key}?imza=xyz",
    )
    return store


def _create_company(client: TestClient, token: str, *, name: str) -> str:
    response = client.post(
        "/api/v1/entities",
        json={"schema_type": "Company", "name": name, "country": "TR"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    # Yazma ucu kaydı ve uyarıları birlikte döndürür (EntityWriteResponse).
    entity_id: str = response.json()["entity"]["id"]
    return entity_id


def test_taramasiz_varligin_risk_ozeti_belirsizdir(api_client: TestClient) -> None:
    """ "Tarama yapılmadı" ile "tarama temiz çıktı" karıştırılmamalıdır."""
    _tenant, token = _register_and_login(api_client, slug="risk-a", email="a@risk.com")
    entity_id = _create_company(api_client, token, name="Özen Denetim A.Ş.")

    response = api_client.get(f"/api/v1/reports/risk/{entity_id}", headers=_auth(token))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["level"] == "unknown"
    assert payload["level_label"] == "Belirsiz"
    assert payload["complete"] is False
    assert any(item["code"] == "screening.missing" for item in payload["findings"])


def test_risk_ozeti_denetim_olayi_yazmaz(api_client: TestClient) -> None:
    """Okuma işlemi denetim izini gürültüyle doldurmamalıdır."""
    tenant, token = _register_and_login(api_client, slug="risk-b", email="b@risk.com")
    entity_id = _create_company(api_client, token, name="Yıldız İnşaat Ltd. Şti.")

    before = api_client.get("/api/v1/audit/events", headers=_auth(token)).json()["total"]
    api_client.get(f"/api/v1/reports/risk/{entity_id}", headers=_auth(token))
    after = api_client.get("/api/v1/audit/events", headers=_auth(token)).json()["total"]
    assert after == before, "risk özeti okuması denetim olayı yazdı"
    assert tenant


@pytest.mark.parametrize("report_format", ["pdf", "docx"])
def test_dosya_disa_aktarilir_saklanir_ve_denetlenir(
    api_client: TestClient, fake_storage: dict[str, bytes], report_format: str
) -> None:
    _tenant, token = _register_and_login(
        api_client, slug=f"rapor-{report_format}", email=f"{report_format}@rapor.com"
    )
    entity_id = _create_company(api_client, token, name="Özen Denetim A.Ş.")

    response = api_client.post(
        "/api/v1/reports/dossier",
        json={"entity_id": entity_id, "report_format": report_format},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["report_format"] == report_format
    assert report["risk_level"] == "unknown"
    assert report["size_bytes"] > 0
    # Saklama saati doğuştan işletilir (Invariant 4).
    assert report["retention_until"] is not None

    # Dosya gerçekten depoda ve kayıttaki özet onunla tutuyor (bütünlük kanıtı).
    assert len(fake_storage) == 1
    stored = next(iter(fake_storage.values()))
    assert sha256_hex(stored) == report["sha256"]
    magic = b"%PDF-" if report_format == "pdf" else b"PK"
    assert stored.startswith(magic)

    # Tam olarak BİR report.export olayı; kaynak referansı dosyanın özetidir.
    events = api_client.get(
        "/api/v1/audit/events?action=report.export", headers=_auth(token)
    ).json()
    assert events["total"] == 1
    event = events["items"][0]
    assert event["object_type"] == "report"
    assert event["object_id"] == report["id"]
    assert event["source_ref"] == f"sha256:{report['sha256']}"
    assert event["payload"]["risk_level"] == "unknown"

    # Zincir bütünlüğü rapor yazımından sonra da tutmalı.
    verify = api_client.get("/api/v1/audit/verify", headers=_auth(token)).json()
    assert verify["ok"] is True

    # İndirme kısa ömürlü imzalı URL döndürür (dosya API'den akıtılmaz).
    download = api_client.get(f"/api/v1/reports/{report['id']}/download", headers=_auth(token))
    assert download.status_code == 200
    assert download.json()["url"].startswith("https://depo.test/")
    assert download.json()["sha256"] == report["sha256"]

    listed = api_client.get(f"/api/v1/reports?entity_id={entity_id}", headers=_auth(token)).json()
    assert [item["id"] for item in listed] == [report["id"]]


def test_denetci_rapor_okur_ama_uretemez(
    api_client: TestClient, fake_storage: dict[str, bytes]
) -> None:
    tenant, token = _register_and_login(api_client, slug="rapor-rbac", email="rbac@rapor.com")
    entity_id = _create_company(api_client, token, name="Kaya Lojistik A.Ş.")
    api_client.post(
        "/api/v1/reports/dossier",
        json={"entity_id": entity_id, "report_format": "pdf"},
        headers=_auth(token),
    )

    auditor = _role_token(tenant, "auditor")
    forbidden = api_client.post(
        "/api/v1/reports/dossier",
        json={"entity_id": entity_id, "report_format": "pdf"},
        headers=_auth(auditor),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "forbidden"
    # Ama okuma serbest: denetçinin işi tam olarak budur.
    assert api_client.get("/api/v1/reports", headers=_auth(auditor)).status_code == 200
    assert (
        api_client.get(f"/api/v1/reports/risk/{entity_id}", headers=_auth(auditor)).status_code
        == 200
    )


def test_denetim_izi_analiste_kapali_denetciye_aciktir(api_client: TestClient) -> None:
    tenant, _token = _register_and_login(api_client, slug="iz-rbac", email="iz@rapor.com")

    analyst = _role_token(tenant, "analyst")
    assert api_client.get("/api/v1/audit/events", headers=_auth(analyst)).status_code == 403

    auditor = _role_token(tenant, "auditor")
    assert api_client.get("/api/v1/audit/events", headers=_auth(auditor)).status_code == 200


def test_denetim_izi_kim_ne_ne_zaman_neye_dayanarak_dondurur(api_client: TestClient) -> None:
    """Görüntüleyici, denetimde sorulan dört sorunun hepsini cevaplamalıdır."""
    _tenant, token = _register_and_login(api_client, slug="iz-icerik", email="ic@rapor.com")
    entity_id = _create_company(api_client, token, name="Deniz Tekstil A.Ş.")

    page = api_client.get("/api/v1/audit/events?object_type=entity", headers=_auth(token)).json()
    assert page["total"] >= 1
    event = page["items"][0]
    assert event["action"] == "entity.edit"
    assert event["object_id"] == entity_id
    assert event["actor_label"] == "ic@rapor.com"  # kim (kimlik düzleminden çözülür)
    assert event["actor_role"] == "owner"
    assert event["occurred_at"]  # ne zaman
    assert event["seq"] >= 1
    assert event["row_hash"]

    # Sayfalama ve süzgeç birlikte çalışır.
    filtered = api_client.get(
        "/api/v1/audit/events?action=report.export", headers=_auth(token)
    ).json()
    assert filtered["total"] == 0


def test_bulunmayan_varlik_icin_rapor_404(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="rapor-404", email="x@rapor.com")
    missing = uuid.uuid4()
    assert (
        api_client.post(
            "/api/v1/reports/dossier",
            json={"entity_id": str(missing), "report_format": "pdf"},
            headers=_auth(token),
        ).status_code
        == 404
    )
    assert (
        api_client.get(f"/api/v1/reports/risk/{missing}", headers=_auth(token)).status_code == 404
    )
