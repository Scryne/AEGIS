"""Varlık kütüğü uçları — provenans, tutarsızlık, çözümleme, birleştirme (E1.4).

Nesne deposu (MinIO) **taklit edilir**: bu testlerin konusu boto3'ün S3 ile konuşması
değil, bizim akışımızdır (yükleme → öneri → onay → kütük). Depo katmanının saf yardımcıları
ayrıca birim testlerdedir.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aegis_core.security.tokens import create_access_token

pytestmark = pytest.mark.integration

# Kontrol basamağı geçerli örnekler (bkz. packages/core/tests/test_identifiers.py).
GECERLI_VKN = "4840847211"
GECERLI_TCKN = "10000000146"
GECERLI_LEI = "529900T8BM49AURSDO55"


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


def _create_company(client: TestClient, token: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Yıldız İnşaat San. ve Tic. Ltd. Şti.",
        "schema_type": "Company",
        "tax_number": GECERLI_VKN,
        "address": "Cumhuriyet Mah. No:15 Şişli/İstanbul",
    }
    body.update(overrides)
    response = client.post("/api/v1/entities", json=body, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()


# ── Oluşturma ve provenans ───────────────────────────────────────────────────


def test_sirket_olusturulur_ve_normalize_edilir(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="kutuk", email="k@kutuk.com")
    created = _create_company(api_client, token)
    entity = created["entity"]
    assert entity["name_normalized"] == "yıldız inşaat"
    assert entity["tax_number"] == GECERLI_VKN
    assert created["identifier_warnings"] == []


def test_her_alan_provenans_satiri_uretir(api_client: TestClient) -> None:
    """ROADMAP E1.4: "provenance on every attribute (source + timestamp)"."""
    _tenant, token = _register_and_login(api_client, slug="prov", email="p@prov.com")
    entity = _create_company(api_client, token)["entity"]

    attributes = api_client.get(
        f"/api/v1/entities/{entity['id']}/attributes", headers=_auth(token)
    ).json()
    by_name = {item["name"]: item for item in attributes}
    assert by_name["name"]["source_type"] == "declared"
    assert by_name["taxNumber"]["value"] == GECERLI_VKN
    assert by_name["address"]["is_current"] is True
    assert all(item["observed_at"] for item in attributes)


def test_kontrol_basamagi_tutmayan_numara_kaydi_engellemez(api_client: TestClient) -> None:
    """Uyarı üretilir ama kayıt YAPILIR — belgedeki numara girilebilmelidir."""
    _tenant, token = _register_and_login(api_client, slug="uyari", email="u@uyari.com")
    created = _create_company(api_client, token, tax_number="1234567891")
    assert created["entity"]["tax_number"] == "1234567891"
    assert len(created["identifier_warnings"]) == 1
    assert created["identifier_warnings"][0]["field"] == "tax_number"


def test_tckn_sifreli_saklanir_ve_maskeli_doner(api_client: TestClient) -> None:
    """KVKK/ADR-0005: TCKN yanıtlarda düz metin GÖRÜNMEZ."""
    _tenant, token = _register_and_login(api_client, slug="tckn", email="t@tckn.com")
    created = api_client.post(
        "/api/v1/entities",
        json={"name": "Ahmet Yılmaz", "schema_type": "Person", "national_id": GECERLI_TCKN},
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text
    entity = created.json()["entity"]
    assert entity["national_id_masked"] == "*******0146"
    assert GECERLI_TCKN not in created.text

    # Öznitelik gözlemi de maskelidir (o tablo şifreli değil).
    attributes = api_client.get(
        f"/api/v1/entities/{entity['id']}/attributes", headers=_auth(token)
    ).json()
    national = next(item for item in attributes if item["name"] == "nationalId")
    assert national["value"] == "*******0146"


def test_tckn_veritabaninda_duz_metin_degildir(
    api_client: TestClient, app_database_url: str
) -> None:
    """Şifrelemenin gerçekten DB'ye yansıdığının kanıtı (ciphertext kontrolü)."""
    from sqlalchemy import create_engine, text

    tenant, token = _register_and_login(api_client, slug="sifre", email="s@sifre.com")
    api_client.post(
        "/api/v1/entities",
        json={"name": "Ayşe Demir", "schema_type": "Person", "national_id": GECERLI_TCKN},
        headers=_auth(token),
    )
    engine = create_engine(app_database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
            rows = conn.execute(text("SELECT national_id FROM entity")).fetchall()
    finally:
        engine.dispose()
    stored = [row[0] for row in rows if row[0]]
    assert stored, "Şifreli kolon boş kalmamalı"
    assert all(GECERLI_TCKN not in value for value in stored)


# ── Tutarsızlık ──────────────────────────────────────────────────────────────


def test_beyanla_celisen_gozlem_tutarsizlik_uretir(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="fark", email="f@fark.com")
    entity = _create_company(api_client, token)["entity"]

    updated = api_client.patch(
        f"/api/v1/entities/{entity['id']}",
        json={
            "changes": {"address": "Başka Mah. No:99 Kadıköy/İstanbul"},
            "source_type": "document",
            "source_ref": "faaliyet-belgesi.pdf",
            "promote_to_current": False,
        },
        headers=_auth(token),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["discrepancies_created"] == 1
    # Beyan üstüne YAZILMADI: müşterinin dediği ile belgenin gösterdiği ayrı durur.
    assert updated.json()["entity"]["address"] == "Cumhuriyet Mah. No:15 Şişli/İstanbul"

    discrepancies = api_client.get(
        f"/api/v1/entities/{entity['id']}/discrepancies", headers=_auth(token)
    ).json()
    assert len(discrepancies) == 1
    assert discrepancies[0]["attribute_name"] == "address"
    assert discrepancies[0]["severity"] == "warning"
    assert discrepancies[0]["status"] == "open"


def test_yazim_farki_tutarsizlik_sayilmaz(api_client: TestClient) -> None:
    """Büyük/küçük harf ve fazladan boşluk fark değildir (gürültü kontrolü)."""
    _tenant, token = _register_and_login(api_client, slug="yazim", email="y@yazim.com")
    entity = _create_company(api_client, token)["entity"]
    updated = api_client.patch(
        f"/api/v1/entities/{entity['id']}",
        json={
            "changes": {"address": "CUMHURİYET MAH.   NO:15  ŞİŞLİ/İSTANBUL"},
            "source_type": "document",
            "promote_to_current": False,
        },
        headers=_auth(token),
    )
    assert updated.json()["discrepancies_created"] == 0


def test_kimlik_numarasi_farki_kritik_sayilir(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="kritik", email="kr@kritik.com")
    entity = _create_company(api_client, token)["entity"]
    api_client.patch(
        f"/api/v1/entities/{entity['id']}",
        json={
            "changes": {"taxNumber": "1234567890"},
            "source_type": "registry",
            "promote_to_current": False,
        },
        headers=_auth(token),
    )
    discrepancies = api_client.get(
        f"/api/v1/entities/{entity['id']}/discrepancies", headers=_auth(token)
    ).json()
    assert discrepancies[0]["attribute_name"] == "taxNumber"
    assert discrepancies[0]["severity"] == "critical"


def test_tutarsizlik_gerekcesiz_karara_baglanamaz(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="ger", email="g@ger.com")
    entity = _create_company(api_client, token)["entity"]
    api_client.patch(
        f"/api/v1/entities/{entity['id']}",
        json={
            "changes": {"address": "Farklı Adres 123"},
            "source_type": "document",
            "promote_to_current": False,
        },
        headers=_auth(token),
    )
    discrepancy = api_client.get(
        f"/api/v1/entities/{entity['id']}/discrepancies", headers=_auth(token)
    ).json()[0]

    bos = api_client.post(
        f"/api/v1/entities/{entity['id']}/discrepancies/{discrepancy['id']}/decision",
        json={"status": "accepted", "note": ""},
        headers=_auth(token),
    )
    assert bos.status_code == 422  # şema düzeyinde min_length=1

    ok = api_client.post(
        f"/api/v1/entities/{entity['id']}/discrepancies/{discrepancy['id']}/decision",
        json={"status": "accepted", "note": "Şirket taşınmış, yeni adres teyit edildi."},
        headers=_auth(token),
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "accepted"
    assert ok.json()["resolution_note"]


# ── Varlık çözümleme (ER v1) ─────────────────────────────────────────────────


def test_ayni_vergi_numarasi_deterministik_eslesir(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="er1", email="e1@er.com")
    entity = _create_company(api_client, token)["entity"]

    result = api_client.post(
        "/api/v1/entities/resolve",
        json={"name": "Tamamen Başka Bir Ad", "tax_number": GECERLI_VKN},
        headers=_auth(token),
    ).json()
    assert result["outcome"] == "matched"
    assert result["matched_entity_id"] == entity["id"]
    assert "vergi numarası" in result["candidates"][0]["reason"]


def test_benzer_ad_ama_farkli_vergi_numarasi_eslesme_degildir(api_client: TestClient) -> None:
    """Bulanık eşleşmenin en tehlikeli hatası: iki farklı müşteriyi birleştirmek."""
    _tenant, token = _register_and_login(api_client, slug="er2", email="e2@er.com")
    _create_company(api_client, token)

    result = api_client.post(
        "/api/v1/entities/resolve",
        json={"name": "Yıldız İnşaat A.Ş.", "tax_number": "1234567890"},
        headers=_auth(token),
    ).json()
    assert result["outcome"] == "new"
    assert result["candidates"][0]["conflicting_identifier"] == "vergi numarası"


def test_ayni_ad_tanimlayicisiz_eslesir(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="er3", email="e3@er.com")
    entity = _create_company(api_client, token)["entity"]
    result = api_client.post(
        "/api/v1/entities/resolve",
        json={"name": "YILDIZ INSAAT LTD STI"},
        headers=_auth(token),
    ).json()
    assert result["outcome"] == "matched"
    assert result["matched_entity_id"] == entity["id"]


def test_alakasiz_ad_yeni_sayilir(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="er4", email="e4@er.com")
    _create_company(api_client, token)
    result = api_client.post(
        "/api/v1/entities/resolve",
        json={"name": "Kuantum Zebra Mühendislik A.Ş."},
        headers=_auth(token),
    ).json()
    assert result["outcome"] == "new"
    assert result["candidates"] == []


# ── İlişkiler ────────────────────────────────────────────────────────────────


def test_yonetici_iliskisi_kurulur(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="rel", email="r@rel.com")
    company = _create_company(api_client, token)["entity"]
    person = api_client.post(
        "/api/v1/entities",
        json={"name": "Ahmet Yılmaz", "schema_type": "Person"},
        headers=_auth(token),
    ).json()["entity"]

    created = api_client.post(
        f"/api/v1/entities/{company['id']}/relationships",
        json={
            "source_entity_id": person["id"],
            "rel_type": "officer",
            "role_title": "Yönetim Kurulu Başkanı",
        },
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text
    assert created.json()["source_entity_name"] == "Ahmet Yılmaz"

    listed = api_client.get(
        f"/api/v1/entities/{company['id']}/relationships", headers=_auth(token)
    ).json()
    assert len(listed) == 1
    assert listed[0]["rel_type"] == "officer"


def test_ortaklik_payi_dogrulanir(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="pay", email="pay@rel.com")
    company = _create_company(api_client, token)["entity"]
    person = api_client.post(
        "/api/v1/entities",
        json={"name": "Ayşe Kaya", "schema_type": "Person"},
        headers=_auth(token),
    ).json()["entity"]

    hatali = api_client.post(
        f"/api/v1/entities/{company['id']}/relationships",
        json={
            "source_entity_id": person["id"],
            "rel_type": "shareholder",
            "ownership_percent": 150,
        },
        headers=_auth(token),
    )
    assert hatali.status_code == 422


def test_varlik_kendisiyle_iliskilendirilemez(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="self", email="se@rel.com")
    company = _create_company(api_client, token)["entity"]
    response = api_client.post(
        f"/api/v1/entities/{company['id']}/relationships",
        json={"source_entity_id": company["id"], "rel_type": "control"},
        headers=_auth(token),
    )
    assert response.status_code == 400


# ── Birleştirme ──────────────────────────────────────────────────────────────


def test_birlestirme_kayitlari_tasir_ve_kaynagi_isaretler(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="merge", email="m@merge.com")
    hedef = _create_company(api_client, token)["entity"]
    kaynak = _create_company(
        api_client, token, name="Yildiz Insaat Limited", tax_number=None, address=None
    )["entity"]
    kisi = api_client.post(
        "/api/v1/entities", json={"name": "Ali Veli", "schema_type": "Person"}, headers=_auth(token)
    ).json()["entity"]
    api_client.post(
        f"/api/v1/entities/{kaynak['id']}/relationships",
        json={"source_entity_id": kisi["id"], "rel_type": "officer"},
        headers=_auth(token),
    )

    merged = api_client.post(
        f"/api/v1/entities/{hedef['id']}/merge",
        json={"source_entity_id": kaynak["id"], "note": "Aynı şirket, mükerrer kayıt."},
        headers=_auth(token),
    )
    assert merged.status_code == 200, merged.text

    # Kaynak kayıt SİLİNMEZ, işaretlenir.
    kaynak_sonra = api_client.get(f"/api/v1/entities/{kaynak['id']}", headers=_auth(token)).json()
    assert kaynak_sonra["status"] == "merged"
    assert kaynak_sonra["merged_into_id"] == hedef["id"]

    # İlişki hedefe taşındı.
    iliskiler = api_client.get(
        f"/api/v1/entities/{hedef['id']}/relationships", headers=_auth(token)
    ).json()
    assert len(iliskiler) == 1


def test_farkli_turler_birlestirilemez(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="merge2", email="m2@merge.com")
    company = _create_company(api_client, token)["entity"]
    person = api_client.post(
        "/api/v1/entities", json={"name": "Veli Ali", "schema_type": "Person"}, headers=_auth(token)
    ).json()["entity"]
    response = api_client.post(
        f"/api/v1/entities/{company['id']}/merge",
        json={"source_entity_id": person["id"]},
        headers=_auth(token),
    )
    assert response.status_code == 409


# ── RBAC ─────────────────────────────────────────────────────────────────────


def test_denetci_kutuge_yazamaz_ama_okur(api_client: TestClient) -> None:
    tenant, token = _register_and_login(api_client, slug="rbac-e", email="rb@ent.com")
    _create_company(api_client, token)
    auditor = _role_token(tenant, "auditor")

    forbidden = api_client.post("/api/v1/entities", json={"name": "X A.Ş."}, headers=_auth(auditor))
    assert forbidden.status_code == 403
    assert api_client.get("/api/v1/entities", headers=_auth(auditor)).status_code == 200


def test_analist_kutuge_yazar_ama_birlestiremez(api_client: TestClient) -> None:
    """Birleştirme geri alınması pahalı bir uyum kararıdır; analiste kapalıdır."""
    tenant, owner_token = _register_and_login(api_client, slug="rbac-a2", email="rb2@ent.com")
    analyst = _role_token(tenant, "analyst")

    created = api_client.post(
        "/api/v1/entities", json={"name": "Analist Yapı A.Ş."}, headers=_auth(analyst)
    )
    assert created.status_code == 201

    hedef = _create_company(api_client, owner_token)["entity"]
    forbidden = api_client.post(
        f"/api/v1/entities/{hedef['id']}/merge",
        json={"source_entity_id": created.json()["entity"]["id"]},
        headers=_auth(analyst),
    )
    assert forbidden.status_code == 403


def test_tutarsizlik_karari_analiste_kapali(api_client: TestClient) -> None:
    tenant, token = _register_and_login(api_client, slug="rbac-d", email="rb3@ent.com")
    entity = _create_company(api_client, token)["entity"]
    api_client.patch(
        f"/api/v1/entities/{entity['id']}",
        json={
            "changes": {"address": "Farklı Adres 456"},
            "source_type": "document",
            "promote_to_current": False,
        },
        headers=_auth(token),
    )
    discrepancy = api_client.get(
        f"/api/v1/entities/{entity['id']}/discrepancies", headers=_auth(token)
    ).json()[0]

    analyst = _role_token(tenant, "analyst")
    forbidden = api_client.post(
        f"/api/v1/entities/{entity['id']}/discrepancies/{discrepancy['id']}/decision",
        json={"status": "accepted", "note": "olur"},
        headers=_auth(analyst),
    )
    assert forbidden.status_code == 403


# ── Denetim izi ──────────────────────────────────────────────────────────────


def test_kutuk_islemleri_denetim_zincirini_bozmaz(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="izle", email="i@izle.com")
    company = _create_company(api_client, token)["entity"]
    person = api_client.post(
        "/api/v1/entities",
        json={"name": "Zeynep Ak", "schema_type": "Person"},
        headers=_auth(token),
    ).json()["entity"]
    api_client.post(
        f"/api/v1/entities/{company['id']}/relationships",
        json={"source_entity_id": person["id"], "rel_type": "ubo", "ownership_percent": 30},
        headers=_auth(token),
    )
    verify = api_client.get("/api/v1/audit/verify", headers=_auth(token))
    assert verify.status_code == 200
    assert verify.json()["ok"] is True
    # create ×2 + relationship ×1 → en az 3 olay
    assert verify.json()["events_checked"] >= 3


# ── Arama ────────────────────────────────────────────────────────────────────


def test_ada_gore_arama_turkce_normalizasyon_kullanir(api_client: TestClient) -> None:
    _tenant, token = _register_and_login(api_client, slug="ara", email="a@ara.com")
    _create_company(api_client, token)
    found = api_client.get("/api/v1/entities?q=yildiz insaat", headers=_auth(token)).json()
    assert found["total"] >= 1
    assert any("Yıldız" in item["name"] for item in found["items"])
