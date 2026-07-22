"""API genel yanıt şemaları (sözleşme kaynağı — OpenAPI'ya yansır)."""

from __future__ import annotations

from pydantic import BaseModel

from aegis_core.config import Environment


class HealthResponse(BaseModel):
    """Liveness yanıtı."""

    status: str = "ok"


class ReadinessComponent(BaseModel):
    """Tek bir bağımlılığın (DB, Redis) hazırlık durumu."""

    name: str
    healthy: bool
    detail: str | None = None


class ReadinessResponse(BaseModel):
    """Readiness yanıtı — bağımlılık kontrol sonuçları."""

    ready: bool
    components: list[ReadinessComponent]


class VersionResponse(BaseModel):
    """Servis sürüm/ortam bilgisi."""

    name: str
    version: str
    environment: Environment
