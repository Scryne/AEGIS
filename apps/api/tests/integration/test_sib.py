"""ŞİB taslağı (E2.2): ön doldurma, doğrulama kapısı, DOCX, gizlilik, denetim izi, saklama.

ROADMAP E2.2: *"template with prefill from dossier (identity, UBO findings, discrepancies,
screening hits)"*, *"export as editable document; status tracking + audit events"*, *"prominent
disclaimer"*. Rehber: MSK-RHB-ŞİB-018-1.0 (SMMM).
"""

from __future__ import annotations

import io
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from aegis_core.security.tokens import create_access_token

pytestmark = pytest.mark.integration

TCKN = "10000000146"
ACIKLAMA = (
    "Müşteri şirketin üçüncü çeyrek defterlerinde faaliyet konusuyla ilgisi bulunmayan, "
    "tamamı nakit tahsil edildiği beyan edilen danışmanlık gelirleri tespit edilmiştir. "
    "Gelirlerin karşı tarafı olarak gösterilen iki firmanın adresleri aynıdır. Fonların "
    "kaynağı sorulduğunda belge sunulamamış, gerçek faydalanıcı görüşmeye gelmemiştir."
)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, slug: str) -> tuple[str, str]:
    email = f"u@{slug}.com"
    r = client.post(
        "/api/v1/auth/register",
        json={
            "org_name": f"{slug} SMMM Bürosu",
            "org_slug": slug,
            "email": email,
            "password": "sifre-12345",
        },
    )
    assert r.status_code == 201, r.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "sifre-12345"})
    return r.json()["tenant_id"], login.json()["access_token"]


def _role_token(tenant_id: str, role: str) -> str:
    return create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant_id),
        role=role,
        secret=os.environ["AUTH_SECRET"],
        expires_in_minutes=60,
    )


def _entity(client: TestClient, token: str, **body: Any) -> str:
    r = client.post("/api/v1/entities", json=body, headers=_auth(token))
    assert r.status_code == 201, r.text
    return str(r.json()["entity"]["id"])


def _sirket_ve_ubo(client: TestClient, token: str) -> str:
    sirket = _entity(
        client,
        token,
        name="Deniz Ticaret A.Ş.",
        schema_type="Company",
        tax_number="1234567890",
        address="Liman Cad. No:3 Konak/İzmir",
    )
    kisi = _entity(client, token, name="Ayşe Nur Yılmaz", schema_type="Person", national_id=TCKN)
    r = client.post(
        f"/api/v1/entities/{sirket}/relationships",
        json={"source_entity_id": kisi, "rel_type": "shareholder", "ownership_percent": 80},
        headers=_auth(token),
    )
    assert r.status_code == 201, r.text
    assert client.post(f"/api/v1/entities/{sirket}/ubo", headers=_auth(token)).status_code == 201
    return sirket


def _duzelt(form: dict[str, Any]) -> dict[str, Any]:
    form["yukumlu"]["kimlik_no"] = "9876543210"
    form["bildirim"]["kategori"] = "aklama"
    form["sk_kodlari"] = ["SK-11", "SK-17"]
    form["aciklama"] = ACIKLAMA
    return form


