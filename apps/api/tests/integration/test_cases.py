"""Tam izleme + vaka yönetimi (E3.1/E3.2) uçtan uca.

Faz 3 çıkış ölçütü: *"A dataset change on a monitored entity flows end-to-end unattended:
diff → alert → case → re-scored dossier"*. yente ``httpx.MockTransport`` ile taklit edilir.
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

BASE: list[dict[str, Any]] = [
    {
        "id": "NK-LOW",
        "caption": "Denizli Ticaret",
        "schema": "Company",
        "score": 0.55,
        "match": False,
        "datasets": ["default"],
        "properties": {},
    }
]
SANCTION = {
    "id": "NK-SANCTION-NEW",
    "caption": "Deniz Ticaret Ltd",
    "schema": "Company",
    "score": 0.93,
    "match": True,
    "datasets": ["default"],
    "properties": {"topics": ["sanction"]},
}
PEP = {
    "id": "NK-PEP-NEW",
    "caption": "Deniz Ticaret Holding",
    "schema": "Company",
    "score": 0.81,
    "match": False,
    "datasets": ["default"],
    "properties": {"topics": ["role.pep"]},
}
REASON = "Kimlik ve sicil kaydı karşılaştırıldı, belge dosyada."


def _install(client: TestClient, results: list[dict[str, Any]]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"responses": {f"s{i}": {"status": 200, "results": results} for i in range(4)}},
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://yente")
    client.app.state.yente_client = YenteClient("http://yente", client=http)  # type: ignore[attr-defined]


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


def _role_token(tenant: str, role: str) -> str:
    return create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant),
        role=role,
        secret=os.environ["AUTH_SECRET"],
        expires_in_minutes=60,
    )


def _watched_entity(client: TestClient, token: str, name: str) -> str:
    entity = client.post(
        "/api/v1/entities", json={"name": name, "schema_type": "Company"}, headers=_auth(token)
    ).json()["entity"]
    client.put(
        f"/api/v1/entities/{entity['id']}/monitoring",
        json={"monitored": True},
        headers=_auth(token),
    )
    return str(entity["id"])


def _run(client: TestClient, token: str) -> dict[str, int]:
    res = client.post("/api/v1/monitoring/run", headers=_auth(token))
    assert res.status_code == 200, res.text
    return dict(res.json())


def test_sanction_change_flows_to_edd_case_and_rescored_dossier(api_client: TestClient) -> None:
    token, tenant = _register(api_client, "vaka1")
    entity_id = _watched_entity(api_client, token, "Deniz Ticaret A.Ş.")

    _install(api_client, BASE)
    assert _run(api_client, token)["alerts"] == 0  # taban

    _install(api_client, [*BASE, SANCTION])
    assert _run(api_client, token)["alerts"] == 1

    (alert,) = api_client.get("/api/v1/monitoring/alerts", headers=_auth(token)).json()["items"]
    assert (alert["severity"], alert["severity_label"]) == ("critical", "Kritik")
    assert alert["case_id"] is not None
    re = alert["reassessment"]
    assert re["snapshot_id"]
    assert re["score_after"] is not None

    # Gözetimsiz: alarm vakayı kendisi açtı, EDD işaretli, kontrol listesiyle.
    listing = api_client.get("/api/v1/cases", headers=_auth(token)).json()
    assert listing["summary"]["open"] == 1
    assert listing["summary"]["edd_open"] == 1
    (case,) = listing["items"]
    assert case["id"] == alert["case_id"]
    assert (case["source"], case["status"], case["edd"]) == ("monitoring_alert", "new", True)
    assert case["entity_id"] == entity_id
    assert case["due_at"] is not None

    # Aynı veriyle yeniden koşu: yeni alarm yok, ikinci vaka yok (idempotent).
    assert _run(api_client, token)["alerts"] == 0
    assert api_client.get("/api/v1/cases", headers=_auth(token)).json()["summary"]["open"] == 1

    cid = case["id"]
    detail = api_client.get(f"/api/v1/cases/{cid}", headers=_auth(token)).json()
    assert detail["allowed_actions"] == ["start_review", "escalate"]
    assert [e["action"] for e in detail["history"]] == ["case.open"]
    assert len(detail["edd_checklist"]) == 7
    assert detail["edd_complete"] is False

    # İnceleme: eşleşmeyi onayla (taramanın karar ucu), vakada yükselt.
    started = api_client.post(
        f"/api/v1/cases/{cid}/actions", json={"action": "start_review"}, headers=_auth(token)
    )
    assert started.json()["status"] == "in_review"
    screening = api_client.get(
        f"/api/v1/screenings/{alert['screening_id']}", headers=_auth(token)
    ).json()
    hit = next(c for c in screening["candidates"] if c["external_id"] == "NK-SANCTION-NEW")
    decided = api_client.post(
        f"/api/v1/screenings/{alert['screening_id']}/candidates/{hit['id']}/decision",
        json={"decision": "confirmed", "note": "Sicil numarası birebir tutuyor."},
        headers=_auth(token),
    )
    assert decided.status_code == 200, decided.text
    escalated = api_client.post(
        f"/api/v1/cases/{cid}/actions",
        json={"action": "escalate", "reason": "Yaptırım eşleşmesi onaylandı, EDD başlıyor."},
        headers=_auth(token),
    ).json()
    assert escalated["status"] == "escalated"

    # Liste tamamlanmadan karar yok.
    blocked = api_client.post(
        f"/api/v1/cases/{cid}/actions",
        json={"action": "approve", "reason": REASON},
        headers=_auth(token),
    )
    assert blocked.status_code == 409

    no_note = api_client.put(
        f"/api/v1/cases/{cid}/edd/match_evidence", json={"done": True}, headers=_auth(token)
    )
    assert no_note.status_code == 400
    for item in detail["edd_checklist"]:
        ok = api_client.put(
            f"/api/v1/cases/{cid}/edd/{item['key']}",
            json={"done": True, "note": "Belge dosyaya eklendi."},
            headers=_auth(token),
        )
        assert ok.status_code == 200, ok.text
    comment = api_client.post(
        f"/api/v1/cases/{cid}/comments",
        json={"body": "Müşteri ilişkisi askıya alındı."},
        headers=_auth(token),
    )
    assert comment.status_code == 201

    closed = api_client.post(
        f"/api/v1/cases/{cid}/actions",
        json={"action": "close", "reason": "İlişki sonlandırıldı; değerlendirme kayıtlı."},
        headers=_auth(token),
    ).json()
    assert closed["status"] == "closed"
    assert closed["closed_at"]
    assert closed["edd_complete"]
    actions = [e["action"] for e in closed["history"]]
    assert actions[0] == "case.open"
    assert actions[-1] == "case.transition"
    assert actions.count("case.edd_item") == 7
    assert "case.comment" in actions
    snap_id = closed["history"][-1]["payload"]["risk_score_snapshot_id"]
    assert snap_id

    # Dosya yeniden puanlandı: kararla alınan kayıt onaylı yaptırımı içerir, puan yükseldi.
    score = api_client.get(f"/api/v1/reports/score/{entity_id}", headers=_auth(token)).json()
    assert score["recorded"] is True
    assert score["history"][0]["id"] == snap_id
    assert score["history"][0]["reason"] == "case_decision"
    assert score["history"][0]["score"] > re["score_after"]

    # Kapanmış vakada madde değiştirilemez; denetçi geçmişi görür ama dokunamaz.
    late = api_client.put(
        f"/api/v1/cases/{cid}/edd/match_evidence",
        json={"done": False},
        headers=_auth(token),
    )
    assert late.status_code == 409
    auditor = _role_token(tenant, "auditor")
    seen = api_client.get(f"/api/v1/cases/{cid}", headers=_auth(auditor))
    assert seen.status_code == 200
    assert seen.json()["allowed_actions"] == []
    denied = api_client.post(
        f"/api/v1/cases/{cid}/comments", json={"body": "deneme"}, headers=_auth(auditor)
    )
    assert denied.status_code == 403


def test_pep_alert_opens_plain_case_and_analyst_cannot_decide(api_client: TestClient) -> None:
    token, tenant = _register(api_client, "vaka2")
    _watched_entity(api_client, token, "Deniz Ticaret Holding A.Ş.")
    _install(api_client, BASE)
    _run(api_client, token)
    _install(api_client, [*BASE, PEP])
    assert _run(api_client, token)["alerts"] == 1

    (case,) = api_client.get("/api/v1/cases", headers=_auth(token)).json()["items"]
    assert (case["severity"], case["edd"]) == ("high", False)

    analyst = _role_token(tenant, "analyst")
    cid = case["id"]
    review = api_client.post(
        f"/api/v1/cases/{cid}/actions", json={"action": "start_review"}, headers=_auth(analyst)
    )
    assert review.status_code == 200
    approve = api_client.post(
        f"/api/v1/cases/{cid}/actions",
        json={"action": "approve", "reason": REASON},
        headers=_auth(analyst),
    )
    assert approve.status_code == 403
    short = api_client.post(
        f"/api/v1/cases/{cid}/actions",
        json={"action": "approve", "reason": "tamam"},
        headers=_auth(token),
    )
    assert short.status_code == 400
    ok = api_client.post(
        f"/api/v1/cases/{cid}/actions",
        json={"action": "approve", "reason": REASON},
        headers=_auth(token),
    )
    assert ok.json()["status"] == "approved"


def test_manual_case_assignment_and_queue_filters(api_client: TestClient) -> None:
    token, tenant = _register(api_client, "vaka3")
    entity = api_client.post(
        "/api/v1/entities",
        json={"name": "Yıldız İnşaat A.Ş.", "schema_type": "Company"},
        headers=_auth(token),
    ).json()["entity"]
    created = api_client.post(
        "/api/v1/cases",
        json={
            "entity_id": entity["id"],
            "title": "Ortaklık yapısı değişikliği",
            "severity": "high",
            "note": "Ticaret sicilinde yeni ortak görünüyor.",
        },
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source"] == "manual"
    assert body["edd"] is False
    assert [c["body"] for c in body["comments"]] == ["Ticaret sicilinde yeni ortak görünüyor."]

    members = api_client.get("/api/v1/members", headers=_auth(token)).json()
    me = members[0]["user_id"]
    assigned = api_client.put(
        f"/api/v1/cases/{body['id']}/assignee", json={"user_id": me}, headers=_auth(token)
    )
    assert assigned.json()["assignee_user_id"] == me
    stranger = api_client.put(
        f"/api/v1/cases/{body['id']}/assignee",
        json={"user_id": str(uuid.uuid4())},
        headers=_auth(token),
    )
    assert stranger.status_code == 400

    mine = api_client.get("/api/v1/cases", params={"mine": "true"}, headers=_auth(token)).json()
    assert [c["id"] for c in mine["items"]] == [body["id"]]
    assert mine["summary"]["mine"] == 1
    assert mine["summary"]["unassigned"] == 0

    past = api_client.put(
        f"/api/v1/cases/{body['id']}/due",
        json={"due_at": "2026-01-01T00:00:00Z"},
        headers=_auth(token),
    )
    assert past.json()["overdue"] is True
    overdue = api_client.get(
        "/api/v1/cases", params={"overdue": "true"}, headers=_auth(token)
    ).json()
    assert overdue["summary"]["overdue"] == 1
    assert len(overdue["items"]) == 1

    analyst = _role_token(tenant, "analyst")
    due = api_client.put(
        f"/api/v1/cases/{body['id']}/due",
        json={"due_at": "2027-01-01T00:00:00Z"},
        headers=_auth(analyst),
    )
    assert due.status_code == 403

    # Başka kiracı bu vakayı göremez (RLS).
    other, _ = _register(api_client, "vaka3b")
    assert api_client.get(f"/api/v1/cases/{body['id']}", headers=_auth(other)).status_code == 404
    assert api_client.get("/api/v1/cases", headers=_auth(other)).json()["items"] == []


def test_one_alert_opens_at_most_one_case(api_client: TestClient, app_database_url: str) -> None:
    """Gece koşusu yeniden denense bile bir alarm ikinci vaka açamaz (tekillik kısıtı + servis)."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import IntegrityError

    token, tenant = _register(api_client, "vaka4")
    _watched_entity(api_client, token, "Marmara Gıda A.Ş.")
    _install(api_client, BASE)
    _run(api_client, token)
    _install(api_client, [*BASE, SANCTION])
    _run(api_client, token)
    (alert,) = api_client.get("/api/v1/monitoring/alerts", headers=_auth(token)).json()["items"]

    engine = create_engine(app_database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant})
            duplicate = text(
                "INSERT INTO compliance_case (tenant_id, entity_id, title, source, "
                "source_alert_id, severity) VALUES (:t, :e, 'kopya', 'monitoring_alert', "
                ":a, 'critical')"
            )
            params = {"t": tenant, "e": alert["entity_id"], "a": alert["id"]}
            with pytest.raises(IntegrityError):
                conn.execute(duplicate, params)
            conn.rollback()
    finally:
        engine.dispose()
    assert api_client.get("/api/v1/cases", headers=_auth(token)).json()["summary"]["open"] == 1
