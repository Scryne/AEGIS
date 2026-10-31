"""Plan ve kota (E2.6, ADR-0012): kullanım sayımı, aşım izni olmayan planda 402, izleme sınırı.

Kota sayıları testte küçültülür (``PLANS`` sözlüğü çağrı anında okunur); plan değişikliği
``scripts/plan_ata.py`` ile aynı yoldan, ayrıcalıklı bağlantıyla yapılır.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from aegis_core.billing import plans
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
    }
]


def _install(client: TestClient, results: list[dict[str, Any]]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"responses": {f"s{i}": {"status": 200, "results": results} for i in range(8)}},
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://yente")
    client.app.state.yente_client = YenteClient("http://yente", client=http)  # type: ignore[attr-defined]


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


def _screen(client: TestClient, token: str, name: str, related: int = 0) -> int:
    body = {
        "subject": {"name": name, "subject_type": "company"},
        "related_subjects": [
            {"name": f"Kişi {i} {name}", "subject_type": "person"} for i in range(related)
        ],
    }
    return client.post("/api/v1/screenings", json=body, headers=_auth(token)).status_code


def _set_plan(admin_url: str, slug: str, plan: str) -> None:
    engine = create_engine(admin_url)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE organization SET plan_code = :p WHERE slug = :s"), {"p": plan, "s": slug}
        )
    engine.dispose()


def test_quota_counts_subjects_and_blocks_pilot(
    api_client: TestClient, admin_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(plans.PLANS, "pilot", plans.Plan("pilot", "Pilot", 3, 1, False))
    monkeypatch.setitem(plans.PLANS, "standart", plans.Plan("standart", "Standart", 3, 5, True))
    token = _register(api_client, "kota1")
    _install(api_client, BASE_RESULTS)

    usage = api_client.get("/api/v1/billing/usage", headers=_auth(token)).json()
    assert (usage["plan"]["code"], usage["used_queries"], usage["blocked"]) == ("pilot", 0, False)

    assert _screen(api_client, token, "Deniz Ticaret", related=1) == 201  # 2 özne
    usage = api_client.get("/api/v1/billing/usage", headers=_auth(token)).json()
    assert (usage["used_queries"], usage["remaining_queries"]) == (2, 1)

    # 2 + 2 > 3 → istek tümüyle reddedilir, kayıt oluşmaz.
    blocked = api_client.post(
        "/api/v1/screenings",
        json={
            "subject": {"name": "Ege Lojistik", "subject_type": "company"},
            "related_subjects": [{"name": "Ali Veli", "subject_type": "person"}],
        },
        headers=_auth(token),
    )
    assert blocked.status_code == 402
    assert blocked.json()["error"]["code"] == "quota_exceeded"
    assert api_client.get("/api/v1/billing/usage", headers=_auth(token)).json()["used_queries"] == 2

    assert _screen(api_client, token, "Marmara Gıda") == 201  # tam 3
    assert _screen(api_client, token, "Trakya Un") == 402
    assert api_client.get("/api/v1/billing/usage", headers=_auth(token)).json()["blocked"] is True

    # Aşım izni olan plana geçince tarama sürer, aşım ayrı sayılır.
    _set_plan(admin_database_url, "kota1", "standart")
    assert _screen(api_client, token, "Trakya Un") == 201
    usage = api_client.get("/api/v1/billing/usage", headers=_auth(token)).json()
    assert (usage["used_queries"], usage["overage_queries"], usage["blocked"]) == (4, 1, False)


def test_monitoring_limit_and_nightly_runs_do_not_count(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(plans.PLANS, "pilot", plans.Plan("pilot", "Pilot", 100, 1, False))
    token = _register(api_client, "kota2")
    _install(api_client, BASE_RESULTS)
    ids = [
        api_client.post(
            "/api/v1/entities",
            json={"name": name, "schema_type": "Company"},
            headers=_auth(token),
        ).json()["entity"]["id"]
        for name in ("Deniz Ticaret A.Ş.", "Ege Lojistik A.Ş.")
    ]

    def watch(eid: str, on: bool = True) -> int:
        return api_client.put(
            f"/api/v1/entities/{eid}/monitoring", json={"monitored": on}, headers=_auth(token)
        ).status_code

    assert watch(ids[0]) == 200
    assert watch(ids[0]) == 200  # zaten izleniyor: sınır yeniden sayılmaz
    second = api_client.put(
        f"/api/v1/entities/{ids[1]}/monitoring", json={"monitored": True}, headers=_auth(token)
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "plan_limit"
    assert watch(ids[0], on=False) == 200  # çıkarmak serbest
    assert watch(ids[1]) == 200

    run = api_client.post("/api/v1/monitoring/run", headers=_auth(token)).json()
    assert run["checked"] == 1
    usage = api_client.get("/api/v1/billing/usage", headers=_auth(token)).json()
    assert (usage["used_queries"], usage["monitored_entities"]) == (0, 1)  # gece koşusu sayılmaz
