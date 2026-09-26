"""Belge akışı — yükleme → çıkarım → öneri → onay → kütük (E1.4, R2).

**Nesne deposu taklit edilir** (bellek içi sözlük): testin konusu boto3'ün S3 ile
konuşması değil, bizim akışımızdır. Depo modülünün saf yardımcıları birim testlerdedir.

**Çıkarım gerçekten koşar.** Belgeler ``text/plain`` yüklenir; bu yolda Docling
gerekmez (bkz. ``docling_adapter``), böylece desen çıkarımı → öneri → onay zinciri
uçtan uca, gerçek worker koroutini üzerinden sınanır.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aegis_core.documents.storage import StoredObject
from aegis_core.security.tokens import create_access_token

pytestmark = pytest.mark.integration

GECERLI_VKN = "4840847211"
GECERLI_TCKN = "10000000146"

IMZA_SIRKULERI_METNI = f"""İMZA SİRKÜLERİ

YILDIZ İNŞAAT SANAYİ VE TİCARET LİMİTED ŞİRKETİ
Vergi Kimlik No : {GECERLI_VKN}

AHMET YILMAZ - T.C. Kimlik No: {GECERLI_TCKN}
Şirketi münferiden temsil ve ilzama yetkilidir.
"""


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
        from aegis_core.documents.storage import sha256_hex

        return StoredObject(key=key, size_bytes=len(data), sha256=sha256_hex(data))

    def _get(key: str, settings: Any = None) -> bytes:
        return store[key]

    monkeypatch.setattr("aegis_api.routers.v1.documents.put_object", _put)
    monkeypatch.setattr("aegis_api.routers.v1.documents.ensure_bucket", lambda settings=None: None)
    monkeypatch.setattr(
        "aegis_api.routers.v1.documents.presigned_url",
        lambda key, expires_in=300, settings=None: f"https://depo.test/{key}?imza=xyz",
    )
    # Kuyruğa gerçek mesaj bırakılmaz; çıkarım testte elle tetiklenir.
    monkeypatch.setattr("aegis_api.routers.v1.documents.dispatch", lambda *a, **k: "task-id")
    monkeypatch.setattr("aegis_worker.tasks.documents.get_object", _get)
    return store


def _run_extraction(tenant_id: str, document_id: str) -> dict[str, Any]:
    """Worker çıkarım koroutinini testte doğrudan koşturur (Celery olmadan)."""
    from aegis_worker.tasks.documents import _extract_document

    return asyncio.run(
        _extract_document(tenant_id=uuid.UUID(tenant_id), document_id=uuid.UUID(document_id))
    )


def _upload(
    client: TestClient,
    token: str,
    *,
    entity_id: str | None = None,
    doc_type: str = "imza_sirkuleri",
    content: str = IMZA_SIRKULERI_METNI,
    filename: str = "imza-sirkuleri.txt",
    extra: dict[str, str] | None = None,
) -> dict[str, Any]:
    data = {"doc_type": doc_type}
    if entity_id:
        data["entity_id"] = entity_id
    if extra:
        data.update(extra)
    response = client.post(
        "/api/v1/documents",
        files={"file": (filename, content.encode("utf-8"), "text/plain")},
        data=data,
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_company(client: TestClient, token: str) -> dict[str, Any]:
    response = client.post(
        "/api/v1/entities",
        json={"name": "Yıldız İnşaat San. ve Tic. Ltd. Şti.", "tax_number": GECERLI_VKN},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["entity"]


# ── Yükleme ──────────────────────────────────────────────────────────────────


def test_belge_yuklenir_ve_cikarim_bekler(
    api_client: TestClient, fake_storage: dict[str, bytes]
) -> None:
    tenant, token = _register_and_login(api_client, slug="blg", email="b@blg.com")
    entity = _create_company(api_client, token)
    document = _upload(api_client, token, entity_id=entity["id"])

    assert document["extraction_status"] == "pending"
    assert document["sha256"]
    # Kiracı kimliği nesne anahtarının önekindedir (bkz. storage modül başlığı).
    assert any(key.startswith(tenant) for key in fake_storage)


def test_desteklenmeyen_tur_reddedilir(
    api_client: TestClient, fake_storage: dict[str, bytes]
) -> None:
    _tenant, token = _register_and_login(api_client, slug="tur", email="t@tur.com")
    response = api_client.post(
        "/api/v1/documents",
        files={"file": ("zararli.exe", b"MZ...", "application/x-msdownload")},
        data={"doc_type": "other"},
        headers=_auth(token),
    )
    assert response.status_code == 400
    assert "Desteklenmeyen" in response.json()["error"]["message"]


def test_bos_dosya_reddedilir(api_client: TestClient, fake_storage: dict[str, bytes]) -> None:
    _tenant, token = _register_and_login(api_client, slug="bos", email="bo@bos.com")
    response = api_client.post(
        "/api/v1/documents",
        files={"file": ("bos.txt", b"", "text/plain")},
        data={"doc_type": "other"},
        headers=_auth(token),
    )
    assert response.status_code == 400


def test_other_turu_cikarim_denemez(api_client: TestClient, fake_storage: dict[str, bytes]) -> None:
    _tenant, token = _register_and_login(api_client, slug="oth", email="o@oth.com")
    document = _upload(api_client, token, doc_type="other", filename="fis.txt", content="fiş")
    assert document["extraction_status"] == "skipped"


def test_gazete_kaynak_referansi_saklanir(
    api_client: TestClient, fake_storage: dict[str, bytes]
) -> None:
    """R1: otomatik gazete sorgusu YOK; kullanıcı sayı/tarih verir, kanıt olarak durur."""
    _tenant, token = _register_and_login(api_client, slug="gzt", email="g@gzt.com")
    document = _upload(
        api_client,
        token,
        doc_type="ticaret_sicil_gazetesi",
        filename="gazete.txt",
        content="Tescil ilanı",
        extra={
            "gazette_issue_number": "11234",
            "gazette_issue_date": "2024-05-20",
            "gazette_url": "https://www.ticaretsicil.gov.tr/ilan/11234",
        },
    )
    assert document["source_ref"] is not None
    assert "11234" in document["source_ref"]
    assert "2024-05-20" in document["source_ref"]


def test_indirme_baglantisi_kisa_omurludur(
    api_client: TestClient, fake_storage: dict[str, bytes]
) -> None:
    _tenant, token = _register_and_login(api_client, slug="ind", email="i@ind.com")
    document = _upload(api_client, token)
    response = api_client.get(f"/api/v1/documents/{document['id']}/download", headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["expires_in_seconds"] == 300
    assert response.json()["url"].startswith("https://depo.test/")


# ── Çıkarım → öneri ──────────────────────────────────────────────────────────


def test_cikarim_oneri_uretir_ama_kutuge_yazmaz(
    api_client: TestClient, fake_storage: dict[str, bytes]
) -> None:
    """R2'nin açık koşulu: öneriler insan onayı bekler, grafiğe kendiliğinden girmez."""
    tenant, token = _register_and_login(api_client, slug="cik", email="c@cik.com")
    entity = _create_company(api_client, token)
    document = _upload(api_client, token, entity_id=entity["id"])

    result = _run_extraction(tenant, document["id"])
    assert result["status"] == "completed"
    assert result["engine"] == "text"

    proposals = api_client.get(
        f"/api/v1/documents/{document['id']}/proposals", headers=_auth(token)
    ).json()
    kinds = {item["kind"] for item in proposals}
    assert "relationship" in kinds
    assert "attribute" in kinds
    assert all(item["status"] == "pending" for item in proposals)

    # Kütükte henüz ilişki YOK.
    relationships = api_client.get(
        f"/api/v1/entities/{entity['id']}/relationships", headers=_auth(token)
    ).json()
    assert relationships == []


