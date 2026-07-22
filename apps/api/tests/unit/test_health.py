"""DB gerektirmeyen API birim testi: liveness + sürüm uçları."""

from __future__ import annotations

from fastapi.testclient import TestClient

from aegis_api.main import create_app


def test_healthz_and_version() -> None:
    with TestClient(create_app()) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        version = client.get("/api/v1/system/version")
        assert version.status_code == 200
        body = version.json()
        assert body["name"] == "AEGIS"
        assert body["environment"] == "development"
