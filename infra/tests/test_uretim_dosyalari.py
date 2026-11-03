"""Üretim dağıtım dosyalarının değişmezleri (E1.6) — Docker gerektirmez, her push'ta koşar.

``docker compose config`` sözdizimini CI'daki ayrı adım denetler; bu test **ilkeleri** denetler:
sır dosyada yok, dışarı yalnız Caddy açık, her uzun ömürlü serviste sınır + yeniden başlatma +
sağlık kontrolü var, uygulama RLS'ye tabi rolle bağlanıyor, deploy işi yalnız elle tetikleniyor.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra" / "compose" / "docker-compose.prod.yml"
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"
ENV_EXAMPLE = ROOT / "infra" / "compose" / "aegis.env.example"

EXPECTED_SERVICES = {
    "caddy", "web", "api", "migrate", "worker", "beat",
    "postgres", "redis", "minio", "elasticsearch", "yente",
}  # fmt: skip
SECRET_KEYS = re.compile(r"PASSWORD|SECRET|TOKEN|ENCRYPTION_KEY|ACCESS_KEY", re.IGNORECASE)
REQUIRED_INTERP = re.compile(r"\$\{[A-Z0-9_]+:\?[^}]*\}")


def _compose() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return data


def _env(service: dict[str, Any]) -> dict[str, str]:
    env = service.get("environment") or {}
    assert isinstance(env, dict), "environment eşlem (map) biçiminde olmalı"
    return {str(k): str(v) for k, v in env.items()}


def test_all_services_present() -> None:
    assert set(_compose()["services"]) == EXPECTED_SERVICES


def test_only_caddy_publishes_ports() -> None:
    for name, svc in _compose()["services"].items():
        if name == "caddy":
            assert sorted(svc["ports"]) == ["443:443", "443:443/udp", "80:80"]
        else:
            assert "ports" not in svc, f"{name} sunucuya port açmamalı"


def test_long_running_services_have_limits_restart_and_healthcheck() -> None:
    for name, svc in _compose()["services"].items():
        assert svc["deploy"]["resources"]["limits"]["memory"], name
        assert "logging" in svc, name
        if name == "migrate":
            assert svc["restart"] == "no"
            continue
        assert svc["restart"] == "unless-stopped", name
        assert svc["healthcheck"]["test"], name


def test_secrets_come_only_from_env_file() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    for name, svc in _compose()["services"].items():
        for key, value in _env(svc).items():
            if SECRET_KEYS.search(key):
                assert value.startswith("${") or "${" in value, f"{name}.{key} sabit değer taşıyor"
                if key != "SMTP_PASSWORD":  # SMTP isteğe bağlı: boşsa e-posta kapalı
                    assert REQUIRED_INTERP.search(value), f"{name}.{key} zorunlu değil (:?)"
    # Bağlantı dizgilerindeki parolalar da interpolasyonla gelir.
    urls = [line for line in text.splitlines() if "postgresql+psycopg://" in line]
    assert urls
    for line in urls:
        assert re.search(r"://aegis(_app)?:\$\{[A-Z_]+:\?", line), line


def test_app_connects_as_rls_role_and_only_migrate_is_privileged() -> None:
    services = _compose()["services"]
    for name in ("api", "worker", "beat"):
        env = _env(services[name])
        assert env["DATABASE_URL"].startswith("postgresql+psycopg://aegis_app:"), name
        assert "DATABASE_ADMIN_URL" not in env, name
        assert env["ENVIRONMENT"] == "production"
    migrate = _env(services["migrate"])
    assert migrate["DATABASE_ADMIN_URL"].startswith("postgresql+psycopg://aegis:")


def test_screening_stays_self_hosted() -> None:
    services = _compose()["services"]
    assert _env(services["api"])["YENTE_URL"] == "http://yente:8000"
    assert _env(services["yente"])["YENTE_STATEMENT_API"] == "false"
    assert _env(services["yente"])["YENTE_AUTO_REINDEX"] == "true"


def test_beat_is_separate_from_worker() -> None:
    services = _compose()["services"]
    assert "-B" not in services["worker"]["command"]
    assert "beat" in services["beat"]["command"]


def test_deploy_workflow_is_manual_only() -> None:
    data = yaml.safe_load(DEPLOY.read_text(encoding="utf-8"))
    triggers = data.get("on", data.get(True))  # PyYAML 'on' anahtarını True okur
    assert set(triggers) == {"workflow_dispatch"}
    assert data["jobs"]["images"]["if"] == "inputs.onay == 'DAGIT'"
    assert data["jobs"]["deploy"]["environment"] == "production"


def test_env_example_has_no_values_for_secrets() -> None:
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split("#", 1)[0].strip()
        if SECRET_KEYS.search(key) or key in {"BACKUP_CRYPT_SALT", "MINIO_ROOT_USER"}:
            assert value == "", f"şablonda {key} dolu"
