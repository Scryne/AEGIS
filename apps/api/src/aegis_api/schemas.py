"""API genel yanıt şemaları (sözleşme kaynağı — OpenAPI'ya yansır)."""

from __future__ import annotations

from pydantic import BaseModel

from aegis_core.config import Environment


class HealthResponse(BaseModel):
    """Liveness yanıtı."""

    status: str = "ok"


class ReadinessComponent(BaseModel):
    """Tek bir bağımlılığın (DB, Redis, yente) hazırlık durumu."""

    name: str
    healthy: bool
    detail: str | None = None
    required: bool = True
    """Hazırlığı BLOKE eder mi.

    DB ve Redis zorunludur. Tarama motoru (yente) değildir: yente düştüğünde giriş,
    dosya görüntüleme ve denetim izi çalışmaya devam etmelidir — servisi tamamen
    hazır-değil ilan etmek, çalışan işlevleri de kapatırdı. Tarama uçları o sırada
    zaten ``failed`` durumunda kayıt üretip 502 döner.
    """


class ReadinessResponse(BaseModel):
    """Readiness yanıtı — bağımlılık kontrol sonuçları."""

    ready: bool
    components: list[ReadinessComponent]


class VersionResponse(BaseModel):
    """Servis sürüm/ortam bilgisi."""

    name: str
    version: str
    environment: Environment
