"""Uygulama yapılandırması (12-factor): ayarlar ortam değişkenlerinden okunur."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIN_AUTH_SECRET_LENGTH = 32  # HS256 için RFC 7518 §3.2 önerisi


class Environment(StrEnum):
    """Çalışma ortamları."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Merkezî ayarlar. Alanlar env değişkenlerinden (case-insensitive) okunur."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Uygulama ─────────────────────────────────────────────────────────────
    project_name: str = "AEGIS"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    # NoDecode: pydantic-settings'in env değerini JSON olarak çözmesini engeller;
    # ham string aşağıdaki validator'a gider (virgülle ayrılır).
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # ── Veri katmanı ─────────────────────────────────────────────────────────
    # Uygulama (api/worker) bağlantısı: RLS'ye TABİ, süper-kullanıcı OLMAYAN rol.
    database_url: str = "postgresql+psycopg://aegis_app:aegis_app@localhost:5432/aegis"
    # Migration/DDL için ayrıcalıklı bağlantı (owner/superuser). Boşsa database_url kullanılır.
    database_admin_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"

    # ── Nesne depolama (MinIO / S3) — E1.4 ───────────────────────────────────
    object_storage_endpoint_url: str | None = None
    object_storage_bucket: str | None = None
    object_storage_access_key_id: str | None = None
    object_storage_secret_access_key: str | None = None
    object_storage_region: str = "auto"

    # ── Tarama motoru (yente) — E1.3 ─────────────────────────────────────────
    # KVKK: self-host; müşteri PII'si asla dış tarama API'sine gitmez.
    yente_url: str = "http://localhost:8001"

    # ── Gözlemlenebilirlik ────────────────────────────────────────────────────
    sentry_dsn: str | None = None

    # ── Kimlik ────────────────────────────────────────────────────────────────
    auth_secret: str | None = None
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    password_reset_expire_minutes: int = 30

    # ── Oran sınırlama (login/register brute-force) ──────────────────────────
    auth_rate_limit_attempts: int = 5  # e-posta başına pencere içi deneme
    auth_rate_limit_ip_attempts: int = 20  # IP başına (ofis NAT'ı için daha gevşek)
    auth_rate_limit_window_seconds: int = 300
    # Güvenilir ters-proxy sayısı: X-Forwarded-For'un SONDAN kaç girdisinin güvenilir
    # altyapı (Next proxy / LB) tarafından eklendiği. 0 = XFF yok sayılır.
    trusted_proxy_count: int = 0

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv_list(cls, value: object) -> object:
        """Virgülle ayrılmış env değerini (JSON değil, düz string) listeye ayrıştırır."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _enforce_production_hardening(self) -> Self:
        """Production'da güvensiz varsayılanlarla açılışı engeller (fail-fast)."""
        if self.environment is Environment.PRODUCTION:
            if not self.auth_secret or len(self.auth_secret) < MIN_AUTH_SECRET_LENGTH:
                raise ValueError(
                    "Production'da AUTH_SECRET zorunludur ve en az "
                    f"{MIN_AUTH_SECRET_LENGTH} karakter olmalıdır "
                    "(`openssl rand -base64 32` ile üretin)."
                )
            if self.debug:
                raise ValueError("Production'da DEBUG=true olamaz.")
        return self

    @property
    def is_production(self) -> bool:
        """Ortam production mı."""
        return self.environment is Environment.PRODUCTION

    @property
    def migration_database_url(self) -> str:
        """Migration/DDL için ayrıcalıklı bağlantı (yoksa uygulama URL'ine düşer)."""
        return self.database_admin_url or self.database_url


@lru_cache
def get_settings() -> Settings:
    """Önbelleğe alınmış tekil ayarlar örneği döndürür."""
    return Settings()
