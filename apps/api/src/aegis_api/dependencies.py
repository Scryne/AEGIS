"""FastAPI bağımlılıkları: DB oturumu, kimlik (principal) ve RBAC."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aegis_api.errors import ForbiddenError, RateLimitedError, UnauthorizedError
from aegis_core.adverse_media.source import NewsProvider
from aegis_core.config import Settings, get_settings
from aegis_core.db.tenant import set_tenant_context
from aegis_core.integrations import api_keys as api_key_service
from aegis_core.models import Role
from aegis_core.observability import bind_sentry_tags
from aegis_core.screening.yente import YenteClient
from aegis_core.security.api_keys import PREFIX as API_KEY_PREFIX
from aegis_core.security.tokens import TYPE_ACCESS, decode_token
from aegis_core.services.rate_limit import RateLimitExceededError, check_rate_limit


def _session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return factory


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Kiracı bağlamı OLMAYAN oturum (kayıt/giriş gibi kimlik işlemleri için)."""
    async with _session_factory(request)() as session:
        yield session


@dataclass(frozen=True)
class Principal:
    """Kimliği doğrulanmış istek sahibi."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: Role
    api_key_id: uuid.UUID | None = None
    """API anahtarıyla gelen istekte anahtarın kimliği (``user_id`` da odur, E3.4)."""


def _bearer_token(authorization: str | None) -> str:
    prefix = "bearer "
    if authorization is None or not authorization.lower().startswith(prefix):
        raise UnauthorizedError("Yetkilendirme başlığı eksik veya hatalı.")
    return authorization[len(prefix) :]


async def _api_key_principal(request: Request, settings: Settings, raw: str) -> Principal:
    """API anahtarı (E3.4): önekle bulunur, özetle doğrulanır, anahtar başına oran sınırı."""
    async with _session_factory(request)() as session, session.begin():
        key = await api_key_service.authenticate(session, raw)
        if key is None:
            raise UnauthorizedError("Geçersiz, iptal edilmiş ya da süresi dolmuş API anahtarı.")
        principal = Principal(
            user_id=key.id, tenant_id=key.tenant_id, role=Role(key.role), api_key_id=key.id
        )
    try:
        await check_rate_limit(
            request.app.state.redis,
            scope="apikey",
            identifier=str(principal.api_key_id),
            limit=settings.api_key_rate_limit_per_minute,
            window_seconds=60,
        )
    except RateLimitExceededError as exc:
        raise RateLimitedError(
            "API anahtarının dakikalık istek sınırı doldu.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    bind_sentry_tags(tenant_id=principal.tenant_id, user_id=principal.user_id)
    return principal


async def get_principal(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> Principal:
    """Bearer erişim JWT'sini ya da API anahtarını (``X-API-Key`` / ``Bearer aeg_…``) doğrular."""
    if x_api_key:
        return await _api_key_principal(request, settings, x_api_key)
    if authorization and authorization.lower().startswith(f"bearer {API_KEY_PREFIX}_"):
        return await _api_key_principal(request, settings, authorization[len("bearer ") :])
    if settings.auth_secret is None:
        raise UnauthorizedError("Sunucu kimlik doğrulaması yapılandırılmamış (AUTH_SECRET).")
    token = _bearer_token(authorization)
    try:
        payload = decode_token(token, settings.auth_secret, expected_type=TYPE_ACCESS)
        principal = Principal(
            user_id=uuid.UUID(payload.sub),
            tenant_id=uuid.UUID(payload.tenant_id),
            role=Role(payload.role),
        )
    except (jwt.PyJWTError, ValueError) as exc:
        # ValueError: imzası geçerli ama claim'i çözümsüz token (ör. UUID olmayan
        # sub veya artık tanımlı olmayan rol) 500 değil 401 üretmeli.
        raise UnauthorizedError("Geçersiz veya süresi dolmuş token.") from exc
    # Hata raporları kiracı/kullanıcı korelasyonu taşır (yalnız ID — PII değil).
    bind_sentry_tags(tenant_id=principal.tenant_id, user_id=principal.user_id)
    return principal


async def get_tenant_session(
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> AsyncIterator[AsyncSession]:
    """RLS kiracı bağlamı ayarlanmış oturum (kiracı-özel veriler için)."""
    async with _session_factory(request)() as session, session.begin():
        await set_tenant_context(session, principal.tenant_id)
        yield session


def require_role(*roles: Role) -> Callable[..., Coroutine[Any, Any, Principal]]:
    """Belirtilen rollerden birini gerektiren bir bağımlılık üretir."""

    async def _checker(
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> Principal:
        if principal.role not in roles:
            raise ForbiddenError("Bu işlem için yetkiniz yok.")
        return principal

    return _checker


def get_redis(request: Request) -> Redis:
    """Uygulamanın paylaşılan async Redis istemcisini döndürür (oran sınırlama)."""
    redis: Redis = request.app.state.redis
    return redis


def get_yente_client(request: Request) -> YenteClient:
    """Uygulamanın paylaşılan yente istemcisini döndürür (E1.3).

    İstemci yaşam döngüsü boyunca tektir: httpx bağlantı havuzu korunur, böylece her
    tarama için TCP/TLS el sıkışması tekrarlanmaz (senkron yol NFR'si < 30 sn).
    """
    client: YenteClient = request.app.state.yente_client
    return client


def get_news_provider(request: Request) -> NewsProvider:
    """Olumsuz haber betasının haber kaynağı (E2.5); uygulama ömrü boyunca tek istemci."""
    provider: NewsProvider = request.app.state.news_provider
    return provider


# Sık kullanılan tip takma adları (router imzalarını sadeleştirir).
SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantSessionDep = Annotated[AsyncSession, Depends(get_tenant_session)]
PrincipalDep = Annotated[Principal, Depends(get_principal)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
RedisDep = Annotated[Redis, Depends(get_redis)]
YenteClientDep = Annotated[YenteClient, Depends(get_yente_client)]
NewsProviderDep = Annotated[NewsProvider, Depends(get_news_provider)]
