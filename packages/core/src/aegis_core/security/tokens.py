"""JWT token'ları (HS256): erişim (access) + yenileme (refresh) + parola sıfırlama.

Her token bir ``typ`` iddiası taşır; ``decode_token`` beklenen türü doğrular; böylece
bir refresh token'ı erişim token'ı yerine (veya tersine) kullanılamaz.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pydantic import BaseModel, ValidationError

ALGORITHM = "HS256"

TYPE_ACCESS = "access"
TYPE_REFRESH = "refresh"
TYPE_RESET = "reset"


class TokenPayload(BaseModel):
    """Erişim/yenileme token'ının çözülmüş içeriği."""

    sub: str  # user id
    tenant_id: str  # aktif organizasyon (tenant) id
    role: str  # RBAC rolü
    typ: str  # token türü (access | refresh)
    exp: int  # sona erme (unix epoch)


class ResetTokenPayload(BaseModel):
    """Parola sıfırlama token'ının çözülmüş içeriği (tenant/rol taşımaz)."""

    sub: str  # user id
    typ: str  # "reset"
    exp: int


def _encode(payload: dict[str, object], secret: str) -> str:
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def create_access_token(
    *, user_id: uuid.UUID, tenant_id: uuid.UUID, role: str, secret: str, expires_in_minutes: int
) -> str:
    """Kısa ömürlü, imzalı bir erişim token'ı üretir."""
    now = datetime.now(UTC)
    return _encode(
        {
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "role": role,
            "typ": TYPE_ACCESS,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=expires_in_minutes)).timestamp()),
        },
        secret,
    )


def create_refresh_token(
    *, user_id: uuid.UUID, tenant_id: uuid.UUID, role: str, secret: str, expires_in_days: int
) -> str:
    """Uzun ömürlü, imzalı bir yenileme token'ı üretir (erişim token'ı tazelemek için)."""
    now = datetime.now(UTC)
    return _encode(
        {
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "role": role,
            "typ": TYPE_REFRESH,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=expires_in_days)).timestamp()),
        },
        secret,
    )


def create_password_reset_token(*, user_id: uuid.UUID, secret: str, expires_in_minutes: int) -> str:
    """Kısa ömürlü, tek amaçlı bir parola sıfırlama token'ı üretir."""
    now = datetime.now(UTC)
    return _encode(
        {
            "sub": str(user_id),
            "typ": TYPE_RESET,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=expires_in_minutes)).timestamp()),
        },
        secret,
    )


def decode_token(token: str, secret: str, *, expected_type: str) -> TokenPayload:
    """Erişim/yenileme token'ını doğrular; tür beklenenle eşleşmezse hata verir.

    İmzası geçerli ama şeması/türü uymayan token'lar ``jwt.InvalidTokenError``'a
    eşlenir; çağıran tek tip ``PyJWTError`` yakalayarak 401 dönebilir.
    """
    data = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["exp"]})
    try:
        payload = TokenPayload.model_validate(data)
    except ValidationError as exc:
        raise jwt.InvalidTokenError("Token içeriği beklenen şemaya uymuyor.") from exc
    if payload.typ != expected_type:
        raise jwt.InvalidTokenError(
            f"Beklenen token türü '{expected_type}', gelen '{payload.typ}'."
        )
    return payload


def decode_reset_token(token: str, secret: str) -> ResetTokenPayload:
    """Parola sıfırlama token'ını doğrular (tür ``reset`` olmalı)."""
    data = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["exp"]})
    try:
        payload = ResetTokenPayload.model_validate(data)
    except ValidationError as exc:
        raise jwt.InvalidTokenError("Token içeriği beklenen şemaya uymuyor.") from exc
    if payload.typ != TYPE_RESET:
        raise jwt.InvalidTokenError("Bu token bir parola sıfırlama token'ı değil.")
    return payload