def test_oneri_tckn_maskeli_doner(api_client: TestClient, fake_storage: dict[str, bytes]) -> None:
    tenant, token = _register_and_login(api_client, slug="msk", email="m@msk.com")
    entity = _create_company(api_client, token)
    document = _upload(api_client, token, entity_id=entity["id"])
    _run_extraction(tenant, document["id"])

    response = api_client.get(f"/api/v1/documents/{document['id']}/proposals", headers=_auth(token))
    assert GECERLI_TCKN not in response.text
    kisi = next(item for item in response.json() if item["kind"] == "relationship")
    assert kisi["payload"]["national_id"] == "*******0146"


def test_cikarim_idempotenttir(api_client: TestClient, fake_storage: dict[str, bytes]) -> None:
    tenant, token = _register_and_login(api_client, slug="idm", email="id@idm.com")
    entity = _create_company(api_client, token)
    document = _upload(api_client, token, entity_id=entity["id"])
    first = _run_extraction(tenant, document["id"])
    second = _run_extraction(tenant, document["id"])
    assert first["status"] == "completed"
    # İkinci koşu yeniden çalışmaz (durum artık pending değil).
    assert second["status"] == "completed"
    proposals = api_client.get(
        f"/api/v1/documents/{document['id']}/proposals", headers=_auth(token)
    ).json()
    assert len(proposals) == first["proposals"]


