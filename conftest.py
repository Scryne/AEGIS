"""Kök test yapılandırması: platform shim + paylaşılan entegrasyon fixture'ları.

Entegrasyon testleri (``-m integration``) Docker gerektirir: bir PostgreSQL 16 ve bir
Redis konteyneri testcontainers ile ayağa kaldırılır. Migration'lar **ayrıcalıklı**
``aegis`` rolüyle uygulanır; uygulama RLS'ye tabi ``aegis_app`` rolüyle bağlanır — süper
kullanıcı RLS'yi baypas ederdi (ADR-0002). Bu ayrım, kiracılar-arası izolasyon garantisinin
DB düzeyinde gerçekten çalıştığını doğrulamanın ön koşuludur.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

# Windows'ta psycopg async, ProactorEventLoop ile çalışmaz; selector şart.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

PROJECT_ROOT = Path(__file__).resolve().parent

APP_ROLE = "aegis_app"
APP_PASSWORD = "aegis_app"
TEST_AUTH_SECRET = "test-secret-please-change-in-prod-0123456789"


@pytest.fixture(scope="session")
def app_database_url() -> Iterator[str]:
    """pgvector'suz PostgreSQL 16 + migration + non-superuser app rolü döndürür."""
    postgres_container = pytest.importorskip("testcontainers.postgres").PostgresContainer
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    from aegis_core.config import get_settings

    with postgres_container(
        "postgres:16",
        username="aegis",
        password="aegis",
        dbname="aegis",
        driver="psycopg",
    ) as postgres:
        admin_url = postgres.get_connection_url()
        os.environ["DATABASE_ADMIN_URL"] = admin_url
        os.environ["DATABASE_URL"] = admin_url
        get_settings.cache_clear()

        cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
        command.upgrade(cfg, "head")

        admin_engine = create_engine(admin_url)
        with admin_engine.begin() as conn:
            conn.execute(text(f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}'"))
            conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
            conn.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE "
                    f"ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"
                )
            )
            # Append-only denetim izi: production'da initdb blanket verir, migration
            # 0002 audit_event için UPDATE/DELETE geri alır. Testte rol migration'dan
            # SONRA yaratıldığından revoke'u burada yansıtırız (yoksa blanket grant
            # migration'ın revoke'unu ezerdi). Trigger katmanı rolden bağımsızdır.
            conn.execute(text(f"REVOKE UPDATE, DELETE ON audit_event FROM {APP_ROLE}"))
        admin_engine.dispose()

        host = postgres.get_container_host_ip()
        port = postgres.get_exposed_port(5432)
        app_url = f"postgresql+psycopg://{APP_ROLE}:{APP_PASSWORD}@{host}:{port}/aegis"
        try:
            yield app_url
        finally:
            for key in ("DATABASE_URL", "DATABASE_ADMIN_URL"):
                os.environ.pop(key, None)
            get_settings.cache_clear()


@pytest.fixture
def admin_database_url(app_database_url: str) -> str:
    """Ayrıcalıklı (superuser ``aegis``) bağlantı URL'i — trigger devre dışı bırakma /
    kurcalama simülasyonu gibi DBA-düzeyi senaryoları için (bkz. hash zinciri testi)."""
    return os.environ["DATABASE_ADMIN_URL"]


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    """Testcontainers Redis 7 örneği (oran sınırlama gerçek Redis'e sayar)."""
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs

    container = DockerContainer("redis:7-alpine").with_exposed_ports(6379)
    container.start()
    try:
        wait_for_logs(container, "Ready to accept connections", timeout=30)
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"
    finally:
        container.stop()


@pytest.fixture
def api_client(app_database_url: str, redis_url: str) -> Iterator[object]:
    """Uygulamayı (RLS'ye tabi app rolüyle) bir TestClient olarak sunar."""
    from fastapi.testclient import TestClient

    from aegis_core.config import get_settings

    os.environ["DATABASE_URL"] = app_database_url
    os.environ["REDIS_URL"] = redis_url
    os.environ["AUTH_SECRET"] = TEST_AUTH_SECRET
    get_settings.cache_clear()

    # Oran sınırlama gerçek Redis'e sayar; önceki koşulardan kalan rl:* anahtarları
    # kayıt/giriş uçlarını 429'a düşürebilir — her kurulumda temizlenir (yalnız rl:*).
    import redis as redis_sync

    try:
        client = redis_sync.Redis.from_url(redis_url)
        stale = list(client.scan_iter("rl:*"))
        if stale:
            client.delete(*stale)
        client.close()
    except redis_sync.RedisError:
        pass

    from aegis_api.main import create_app

    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()