def test_onden_doldurma_dogrulama_kapisi_ve_docx(api_client: TestClient) -> None:
    _tenant, token = _register(api_client, "sib1")
    sirket = _sirket_ve_ubo(api_client, token)

    r = api_client.post(f"/api/v1/entities/{sirket}/sib-drafts", headers=_auth(token))
    assert r.status_code == 201, r.text
    taslak = r.json()
    yil = datetime.now(UTC).year
    assert taslak["reference_no"] == f"SIB-{yil}-0001"
    form = taslak["form"]
    # Ön doldurma: kuruluş, şirket (D), gerçek faydalanıcı (C) kütükten.
    assert form["yukumlu"]["ad_unvan"] == "sib1 SMMM Bürosu"
    assert form["tuzel_kisiler"][0]["unvan"] == "Deniz Ticaret A.Ş."
    assert form["tuzel_kisiler"][0]["vkn"] == "1234567890"
    assert form["tuzel_kisiler"][0]["kurulus_nevi"] == "ticaret_sicili"
    ubo = form["gercek_kisiler"][0]
    assert (ubo["ad"], ubo["soyad"], ubo["baglanti"]) == (
        "Ayşe Nur",
        "Yılmaz",
        "gercek_faydalanici",
    )
    assert ubo["tckn"] == TCKN
    assert "%80" in ubo["ek_bilgi"]
    # Yargı gerektiren alanlar seçilmez; iskelet açıklama dışa aktarmayı kilitler.
    assert form["bildirim"]["kategori"] is None
    assert form["sk_kodlari"] == []
    hatali_alanlar = {h["alan"] for h in taslak["hatalar"]}
    assert {"bildirim.kategori", "sk_kodlari", "aciklama", "yukumlu.kimlik_no"} <= hatali_alanlar

    r = api_client.post(f"/api/v1/sib-drafts/{taslak['id']}/export", headers=_auth(token))
    assert r.status_code == 409
    assert {d["alan"] for d in r.json()["error"]["details"]} == hatali_alanlar

    r = api_client.put(
        f"/api/v1/sib-drafts/{taslak['id']}", json=_duzelt(form), headers=_auth(token)
    )
    assert r.status_code == 200, r.text
    assert r.json()["hatalar"] == []

    r = api_client.post(f"/api/v1/sib-drafts/{taslak['id']}/export", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert r.headers["cache-control"] == "no-store"
    belge = Document(io.BytesIO(r.content))
    metin = "\n".join(p.text for p in belge.paragraphs)
    tablolar = "\n".join(c.text for t in belge.tables for row in t.rows for c in row.cells)
    assert "TASLAKTIR" in metin
    assert "MSK-RHB-ŞİB-018-1.0" in metin
    assert "SK-11 Vergi kaçakçılığı ve vergi kaçırma" in metin
    assert ACIKLAMA in metin
    assert "Gerçek Faydalanıcı" in tablolar
    assert TCKN in tablolar
    assert "GİZLİDİR" in belge.sections[0].footer.paragraphs[0].text

    durum = api_client.get(f"/api/v1/sib-drafts/{taslak['id']}", headers=_auth(token)).json()
    assert (durum["status"], durum["export_count"]) == ("disa_aktarildi", 1)

    # Dışa aktarılmış taslak düzenlenince yeniden taslak olur (son belge artık güncel değil).
    form2 = durum["form"]
    form2["bildirim"]["aciliyet"] = "ivedi"
    r = api_client.put(f"/api/v1/sib-drafts/{taslak['id']}", json=form2, headers=_auth(token))
    assert r.json()["status"] == "taslak"

    # Referans numarası kiracı içinde sıralı.
    r2 = api_client.post(f"/api/v1/entities/{sirket}/sib-drafts", headers=_auth(token)).json()
    assert r2["reference_no"] == f"SIB-{yil}-0002"


def test_gizlilik_yalniz_sahip_ve_uyum_gorevlisi(api_client: TestClient) -> None:
    tenant, token = _register(api_client, "sib2")
    sirket = _entity(api_client, token, name="Kara Lojistik Ltd. Şti.", schema_type="Company")
    taslak = api_client.post(f"/api/v1/entities/{sirket}/sib-drafts", headers=_auth(token)).json()

    uyum = _role_token(tenant, "compliance_officer")
    assert api_client.get("/api/v1/sib-drafts", headers=_auth(uyum)).status_code == 200
    for rol in ("analyst", "auditor"):
        t = _role_token(tenant, rol)
        assert api_client.get("/api/v1/sib-drafts", headers=_auth(t)).status_code == 403
        assert (
            api_client.get(f"/api/v1/sib-drafts/{taslak['id']}", headers=_auth(t)).status_code
            == 403
        )
        assert (
            api_client.post(f"/api/v1/entities/{sirket}/sib-drafts", headers=_auth(t)).status_code
            == 403
        )

    # Başka kiracı taslağı göremez (RLS).
    _t2, diger = _register(api_client, "sib2b")
    assert (
        api_client.get(f"/api/v1/sib-drafts/{taslak['id']}", headers=_auth(diger)).status_code
        == 404
    )


def test_iptal_silmez_ve_kilitler(api_client: TestClient) -> None:
    _tenant, token = _register(api_client, "sib3")
    sirket = _entity(api_client, token, name="Mavi Gıda A.Ş.", schema_type="Company")
    taslak = api_client.post(f"/api/v1/entities/{sirket}/sib-drafts", headers=_auth(token)).json()
    kisa = api_client.post(
        f"/api/v1/sib-drafts/{taslak['id']}/cancel", json={"neden": "kısa"}, headers=_auth(token)
    )
    assert kisa.status_code == 422
    r = api_client.post(
        f"/api/v1/sib-drafts/{taslak['id']}/cancel",
        json={"neden": "Şüphe giderildi: belgeler sonradan sunuldu."},
        headers=_auth(token),
    )
    assert r.json()["status"] == "iptal"
    assert (
        api_client.put(
            f"/api/v1/sib-drafts/{taslak['id']}", json=taslak["form"], headers=_auth(token)
        ).status_code
        == 409
    )
    assert (
        api_client.post(
            f"/api/v1/sib-drafts/{taslak['id']}/export", headers=_auth(token)
        ).status_code
        == 409
    )
    liste = api_client.get(f"/api/v1/sib-drafts?entity_id={sirket}", headers=_auth(token)).json()
    assert [t["status"] for t in liste["items"]] == ["iptal"]


def test_denetim_izi_ve_sifreli_saklama(api_client: TestClient, app_database_url: str) -> None:
    tenant, token = _register(api_client, "sib4")
    sirket = _sirket_ve_ubo(api_client, token)
    taslak = api_client.post(f"/api/v1/entities/{sirket}/sib-drafts", headers=_auth(token)).json()
    api_client.put(
        f"/api/v1/sib-drafts/{taslak['id']}", json=_duzelt(taslak["form"]), headers=_auth(token)
    )
    api_client.post(f"/api/v1/sib-drafts/{taslak['id']}/export", headers=_auth(token))

    engine = create_engine(app_database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
            olaylar = conn.execute(
                text(
                    "SELECT action, payload::text FROM audit_event "
                    "WHERE object_type = 'sib_draft' ORDER BY seq"
                )
            ).fetchall()
            ham = conn.execute(
                text("SELECT form_encrypted, retention_until FROM sib_draft WHERE id = :i"),
                {"i": taslak["id"]},
            ).one()
    finally:
        engine.dispose()
    assert [o[0] for o in olaylar] == ["sib.create", "sib.update", "sib.export"]
    # Denetim izi bildirimin içeriğini taşımaz (kişisel veri + gizlilik).
    assert not any(TCKN in o[1] or "Yılmaz" in o[1] for o in olaylar)
    # Form diskte şifreli: TCKN, ad, açıklama düz metin olarak durmaz.
    assert TCKN not in ham.form_encrypted
    assert "Yılmaz" not in ham.form_encrypted
    assert "danışmanlık" not in ham.form_encrypted
    # ≥5 yıl saklama saati işliyor.
    assert (ham.retention_until - datetime.now(UTC)).days >= 365 * 5 - 2


def test_kod_listeleri(api_client: TestClient) -> None:
    _tenant, token = _register(api_client, "sib5")
    r = api_client.get("/api/v1/sib/kodlar", headers=_auth(token)).json()
    assert len(r["sk_kodlari"]) == 41
    assert r["kategori_zorunlu_sk"] == {"kis": ["SK-36"], "teror": ["SK-23", "SK-35"]}
    assert r["aciklama_en_az"] == 300
