"""Tutarlı hata modeli: makine-okur kod + kullanıcı-okur mesaj.

Tüm hatalar tek bir JSON gövdesiyle döner::

    {"error": {"code": "not_found", "message": "...", "details": [...]}}
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from aegis_core.logging import get_logger

logger = get_logger("aegis.api.errors")


class ErrorCode(StrEnum):
    """Makine-okur hata kodları."""

    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    INTERNAL_ERROR = "internal_error"


class ErrorDetail(BaseModel):
    """Hata gövdesinin çekirdeği."""

    code: ErrorCode
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    """Tüm hata yanıtlarının zarf şeması."""

    error: ErrorDetail


class AppError(Exception):
    """Uygulama hatalarının temeli. Alt sınıflar kod/HTTP durumunu belirler."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        status_code: int | None = None,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details
        self.headers = headers


class NotFoundError(AppError):
    """Kaynak bulunamadı (404)."""

    status_code = status.HTTP_404_NOT_FOUND
    code = ErrorCode.NOT_FOUND


class UnauthorizedError(AppError):
    """Kimlik doğrulanmadı (401)."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = ErrorCode.UNAUTHORIZED


class ForbiddenError(AppError):
    """Yetki yok (403)."""

    status_code = status.HTTP_403_FORBIDDEN
    code = ErrorCode.FORBIDDEN


class ConflictError(AppError):
    """Çakışma (409)."""

    status_code = status.HTTP_409_CONFLICT
    code = ErrorCode.CONFLICT


class ValidationFailedError(AppError):
    """İçerik doğrulaması başarısız (400) — istek şeması değil, iş kuralı ihlali."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = ErrorCode.VALIDATION_ERROR


class RateLimitedError(AppError):
    """Oran sınırı aşıldı (429)."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = ErrorCode.RATE_LIMITED


_HTTP_STATUS_TO_CODE: dict[int, ErrorCode] = {
    status.HTTP_400_BAD_REQUEST: ErrorCode.VALIDATION_ERROR,
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
}


def _error_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(error=ErrorDetail(code=code, message=message, details=details))
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload), headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    """Uygulamaya tutarlı hata yakalayıcılarını kaydeder."""

    @app.exception_handler(AppError)
    async def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCode.VALIDATION_ERROR,
            "İstek doğrulaması başarısız.",
            jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _HTTP_STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        message = exc.detail if isinstance(exc.detail, str) else "HTTP hatası."
        return _error_response(exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("beklenmeyen_hata", error=str(exc), exc_info=exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            ErrorCode.INTERNAL_ERROR,
            "Beklenmeyen bir hata oluştu.",
        )
