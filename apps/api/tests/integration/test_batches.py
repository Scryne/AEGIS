"""Toplu tarama (E3.3) uçtan uca: CSV → önizleme → taslak → başlat → parça parça işle → sonuç.

yente ``httpx.MockTransport`` ile taklit edilir; taklit, sorgudaki ada bakarak yalnız
"Karanlık" geçen öznelere yaptırımlı bir aday döndürür.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from aegis_core.screening.yente import YenteClient
from aegis_core.security.tokens import create_access_token

pytestmark = pytest.mark.integration

SANCTION = {
    "id": "NK-KARANLIK",
    "caption": "Karanlık Lojistik Ltd",
    "schema": "Company",
    "score": 0.95,
    "match": True,
    "datasets": ["default"],
    "properties": {"topics": ["sanction"]},
}


def _install(client: TestClient, *, fail: bool = False) -> list[int]:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if fail:
            return httpx.Response(503, json={"detail": "down"})
        queries = json.loads(request.content)["queries"]
        responses = {}
        for key, q in queries.items():
            names = " ".join(q["properties"].get("name", []))
            results = [SANCTION] if "Karanlık" in names or "Karanlik" in names else []
            responses[key] = {"status": 200, "results": results}
        return httpx.Response(200, json={"responses": responses})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://yente")
    client.app.state.yente_client = YenteClient("http://yente", client=http)  # type: ignore[attr-defined]
    return calls


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, slug: str) -> tuple[str, str]:
    email = f"u@{slug}.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={"org_name": slug, "org_slug": slug, "email": email, "password": "sifre-12345"},
    )
    assert reg.status_code == 201, reg.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "sifre-12345"})
    return str(login.json()["access_token"]), str(reg.json()["tenant_id"])


def _entity(client: TestClient, token: str, name: str, **extra: Any) -> str:
    res = client.post(
        "/api/v1/entities",
        json={"name": name, "schema_type": "Company", **extra},
        headers=_auth(token),
    )
    assert res.status_code == 201, res.text
    return str(res.json()["entity"]["id"])


CSV = (
    "Müşteri No;Ticaret Unvanı;Vergi No;Tür\r\n"
    "C-1;Deniz Ticaret A.Ş.;4840847211;şirket\r\n"
    "C-2;Karanlık Lojistik Ltd;;şirket\r\n"
    "C-3;Ayşe Kaya;;kişi\r\n"
    "C-4;Karanlık Lojistik Ltd;;şirket\r\n"
    "C-5;;;şirket\r\n"
    "C-6;Yıldız Gıda A.Ş.;;şirket\r\n"
).encode("cp1254")

MAPPING = {
    "name": "Ticaret Unvanı",
    "tax_number": "Vergi No",
    "schema_type": "Tür",
    "external_ref": "Müşteri No",
}


def test_batch_end_to_end(api_client: TestClient) -> None:
    token, tenant = _register(api_client, "toplu1")
    existing = _entity(api_client, token, "Deniz Ticaret Anonim Şirketi", tax_number="4840847211")
    yildiz_a = _entity(api_client, token, "Yıldız Gıda A.Ş.")
    _entity(api_client, token, "Yıldız Gıda A.Ş.")  # aynı ad iki kayıt → ER belirsiz

    files = {"file": ("müşteriler.csv", CSV, "text/csv")}
    prev = api_client.post("/api/v1/batches/preview", files=files, headers=_auth(token))
    assert prev.status_code == 200, prev.text
    p = prev.json()
    assert p["suggested_mapping"] == {**MAPPING, "mersis_number": None, "country": None}
    assert (p["total_rows"], p["valid_rows"], p["invalid_rows"], p["duplicate_rows"]) == (
        6,
        4,
        1,
        1,
    )

    created = api_client.post(
        "/api/v1/batches",
        files=files,
        data={"mapping": json.dumps(MAPPING)},
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text
    batch = created.json()
    bid = batch["id"]
    assert batch["status"] == "draft"
    assert (batch["counts"]["pending"], batch["counts"]["invalid"]) == (4, 1)
    assert batch["counts"]["duplicate"] == 1

    calls = _install(api_client)
    started = api_client.post(f"/api/v1/batches/{bid}/start", headers=_auth(token))
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "queued"
    again = api_client.post(f"/api/v1/batches/{bid}/start", headers=_auth(token))
    assert again.status_code == 409

    # Parça parça: 2 + kalan. Yarıda kalan iş kaldığı yerden devam eder.
    first = api_client.post(
        f"/api/v1/batches/{bid}/process", params={"limit": 2}, headers=_auth(token)
    ).json()
    assert (first["processed"], first["remaining"]) == (2, 2)
    second = api_client.post(f"/api/v1/batches/{bid}/process", headers=_auth(token)).json()
    assert second == {"processed": 2, "done": 1, "needs_review": 1, "failed": 0, "remaining": 0}
    assert len(calls) == 3  # belirsiz satır taranmadı

    state = api_client.get(f"/api/v1/batches/{bid}", headers=_auth(token)).json()
    assert state["status"] == "completed"
    assert state["counts"]["done"] == 3
    assert state["counts"]["needs_review"] == 1
    assert state["risk"]["sanction_rows"] == 1

    rows = api_client.get(f"/api/v1/batches/{bid}/rows", headers=_auth(token)).json()
    assert rows["total"] == 6
    top = rows["items"][0]
    assert (top["row_no"], top["sanction_hits"], top["resolution"]) == (3, 1, "new")
    by_no = {r["row_no"]: r for r in rows["items"]}
    assert by_no[2]["resolution"] == "matched"
    assert by_no[2]["entity_id"] == existing
    assert by_no[4]["data"]["schema_type"] == "Person"
    assert by_no[5]["status"] == "duplicate"
    assert by_no[5]["duplicate_of"] == 3
    assert by_no[6]["status"] == "invalid"
    review = by_no[7]
    assert review["status"] == "needs_review"
    assert len(review["resolution_candidates"]) == 2

    # Riskli satır gerçekten bir tarama ve varlığa bağlı; varlık kaynağı toplu işi gösterir.
    screening = api_client.get(
        f"/api/v1/screenings/{top['screening_id']}", headers=_auth(token)
    ).json()
    assert screening["entity_id"] == top["entity_id"]

    # İnsan kararı: belirsiz satır mevcut bir varlığa bağlanır, yeniden kuyruğa girer, taranır.
    resolved = api_client.post(
        f"/api/v1/batches/{bid}/rows/{review['id']}/resolve",
        json={"entity_id": yildiz_a},
        headers=_auth(token),
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "pending"
    tail = api_client.post(f"/api/v1/batches/{bid}/process", headers=_auth(token)).json()
    assert tail["done"] == 1
    assert tail["remaining"] == 0
    rows = api_client.get(
        f"/api/v1/batches/{bid}/rows", params={"status": "done"}, headers=_auth(token)
    ).json()
    assert rows["total"] == 4

    # Toplu işlem: riskli satır için vaka (yaptırım → kritik, EDD) ve izleme.
    case = api_client.post(
        f"/api/v1/batches/{bid}/bulk",
        json={"action": "open_case", "row_ids": [top["id"], by_no[6]["id"]]},
        headers=_auth(token),
    ).json()
    assert case == {"applied": 1, "skipped": 1}
    (opened,) = api_client.get("/api/v1/cases", headers=_auth(token)).json()["items"]
    assert (opened["severity"], opened["edd"], opened["source"]) == ("critical", True, "screening")
    monitor = api_client.post(
        f"/api/v1/batches/{bid}/bulk",
        json={"action": "monitor", "row_ids": [top["id"]]},
        headers=_auth(token),
    ).json()
    assert monitor["applied"] == 1

    export = api_client.get(f"/api/v1/batches/{bid}/export.csv", headers=_auth(token))
    assert export.status_code == 200
    assert (
        "filename*=UTF-8''m%C3%BC%C5%9Fteriler-sonuc.csv" in export.headers["content-disposition"]
    )
    lines = export.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Satır;Ad / unvan")
    assert lines[1].startswith("3;Karanlık Lojistik Ltd")  # riskli satır en üstte
    assert len(lines) == 7

    events = api_client.get(
        "/api/v1/audit/events", params={"object_type": "screening_batch"}, headers=_auth(token)
    ).json()
    actions = {e["action"] for e in events["items"]}
    assert {"batch.create", "batch.start", "batch.row_resolve", "batch.complete"} <= actions

    # Denetçi okur, başlatamaz; başka kiracı göremez.
    auditor = create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant),
        role="auditor",
        secret=os.environ["AUTH_SECRET"],
        expires_in_minutes=60,
    )
    assert api_client.get(f"/api/v1/batches/{bid}", headers=_auth(auditor)).status_code == 200
    assert (
        api_client.post(f"/api/v1/batches/{bid}/cancel", headers=_auth(auditor)).status_code == 403
    )
    other, _ = _register(api_client, "toplu1b")
    assert api_client.get(f"/api/v1/batches/{bid}", headers=_auth(other)).status_code == 404


def test_national_id_column_rejected_and_quota_enforced(api_client: TestClient) -> None:
    token, _ = _register(api_client, "toplu2")
    tckn = "Ad;TCKN\r\nAyşe Kaya;12345678901\r\n".encode()  # sağlama toplamı bilerek bozuk
    bad = api_client.post(
        "/api/v1/batches",
        files={"file": ("k.csv", tckn, "text/csv")},
        data={"mapping": json.dumps({"name": "Ad", "external_ref": "TCKN"})},
        headers=_auth(token),
    )
    assert bad.status_code == 400
    assert "TCKN" in bad.json()["error"]["message"]

    # Pilot planının aylık hakkını aşan toplu iş başlatılamaz (satırlar kotaya sayılır).
    usage = api_client.get("/api/v1/billing/usage", headers=_auth(token)).json()
    included = usage["remaining_queries"]
    body = "Ad\r\n" + "".join(f"Şirket {i} A.Ş.\r\n" for i in range(included + 1))
    created = api_client.post(
        "/api/v1/batches",
        files={"file": ("buyuk.csv", body.encode(), "text/csv")},
        data={"mapping": json.dumps({"name": "Ad"})},
        headers=_auth(token),
    ).json()
    start = api_client.post(f"/api/v1/batches/{created['id']}/start", headers=_auth(token))
    assert start.status_code == 402
    assert (
        api_client.get(f"/api/v1/batches/{created['id']}", headers=_auth(token)).json()["status"]
        == "draft"
    )


def test_engine_outage_marks_rows_failed_and_retry_recovers(api_client: TestClient) -> None:
    token, _ = _register(api_client, "toplu3")
    body = "Ad\r\nKaranlık Lojistik Ltd\r\nMavi Deniz A.Ş.\r\n".encode()
    bid = api_client.post(
        "/api/v1/batches",
        files={"file": ("a.csv", body, "text/csv")},
        data={"mapping": json.dumps({"name": "Ad"})},
        headers=_auth(token),
    ).json()["id"]
    api_client.post(f"/api/v1/batches/{bid}/start", headers=_auth(token))

    _install(api_client, fail=True)
    down = api_client.post(f"/api/v1/batches/{bid}/process", headers=_auth(token)).json()
    assert (down["failed"], down["remaining"]) == (2, 0)
    rows = api_client.get(f"/api/v1/batches/{bid}/rows", headers=_auth(token)).json()["items"]
    assert all("yeniden denenebilir" in (r["error"] or "") for r in rows)

    _install(api_client)
    retry = api_client.post(f"/api/v1/batches/{bid}/retry", headers=_auth(token))
    assert retry.json()["counts"]["pending"] == 2
    queued = api_client.get(f"/api/v1/batches/{bid}/rows", headers=_auth(token)).json()["items"]
    assert all(r["error"] is None for r in queued)  # eski hata yeni denemede gösterilmez
    up = api_client.post(f"/api/v1/batches/{bid}/process", headers=_auth(token)).json()
    assert (up["done"], up["remaining"]) == (2, 0)
    # Yeniden denemede varlık ikinci kez açılmaz (ilk denemede açılan kullanılır).
    entities = api_client.get("/api/v1/entities", headers=_auth(token)).json()
    names = [e["name"] for e in entities["items"]]
    assert sorted(names) == ["Karanlık Lojistik Ltd", "Mavi Deniz A.Ş."]


def test_worker_task_processes_in_committed_chunks(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Worker koroutini: parça başına commit, iptalde durur, kaldığı yerden devam eder."""
    import asyncio

    import aegis_worker.tasks.batch as task

    token, tenant = _register(api_client, "toplu4")
    names = [
        "Akdeniz Tekstil",
        "Boğaziçi Yazılım",
        "Çukurova Tarım",
        "Doruk Enerji",
        "Ercan Mobilya",
        "Fırat Madencilik",
        "Güneş Ambalaj",
    ]
    body = "Ad\r\n" + "".join(f"{n} A.Ş.\r\n" for n in names)
    bid = api_client.post(
        "/api/v1/batches",
        files={"file": ("w.csv", body.encode(), "text/csv")},
        data={"mapping": json.dumps({"name": "Ad"})},
        headers=_auth(token),
    ).json()["id"]

    # Görev taslağı göremezse (API commit'i henüz düşmedi) iş yapmadan yeniden dener.
    draft = asyncio.run(task._run(uuid.UUID(tenant), uuid.UUID(bid)))
    assert draft["not_visible"] is True
    assert draft["processed"] == 0

    api_client.post(f"/api/v1/batches/{bid}/start", headers=_auth(token))

    def fake_client(*_a: Any, **_k: Any) -> YenteClient:
        def handler(request: httpx.Request) -> httpx.Response:
            queries = json.loads(request.content)["queries"]
            return httpx.Response(
                200, json={"responses": {k: {"status": 200, "results": []} for k in queries}}
            )

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://y")
        return YenteClient("http://y", client=http)

    monkeypatch.setattr(task, "YenteClient", fake_client)
    monkeypatch.setattr(task, "CHUNK", 3)
    result = asyncio.run(task._run(uuid.UUID(tenant), uuid.UUID(bid)))
    assert (result["processed"], result["done"], result["remaining"]) == (7, 7, 0)
    state = api_client.get(f"/api/v1/batches/{bid}", headers=_auth(token)).json()
    assert state["status"] == "completed"
    assert state["counts"]["done"] == 7
