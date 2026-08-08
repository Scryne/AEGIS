"""Tarama uçları — uçtan uca davranış (E1.3).

yente **taklit edilir** (``httpx.MockTransport``): bu testin konusu motorun skorlama
kalitesi değil, bizim akışımızdır — eşik bandı, HITL kararları, RBAC, denetim izi,
KVKK maskeleme ve motor hatasının nasıl raporlandığı. Motorun gerçek doğruluğu ayrı
bir kapıda ölçülür (``evals/test_screening_recall.py``, ``-m screening``).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from aegis_core.screening.yente import YenteClient
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
    return tenant_id, login.json()["access_token"]


def _role_token(tenant_id: str, role: str) -> str:
    return create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant_id),
        role=role,
        secret=os.environ["AUTH_SECRET"],
        expires_in_minutes=60,
    )


# ── yente taklidi ────────────────────────────────────────────────────────────

# Skorlar bilinçli olarak üç bandı da kapsar: 0.95 (otomatik işaretle),
# 0.72 (inceleme bandı), 0.55 (otomatik ele).
DEFAULT_RESULTS: list[dict[str, Any]] = [
    {
        "id": "NK-SANCTION",
        "caption": "Yildiz Insaat",
        "schema": "Company",
        "score": 0.95,
        "match": True,
        "datasets": ["default"],
        "features": {"name_literal_match": 1.0},
        "properties": {"topics": ["sanction"], "country": ["tr"]},
    },
    {
        "id": "NK-REVIEW",
        "caption": "Yildiz Insaat Ltd",
        "schema": "Company",
        "score": 0.72,
        "match": False,
        "datasets": ["default"],
        "properties": {"topics": ["role.pep"]},
    },
    {
        "id": "NK-LOW",
        "caption": "Yildirim Insaat",
        "schema": "Company",
        "score": 0.55,
        "match": False,
        "datasets": ["default"],
        "properties": {},
    },
]


def _install_fake_yente(
    client: TestClient,
    *,
    results: list[dict[str, Any]] | None = None,
    fail: bool = False,
    capture: dict[str, Any] | None = None,
) -> None:
    """Uygulamanın yente istemcisini taklit bir taşıma katmanıyla değiştirir."""

    def handler(request: httpx.Request) -> httpx.Response:
        if fail:
            raise httpx.ConnectError("motor kapalı")
        if capture is not None:
            capture["body"] = request.content.decode("utf-8")
            capture["url"] = str(request.url)
        payload = {
            key: {"status": 200, "results": results if results is not None else DEFAULT_RESULTS}
            for key in ["s0", "s1", "s2"]
        }
        return httpx.Response(200, json={"responses": payload})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://yente")
    client.app.state.yente_client = YenteClient("http://yente", client=http_client)


@pytest.fixture
def screening_client(api_client: TestClient) -> TestClient:
    """Taklit yente kurulmuş TestClient (yıkım gerekmez: istemci bellekte, soket yok)."""
    _install_fake_yente(api_client)
    return api_client


# ── Mutlu yol ────────────────────────────────────────────────────────────────


def test_tarama_calisir_ve_bantlar_uygulanir(screening_client: TestClient) -> None:
    _tenant, token = _register_and_login(screening_client, slug="tarama-ofis", email="t@tarama.com")
    response = screening_client.post(
        "/api/v1/screenings",
        json={"subject": {"name": "Yıldız İnşaat San. ve Tic. Ltd. Şti."}},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["status"] == "completed"
    assert body["subject_normalized"] == "yıldız inşaat"
    assert body["candidate_count"] == 3

    kararlar = {c["external_id"]: c for c in body["candidates"]}
    # Yüksek skor: bekliyor + işaretli (OTOMATİK ONAY YOK).
    assert kararlar["NK-SANCTION"]["decision"] == "pending"
    assert kararlar["NK-SANCTION"]["flagged"] is True
    assert kararlar["NK-SANCTION"]["band"] == "auto_flag"
    # Orta bant: insan incelemesi.
    assert kararlar["NK-REVIEW"]["decision"] == "pending"
    assert kararlar["NK-REVIEW"]["flagged"] is False
    # Düşük skor: otomatik elendi ama SİLİNMEDİ (rapor için gerekçesiyle durur).
    assert kararlar["NK-LOW"]["decision"] == "dismissed"
    assert kararlar["NK-LOW"]["decided_automatically"] is True
    assert kararlar["NK-LOW"]["review_note"]

    ozet = body["summary"]
    assert ozet["pending"] == 2
    assert ozet["dismissed"] == 1
    assert ozet["flagged"] == 1
    assert ozet["sanction_hits"] == 1
    assert ozet["pep_hits"] == 1


def test_normalize_edilmis_ve_ascii_varyantlar_motora_gider(api_client: TestClient) -> None:
    """Sorgu tarafı kanonik + ASCII + ham biçimlerin hepsini denemelidir."""
    capture: dict[str, Any] = {}
    _install_fake_yente(api_client, capture=capture)
    _tenant, token = _register_and_login(api_client, slug="varyant", email="v@varyant.com")
    api_client.post(
        "/api/v1/screenings",
        json={"subject": {"name": "Şişli Otomotiv Ltd. Şti."}},
        headers=_auth(token),
    )
    assert "şişli otomotiv" in capture["body"]
    assert "sisli otomotiv" in capture["body"]


def test_tarama_denetim_olayi_yazar_ve_zincir_dogrulanir(screening_client: TestClient) -> None:
    _tenant, token = _register_and_login(screening_client, slug="denetim", email="d@denetim.com")
    screening_client.post(
        "/api/v1/screenings", json={"subject": {"name": "ABC Yapı A.Ş."}}, headers=_auth(token)
    )
    verify = screening_client.get("/api/v1/audit/verify", headers=_auth(token))
    assert verify.status_code == 200
    assert verify.json()["ok"] is True
    assert verify.json()["events_checked"] >= 1


def test_liste_ve_detay(screening_client: TestClient) -> None:
    _tenant, token = _register_and_login(screening_client, slug="liste", email="l@liste.com")
    created = screening_client.post(
        "/api/v1/screenings", json={"subject": {"name": "Ege Gıda"}}, headers=_auth(token)
    ).json()

    listed = screening_client.get("/api/v1/screenings", headers=_auth(token))
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    detail = screening_client.get(f"/api/v1/screenings/{created['id']}", headers=_auth(token))
    assert detail.status_code == 200
    assert len(detail.json()["candidates"]) == 3


def test_bilinmeyen_tarama_404(screening_client: TestClient) -> None:
    _tenant, token = _register_and_login(screening_client, slug="yok", email="y@yok.com")
    response = screening_client.get(f"/api/v1/screenings/{uuid.uuid4()}", headers=_auth(token))
    assert response.status_code == 404


# ── HITL kararları ───────────────────────────────────────────────────────────


def test_eslesme_onaylanir_ve_denetlenir(screening_client: TestClient) -> None:
    _tenant, token = _register_and_login(screening_client, slug="karar", email="k@karar.com")
    created = screening_client.post(
        "/api/v1/screenings", json={"subject": {"name": "Yıldız İnşaat"}}, headers=_auth(token)
    ).json()
    candidate = next(c for c in created["candidates"] if c["external_id"] == "NK-SANCTION")

    response = screening_client.post(
        f"/api/v1/screenings/{created['id']}/candidates/{candidate['id']}/decision",
        json={"decision": "confirmed", "note": "Kimlik ve doğum tarihi tutuyor."},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "confirmed"
    assert response.json()["decided_automatically"] is False
    assert response.json()["reviewed_at"] is not None

    assert screening_client.get("/api/v1/audit/verify", headers=_auth(token)).json()["ok"] is True


def test_eleme_gerekcesiz_yapilamaz(screening_client: TestClient) -> None:
    """MASAK denetiminde "neden elendi" cevapsız kalamaz."""
    _tenant, token = _register_and_login(screening_client, slug="gerekce", email="g@gerekce.com")
    created = screening_client.post(
        "/api/v1/screenings", json={"subject": {"name": "Yıldız İnşaat"}}, headers=_auth(token)
    ).json()
    candidate = created["candidates"][0]

    response = screening_client.post(
        f"/api/v1/screenings/{created['id']}/candidates/{candidate['id']}/decision",
        json={"decision": "dismissed"},
        headers=_auth(token),
    )
    assert response.status_code == 400
    assert "gerekçe" in response.json()["error"]["message"].lower()


def test_karar_ozeti_gunceller(screening_client: TestClient) -> None:
    _tenant, token = _register_and_login(screening_client, slug="ozet", email="o@ozet.com")
    created = screening_client.post(
        "/api/v1/screenings", json={"subject": {"name": "Yıldız İnşaat"}}, headers=_auth(token)
    ).json()
    candidate = next(c for c in created["candidates"] if c["external_id"] == "NK-SANCTION")
    screening_client.post(
        f"/api/v1/screenings/{created['id']}/candidates/{candidate['id']}/decision",
        json={"decision": "confirmed", "note": "teyit"},
        headers=_auth(token),
    )
    detail = screening_client.get(
        f"/api/v1/screenings/{created['id']}", headers=_auth(token)
    ).json()
    assert detail["summary"]["confirmed"] == 1
    assert detail["summary"]["pending"] == 1


# ── RBAC ─────────────────────────────────────────────────────────────────────


def test_denetci_tarama_calistiramaz_ama_okuyabilir(screening_client: TestClient) -> None:
    tenant, _token = _register_and_login(screening_client, slug="rbac-a", email="a@rbac.com")
    auditor = _role_token(tenant, "auditor")

    forbidden = screening_client.post(
        "/api/v1/screenings", json={"subject": {"name": "ABC"}}, headers=_auth(auditor)
    )
    assert forbidden.status_code == 403
    assert screening_client.get("/api/v1/screenings", headers=_auth(auditor)).status_code == 200


def test_analist_tarar_ama_karar_veremez(screening_client: TestClient) -> None:
    """Analist dosyayı hazırlar; kararı uyumdan sorumlu rol verir."""
    tenant, owner_token = _register_and_login(screening_client, slug="rbac-b", email="b@rbac.com")
    analyst = _role_token(tenant, "analyst")

    created = screening_client.post(
        "/api/v1/screenings", json={"subject": {"name": "Yıldız İnşaat"}}, headers=_auth(analyst)
    )
    assert created.status_code == 201, created.text
    candidate = created.json()["candidates"][0]

    forbidden = screening_client.post(
        f"/api/v1/screenings/{created.json()['id']}/candidates/{candidate['id']}/decision",
        json={"decision": "confirmed"},
        headers=_auth(analyst),
    )
    assert forbidden.status_code == 403
    # Owner aynı kararı verebilir.
    allowed = screening_client.post(
        f"/api/v1/screenings/{created.json()['id']}/candidates/{candidate['id']}/decision",
        json={"decision": "confirmed"},
        headers=_auth(owner_token),
    )
    assert allowed.status_code == 200


# ── Motor hatası ─────────────────────────────────────────────────────────────


def test_motor_erisilemezse_502_ve_failed_kaydi(api_client: TestClient) -> None:
    """Başarısız tarama sessizce "temiz" görünmemeli; kayıt yine de kalmalı."""
    _install_fake_yente(api_client, fail=True)
    _tenant, token = _register_and_login(api_client, slug="motor", email="m@motor.com")

    response = api_client.post(
        "/api/v1/screenings", json={"subject": {"name": "ABC Yapı"}}, headers=_auth(token)
    )
    assert response.status_code == 502
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]
    assert body["candidate_count"] == 0

    # Kayıt ve denetim izi duruyor: "taramaya çalıştık ama yapamadık" bilgisi kaybolmaz.
    detail = api_client.get(f"/api/v1/screenings/{body['id']}", headers=_auth(token))
    assert detail.status_code == 200
    assert detail.json()["status"] == "failed"
    assert api_client.get("/api/v1/audit/verify", headers=_auth(token)).json()["ok"] is True


# ── KVKK: kimlik numarası maskeleme ──────────────────────────────────────────


def test_kimlik_numarasi_maskeli_saklanir(api_client: TestClient) -> None:
    """Numara motora gider ama veritabanına maskeli yazılır (alan şifreleme E1.4'te)."""
    capture: dict[str, Any] = {}
    _install_fake_yente(api_client, capture=capture)
    _tenant, token = _register_and_login(api_client, slug="kvkk", email="kvkk@kvkk.com")

    created = api_client.post(
        "/api/v1/screenings",
        json={"subject": {"name": "ABC Yapı", "identifiers": {"taxNumber": "1234567890"}}},
        headers=_auth(token),
    )
    assert created.status_code == 201
    # Motora tam numara gitti…
    assert "1234567890" in capture["body"]
    # …ama saklanan anlık görüntüde maskeli.
    stored = created.json()["subjects"][0]["identifiers"]["taxNumber"]
    assert stored == "******7890"

    detail = api_client.get(
        f"/api/v1/screenings/{created.json()['id']}", headers=_auth(token)
    ).json()
    assert detail["subjects"][0]["identifiers"]["taxNumber"] == "******7890"


def test_taninmayan_kimlik_alani_reddedilir(screening_client: TestClient) -> None:
    _tenant, token = _register_and_login(screening_client, slug="alan", email="al@alan.com")
    response = screening_client.post(
        "/api/v1/screenings",
        json={"subject": {"name": "ABC", "identifiers": {"gizliAlan": "x"}}},
        headers=_auth(token),
    )
    assert response.status_code == 400


# ── Eşik yapılandırması ──────────────────────────────────────────────────────


def test_kiraci_esikleri_uygulanir(screening_client: TestClient) -> None:
    """Eşik yükseltilince orta banttaki aday otomatik elenmeye düşer."""
    _tenant, token = _register_and_login(screening_client, slug="esik", email="e@esik.com")
    screening_client.put(
        "/api/v1/settings/screening.thresholds",
        json={"value": {"auto_dismiss_below": 0.8, "auto_flag_at": 0.9}},
        headers=_auth(token),
    )
    created = screening_client.post(
        "/api/v1/screenings", json={"subject": {"name": "Yıldız İnşaat"}}, headers=_auth(token)
    ).json()

    kararlar = {c["external_id"]: c["decision"] for c in created["candidates"]}
    assert kararlar["NK-REVIEW"] == "dismissed"  # 0.72 artık eşiğin altında
    assert kararlar["NK-SANCTION"] == "pending"  # 0.95 hâlâ işaretli
    # Koşu, o anki eşikleri kanıt olarak taşır.
    assert created["thresholds"]["auto_dismiss_below"] == 0.8


def test_bozuk_esik_ayari_taramayi_reddeder(screening_client: TestClient) -> None:
    """Sessizce varsayılana düşmek gerçek bir eşleşmeyi eleyebilirdi — fail-closed."""
    _tenant, token = _register_and_login(screening_client, slug="bozuk", email="b@bozuk.com")
    screening_client.put(
        "/api/v1/settings/screening.thresholds",
        json={"value": {"auto_dismis_below": 0.8}},
        headers=_auth(token),
    )
    response = screening_client.post(
        "/api/v1/screenings", json={"subject": {"name": "ABC"}}, headers=_auth(token)
    )
    assert response.status_code == 400
    assert "screening.thresholds" in response.json()["error"]["message"]


# ── Çok özneli koşu ──────────────────────────────────────────────────────────


def test_ilgili_kisiler_de_taranir(screening_client: TestClient) -> None:
    """Şirket + yöneticiler tek koşuda; her aday hangi özneden geldiğini taşır."""
    _tenant, token = _register_and_login(screening_client, slug="coklu", email="c@coklu.com")
    created = screening_client.post(
        "/api/v1/screenings",
        json={
            "subject": {"name": "Yıldız İnşaat A.Ş."},
            "related_subjects": [
                {"name": "Şahin Öztürk", "subject_type": "person", "role": "officer"},
                {"name": "Ayşe Yılmaz", "subject_type": "person", "role": "ubo"},
            ],
        },
        headers=_auth(token),
    ).json()

    assert len(created["subjects"]) == 3
    roller = {c["subject_key"]: c["subject_role"] for c in created["candidates"]}
    assert roller == {"s0": "self", "s1": "officer", "s2": "ubo"}
    assert created["candidate_count"] == 9


def test_senkron_yolda_ozne_siniri(screening_client: TestClient) -> None:
    _tenant, token = _register_and_login(screening_client, slug="sinir", email="s@sinir.com")
    response = screening_client.post(
        "/api/v1/screenings",
        json={
            "subject": {"name": "ABC"},
            "related_subjects": [{"name": f"Kişi {i}", "subject_type": "person"} for i in range(9)],
        },
        headers=_auth(token),
    )
    assert response.status_code == 400
    assert "derin" in response.json()["error"]["message"].lower()


def test_bos_ada_indirgenen_ozne_reddedilir(screening_client: TestClient) -> None:
    _tenant, token = _register_and_login(screening_client, slug="bosad", email="ba@bosad.com")
    response = screening_client.post(
        "/api/v1/screenings", json={"subject": {"name": "..."}}, headers=_auth(token)
    )
    assert response.status_code == 400


# ── Veri tazeliği ────────────────────────────────────────────────────────────


def test_veri_kumesi_kaydi_yokken_bayat_kabul_edilir(screening_client: TestClient) -> None:
    """Senkron job'ı hiç koşmadıysa "taze" denemez — bilmiyoruz ≠ taze."""
    _tenant, token = _register_and_login(screening_client, slug="tazelik", email="tz@tazelik.com")
    response = screening_client.get("/api/v1/screenings/datasets", headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["any_stale"] is True
    assert response.json()["staleness_threshold_hours"] == 24
