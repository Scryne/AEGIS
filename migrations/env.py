"""Alembic migration ortamı (senkron SQLAlchemy + ayarlardan URL).

Migration'lar senkron çalışır (uygulama runtime'ı async'tir). Bu; platformlar arası
tutarlılık sağlar (özellikle Windows'ta psycopg async + ProactorEventLoop sorunu) ve
tek psycopg3 sürücüsüyle yürür. Migration'lar **ayrıcalıklı** rolle (DATABASE_ADMIN_URL)
çalışır; RLS'ye tabi uygulama rolü DDL yapamaz (bkz. ADR-0002).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from aegis_core import models  # noqa: F401  (modelleri Base.metadata'ya kaydeder)
from aegis_core.config import get_settings
from aegis_core.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return get_settings().migration_database_url


def run_migrations_offline() -> None:
    """Bağlantısız (URL) modda migration SQL'i üretir."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Canlı bağlantı üzerinden (senkron engine) migration çalıştırır."""
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