def test_basarisiz_cikarim_yeniden_denenir(
    api_client: TestClient, fake_storage: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Motor düştüğünde "failed" kalan belge, yeniden deneme ucuyla işlenebilir hale gelir."""
    tenant, token = _register_and_login(api_client, slug="retry", email="re@try.com")
    entity = _create_company(api_client, token)
    document = _upload(api_client, token, entity_id=entity["id"])

    def _dusen_motor(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("motor geçici olarak yok")

    with monkeypatch.context() as m:
        m.setattr("aegis_worker.tasks.documents.convert", _dusen_motor)
        assert _run_extraction(tenant, document["id"])["status"] == "failed"
    # İdempotent görev "failed" belgeye bir daha dokunmaz — eski davranışın kanıtı.
    assert _run_extraction(tenant, document["id"])["status"] == "failed"

    retry = api_client.post(f"/api/v1/documents/{document['id']}/extract", headers=_auth(token))
    assert retry.status_code == 202, retry.text
    assert retry.json()["extraction_status"] == "pending"
    assert retry.json()["extraction_error"] is None

    result = _run_extraction(tenant, document["id"])
    assert result["status"] == "completed"
    assert result["proposals"] >= 1

    events = api_client.get(
        "/api/v1/audit/events", params={"action": "document.extraction_retry"}, headers=_auth(token)
    ).json()
    items = events["items"] if isinstance(events, dict) else events
    assert any(e.get("action") == "document.extraction_retry" for e in items)


def test_tamamlanmis_cikarim_yeniden_denenemez(
    api_client: TestClient, fake_storage: dict[str, bytes]
) -> None:
    tenant, token = _register_and_login(api_client, slug="retry2", email="re2@try.com")
    document = _upload(api_client, token)
    assert _run_extraction(tenant, document["id"])["status"] == "completed"
    response = api_client.post(f"/api/v1/documents/{document['id']}/extract", headers=_auth(token))
    assert response.status_code == 409


def test_cikarimsiz_tur_yeniden_denenemez(
    api_client: TestClient, fake_storage: dict[str, bytes]
) -> None:
    _tenant, token = _register_and_login(api_client, slug="retry3", email="re3@try.com")
    document = _upload(api_client, token, doc_type="other")
    assert document["extraction_status"] == "skipped"
    response = api_client.post(f"/api/v1/documents/{document['id']}/extract", headers=_auth(token))
    assert response.status_code == 409


def test_denetci_cikarimi_yeniden_deneyemez(
    api_client: TestClient, fake_storage: dict[str, bytes]
) -> None:
    tenant, token = _register_and_login(api_client, slug="retry4", email="re4@try.com")
    document = _upload(api_client, token)
    auditor = _role_token(tenant, "auditor")
    response = api_client.post(
        f"/api/v1/documents/{document['id']}/extract", headers=_auth(auditor)
    )
    assert response.status_code == 403


def test_oneri_govdesinde_tckn_duz_metin_durmaz(
    api_client: TestClient, fake_storage: dict[str, bytes], admin_database_url: str
) -> None:
    """ADR-0007 §5: şifresiz alanlara TCKN'nin yalnız maskesi girer — öneri gövdesi dahil."""
    from sqlalchemy import create_engine, text

    tenant, token = _register_and_login(api_client, slug="tckn-enc", email="t@enc.com")
    document = _upload(api_client, token)
    _run_extraction(tenant, document["id"])

    engine = create_engine(admin_database_url)
    try:
        with engine.connect() as conn:
            rows = (
                conn.execute(
                    text("SELECT payload::text FROM extraction_proposal WHERE document_id = :d"),
                    {"d": document["id"]},
                )
                .scalars()
                .all()
            )
    finally:
        engine.dispose()
    assert rows, "öneri üretilmedi"
    assert all(GECERLI_TCKN not in row for row in rows)
    assert any("national_id_enc" in row for row in rows)


# ── Öneri kararı ─────────────────────────────────────────────────────────────


def test_kisi_onerisi_kabul_edilince_kisi_ve_iliski_olusur(
    api_client: TestClient, fake_storage: dict[str, bytes]
) -> None:
    tenant, token = _register_and_login(api_client, slug="kbl", email="k@kbl.com")
    entity = _create_company(api_client, token)
    document = _upload(api_client, token, entity_id=entity["id"])
    _run_extraction(tenant, document["id"])

    proposals = api_client.get(
        f"/api/v1/documents/{document['id']}/proposals", headers=_auth(token)
    ).json()
    kisi_onerisi = next(item for item in proposals if item["kind"] == "relationship")

    accepted = api_client.post(
        f"/api/v1/documents/{document['id']}/proposals/{kisi_onerisi['id']}/decision",
        json={"decision": "accepted", "note": "Sirkülerden teyit edildi."},
        headers=_auth(token),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["resulting_entity_id"]

    relationships = api_client.get(
        f"/api/v1/entities/{entity['id']}/relationships", headers=_auth(token)
    ).json()
    assert len(relationships) == 1
    assert relationships[0]["rel_type"] == "officer"
    assert relationships[0]["source_type"] == "document"
    # Kanıt referansı belgeye işaret eder (Invariant 4).
    assert relationships[0]["document_id"] == document["id"]


def test_oznitelik_onerisi_kabul_edilince_beyanin_ustune_yazmaz(
    api_client: TestClient, fake_storage: dict[str, bytes]
) -> None:
    """Belge gözlemi beyanı ezmez; ikisi ayrı durur ve çelişirse tutarsızlık üretir."""
    tenant, token = _register_and_login(api_client, slug="ozn", email="oz@ozn.com")
    entity = _create_company(api_client, token)
    metin = IMZA_SIRKULERI_METNI.replace(GECERLI_VKN, "1234567891")
    document = _upload(api_client, token, entity_id=entity["id"], content=metin)
    _run_extraction(tenant, document["id"])

    proposals = api_client.get(
        f"/api/v1/documents/{document['id']}/proposals", headers=_auth(token)
    ).json()
    vergi_onerisi = next(
        item
        for item in proposals
        if item["kind"] == "attribute" and item["payload"]["name"] == "taxNumber"
    )
    api_client.post(
        f"/api/v1/documents/{document['id']}/proposals/{vergi_onerisi['id']}/decision",
        json={"decision": "accepted"},
        headers=_auth(token),
    )

    guncel = api_client.get(f"/api/v1/entities/{entity['id']}", headers=_auth(token)).json()
    assert guncel["tax_number"] == GECERLI_VKN  # beyan korunur

    discrepancies = api_client.get(
        f"/api/v1/entities/{entity['id']}/discrepancies", headers=_auth(token)
    ).json()
    assert len(discrepancies) == 1
    assert discrepancies[0]["attribute_name"] == "taxNumber"
    assert discrepancies[0]["severity"] == "critical"


def test_reddedilen_oneri_silinmez(api_client: TestClient, fake_storage: dict[str, bytes]) -> None:
    """ "Belgede vardı ama uzman kabul etmedi" bilgisi denetimde anlamlıdır."""
    tenant, token = _register_and_login(api_client, slug="red", email="r@red.com")
    entity = _create_company(api_client, token)
    document = _upload(api_client, token, entity_id=entity["id"])
    _run_extraction(tenant, document["id"])
    proposal = api_client.get(
        f"/api/v1/documents/{document['id']}/proposals", headers=_auth(token)
    ).json()[0]

    rejected = api_client.post(
        f"/api/v1/documents/{document['id']}/proposals/{proposal['id']}/decision",
        json={"decision": "rejected", "note": "Bu kişi artık yetkili değil."},
        headers=_auth(token),
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["review_note"]

    kalanlar = api_client.get(
        f"/api/v1/documents/{document['id']}/proposals", headers=_auth(token)
    ).json()
    assert any(item["id"] == proposal["id"] for item in kalanlar)


def test_karara_baglanmis_oneri_tekrar_karara_baglanamaz(
    api_client: TestClient, fake_storage: dict[str, bytes]
) -> None:
    tenant, token = _register_and_login(api_client, slug="tkr", email="tk@tkr.com")
    entity = _create_company(api_client, token)
    document = _upload(api_client, token, entity_id=entity["id"])
    _run_extraction(tenant, document["id"])
    proposal = api_client.get(
        f"/api/v1/documents/{document['id']}/proposals", headers=_auth(token)
    ).json()[0]
    url = f"/api/v1/documents/{document['id']}/proposals/{proposal['id']}/decision"
    api_client.post(url, json={"decision": "rejected"}, headers=_auth(token))
    ikinci = api_client.post(url, json={"decision": "accepted"}, headers=_auth(token))
    assert ikinci.status_code == 400


def test_ayni_kisi_ikinci_belgede_yeniden_olusturulmaz(
    api_client: TestClient, fake_storage: dict[str, bytes]
) -> None:
    """Varlık çözümleme (ER): aynı TCKN'li kişi ikinci dosyada mükerrer kayıt açmaz."""
    tenant, token = _register_and_login(api_client, slug="er-doc", email="e@erdoc.com")
    entity = _create_company(api_client, token)

    ilk = _upload(api_client, token, entity_id=entity["id"], filename="sirküler-1.txt")
    _run_extraction(tenant, ilk["id"])
    ilk_oneri = next(
        item
        for item in api_client.get(
            f"/api/v1/documents/{ilk['id']}/proposals", headers=_auth(token)
        ).json()
        if item["kind"] == "relationship"
    )
    ilk_sonuc = api_client.post(
        f"/api/v1/documents/{ilk['id']}/proposals/{ilk_oneri['id']}/decision",
        json={"decision": "accepted"},
        headers=_auth(token),
    ).json()

    ikinci = _upload(
        api_client,
        token,
        entity_id=entity["id"],
        filename="sirküler-2.txt",
        content=IMZA_SIRKULERI_METNI + "\nEk sayfa.\n",
    )
    _run_extraction(tenant, ikinci["id"])
    ikinci_oneri = next(
        item
        for item in api_client.get(
            f"/api/v1/documents/{ikinci['id']}/proposals", headers=_auth(token)
        ).json()
        if item["kind"] == "relationship"
    )
    ikinci_sonuc = api_client.post(
        f"/api/v1/documents/{ikinci['id']}/proposals/{ikinci_oneri['id']}/decision",
        json={"decision": "accepted"},
        headers=_auth(token),
    ).json()

    assert ikinci_sonuc["resulting_entity_id"] == ilk_sonuc["resulting_entity_id"]


# ── RBAC ve denetim ──────────────────────────────────────────────────────────


def test_denetci_belge_yukleyemez(api_client: TestClient, fake_storage: dict[str, bytes]) -> None:
    tenant, _token = _register_and_login(api_client, slug="rbac-doc", email="rb@doc.com")
    auditor = _role_token(tenant, "auditor")
    response = api_client.post(
        "/api/v1/documents",
        files={"file": ("x.txt", b"metin", "text/plain")},
        data={"doc_type": "other"},
        headers=_auth(auditor),
    )
    assert response.status_code == 403


def test_belge_akisi_denetim_zincirini_bozmaz(
    api_client: TestClient, fake_storage: dict[str, bytes]
) -> None:
    tenant, token = _register_and_login(api_client, slug="dnt", email="d@dnt.com")
    entity = _create_company(api_client, token)
    document = _upload(api_client, token, entity_id=entity["id"])
    _run_extraction(tenant, document["id"])
    proposal = api_client.get(
        f"/api/v1/documents/{document['id']}/proposals", headers=_auth(token)
    ).json()[0]
    api_client.post(
        f"/api/v1/documents/{document['id']}/proposals/{proposal['id']}/decision",
        json={"decision": "rejected", "note": "gerekmiyor"},
        headers=_auth(token),
    )
    verify = api_client.get("/api/v1/audit/verify", headers=_auth(token))
    assert verify.json()["ok"] is True
