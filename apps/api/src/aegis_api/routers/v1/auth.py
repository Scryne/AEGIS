"""/api/v1/auth — kayıt, giriş, token yenileme, parola sıfırlama (oran sınırlamalı)."""

from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, Request, status
from pydantic import BaseModel, EmailStr, Field
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError

from aegis_api.dependencies import PrincipalDep, RedisDep, SessionDep, SettingsDep
from aegis_api.errors import (
    ConflictError,
    RateLimitedError,
    UnauthorizedError,
    ValidationFailedError,
)
from aegis_core.config import Settings
from aegis_core.logging import get_logger
from aegis_core.models import Role, User
from aegis_core.security.tokens import (
    TYPE_REFRESH,
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_reset_token,
    decode_token,
)
from aegis_core.services import auth as auth_service
from aegis_core.services.rate_limit import (
    RateLimitExceededError,
    check_rate_limit,
    reset_rate_limit,
)

logger = get_logger("aegis.api.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request, trusted_proxy_count: int) -> str:
    """Gerçek istemci IP'si: güvenilir proxy arkasında X-Forwarded-For'dan çözülür."""
    if trusted_proxy_count > 0:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            hops = [part.strip() for part in forwarded.split(",") if part.strip()]
            if hops:
                return hops[max(len(hops) - trusted_proxy_count, 0)]
    return request.client.host if request.client else "unknown"


def _rate_limit_email(email: str) -> str:
    return email.strip().lower()


async def _enforce_auth_rate_limit(
    request: Request, redis: Redis, settings: Settings, *, scope: str, email: str
) -> None:
    """IP + e-posta bazlı deneme sınırı (brute-force / kayıt istismarı koruması)."""
    client_ip = _client_ip(request, settings.trusted_proxy_count)
    try:
        await check_rate_limit(
            redis,
            scope=f"{scope}:ip",
            identifier=client_ip,
            limit=settings.auth_rate_limit_ip_attempts,
            window_seconds=settings.auth_rate_limit_window_seconds,
        )
        await check_rate_limit(
            redis,
            scope=f"{scope}:email",
            identifier=_rate_limit_email(email),
            limit=settings.auth_rate_limit_attempts,
            window_seconds=settings.auth_rate_limit_window_seconds,
        )
    except RateLimitExceededError as exc:
        raise RateLimitedError(
            "Çok fazla deneme yapıldı; lütfen daha sonra yeniden deneyin.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


class RegisterRequest(BaseModel):
    """Yeni organizasyon + owner kullanıcı kaydı."""

    org_name: str = Field(min_length=1, max_length=255)
    org_slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    """E-posta/parola ile giriş."""

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Yenileme token'ıyla yeni erişim token'ı talebi."""

    refresh_token: str


class TokenResponse(BaseModel):
    """JWT erişim + yenileme token'ı."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105  (token türü, parola değil)


class AccessTokenResponse(BaseModel):
    """Yalnız yeni erişim token'ı (refresh yanıtı)."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105


class UserResponse(BaseModel):
    """Kullanıcı + aktif kiracı + rol."""

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    tenant_id: uuid.UUID
    role: Role


class PasswordResetRequest(BaseModel):
    """Parola sıfırlama talebi (e-posta)."""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Parola sıfırlama onayı (token + yeni parola)."""

    token: str
    new_password: str = Field(min_length=8, max_length=128)


class PasswordResetResponse(BaseModel):
    """Parola sıfırlama talebi yanıtı.

    E-posta teslimi Phase 1'de (E1.6 onboarding) bağlanır; production'da yanıt
    her zaman aynıdır (kullanıcı numaralandırmasını önler). development ortamında
    ``reset_token`` doğrudan döner — teslimat altyapısı olmadan test/geliştirme için.
    """

    ok: bool = True
    reset_token: str | None = None


def _issue_tokens(
    user: User, tenant_id: uuid.UUID, role: Role, settings: Settings
) -> TokenResponse:
    assert settings.auth_secret is not None  # noqa: S101  (çağırandan önce doğrulanır)
    access = create_access_token(
        user_id=user.id,
        tenant_id=tenant_id,
        role=role.value,
        secret=settings.auth_secret,
        expires_in_minutes=settings.access_token_expire_minutes,
    )
    refresh = create_refresh_token(
        user_id=user.id,
        tenant_id=tenant_id,
        role=role.value,
        secret=settings.auth_secret,
        expires_in_days=settings.refresh_token_expire_days,
    )
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> UserResponse:
    """Yeni bir organizasyon ve owner kullanıcı oluşturur."""
    await _enforce_auth_rate_limit(request, redis, settings, scope="register", email=body.email)
    try:
        async with session.begin():
            user, membership = await auth_service.register(
                session,
                org_name=body.org_name,
                org_slug=body.org_slug,
                email=body.email,
                password=body.password,
                full_name=body.full_name,
            )
    except auth_service.EmailAlreadyExistsError as exc:
        raise ConflictError("Bu e-posta ile bir kullanıcı zaten var.") from exc
    except auth_service.SlugAlreadyExistsError as exc:
        raise ConflictError("Bu slug ile bir organizasyon zaten var.") from exc
    except IntegrityError as exc:
        # Ön-kontrol ile INSERT arasındaki yarışta unique kısıt DB'de yakalar.
        raise ConflictError("Bu e-posta veya organizasyon slug'ı zaten kayıtlı.") from exc
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        tenant_id=membership.organization_id,
        role=membership.role,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Kimlik doğrular ve erişim + yenileme token'ı döndürür."""
    if settings.auth_secret is None:
        raise UnauthorizedError("Sunucu kimlik doğrulaması yapılandırılmamış (AUTH_SECRET).")
    await _enforce_auth_rate_limit(request, redis, settings, scope="login", email=body.email)
    result = await auth_service.authenticate(session, email=body.email, password=body.password)
    if result is None:
        raise UnauthorizedError("E-posta veya parola hatalı.")
    user, membership = result
    await reset_rate_limit(redis, scope="login:email", identifier=_rate_limit_email(body.email))
    return _issue_tokens(user, membership.organization_id, membership.role, settings)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    body: RefreshRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> AccessTokenResponse:
    """Geçerli bir yenileme token'ından yeni bir erişim token'ı üretir.

    Rolü token'dan değil güncel üyelikten okur; böylece rol değişikliği yenilemede
    yansır (bir kullanıcının rolü düşürüldüyse eski refresh yükseltilmiş erişim vermez).
    """
    if settings.auth_secret is None:
        raise UnauthorizedError("Sunucu kimlik doğrulaması yapılandırılmamış (AUTH_SECRET).")
    try:
        payload = decode_token(body.refresh_token, settings.auth_secret, expected_type=TYPE_REFRESH)
        user_id = uuid.UUID(payload.sub)
    except (jwt.PyJWTError, ValueError) as exc:
        raise UnauthorizedError("Geçersiz veya süresi dolmuş yenileme token'ı.") from exc

    user: User | None = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Kullanıcı bulunamadı veya pasif.")
    membership = await auth_service.get_membership(session, user_id)
    if membership is None:
        raise UnauthorizedError("Üyelik bulunamadı.")
    access = create_access_token(
        user_id=user.id,
        tenant_id=membership.organization_id,
        role=membership.role.value,
        secret=settings.auth_secret,
        expires_in_minutes=settings.access_token_expire_minutes,
    )
    return AccessTokenResponse(access_token=access)


@router.get("/me", response_model=UserResponse)
async def me(principal: PrincipalDep, session: SessionDep) -> UserResponse:
    """Geçerli token'a karşılık gelen kullanıcıyı döndürür."""
    user: User | None = await session.get(User, principal.user_id)
    if user is None:
        raise UnauthorizedError("Kullanıcı bulunamadı.")
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        tenant_id=principal.tenant_id,
        role=principal.role,
    )


@router.post(
    "/password-reset/request",
    response_model=PasswordResetResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def password_reset_request(
    body: PasswordResetRequest,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> PasswordResetResponse:
    """Parola sıfırlama token'ı üretir (e-posta teslimi E1.6'da bağlanır).

    Kullanıcı yoksa da 202 döner (numaralandırmayı önler). development ortamında
    token yanıtta gelir; production'da yalnızca loglanır/e-postalanır.
    """
    await _enforce_auth_rate_limit(
        request, redis, settings, scope="password-reset", email=body.email
    )
    if settings.auth_secret is None:
        raise UnauthorizedError("Sunucu kimlik doğrulaması yapılandırılmamış (AUTH_SECRET).")
    user = await auth_service.get_user_by_email(session, body.email)
    if user is None:
        return PasswordResetResponse()
    token = create_password_reset_token(
        user_id=user.id,
        secret=settings.auth_secret,
        expires_in_minutes=settings.password_reset_expire_minutes,
    )
    logger.info("parola_sifirlama_talebi", user_id=str(user.id))
    return PasswordResetResponse(reset_token=None if settings.is_production else token)


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def password_reset_confirm(
    body: PasswordResetConfirm,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    """Sıfırlama token'ını doğrular ve yeni parolayı yazar."""
    if settings.auth_secret is None:
        raise UnauthorizedError("Sunucu kimlik doğrulaması yapılandırılmamış (AUTH_SECRET).")
    try:
        payload = decode_reset_token(body.token, settings.auth_secret)
        user_id = uuid.UUID(payload.sub)
    except (jwt.PyJWTError, ValueError) as exc:
        raise ValidationFailedError("Geçersiz veya süresi dolmuş sıfırlama token'ı.") from exc
    async with session.begin():
        updated = await auth_service.set_password(
            session, user_id=user_id, new_password=body.new_password
        )
    if not updated:
        raise ValidationFailedError("Geçersiz sıfırlama token'ı.")
