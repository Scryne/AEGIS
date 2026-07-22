"""/api/v1/settings — kiracı-özel yapılandırma (ilk RLS'li *veri* ucu).

Okuma tüm rollere açıktır; yazma yalnız Owner + Compliance Officer'a. Oturum
``get_tenant_session`` ile açılır → RLS kiracıyı DB düzeyinde zorlar. Bu uç,
kiracılar-arası izolasyon testinin (API + doğrudan SQL) ana hedefidir.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from aegis_api.dependencies import Principal, PrincipalDep, TenantSessionDep, require_role
from aegis_api.errors import NotFoundError
from aegis_core.models import Role
from aegis_core.services import tenant_settings as settings_service

router = APIRouter(prefix="/settings", tags=["settings"])

# Yazma yetkisi: Owner + Compliance Officer (Analyst/Auditor salt-okunur).
RequireSettingsWrite = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER))
]


class SettingResponse(BaseModel):
    """Tek bir kiracı ayarı."""

    key: str
    value: dict[str, Any]


class SettingUpsertRequest(BaseModel):
    """Ayar oluşturma/güncelleme gövdesi."""

    value: dict[str, Any]


@router.get("", response_model=list[SettingResponse])
async def list_settings(
    _principal: PrincipalDep, session: TenantSessionDep
) -> list[SettingResponse]:
    """Aktif kiracının tüm ayarlarını döndürür (RLS ile sınırlı)."""
    rows = await settings_service.list_settings(session)
    return [SettingResponse(key=row.key, value=row.value) for row in rows]


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str, _principal: PrincipalDep, session: TenantSessionDep
) -> SettingResponse:
    """Anahtara göre tek ayar döndürür."""
    row = await settings_service.get_setting(session, key)
    if row is None:
        raise NotFoundError("Ayar bulunamadı.")
    return SettingResponse(key=row.key, value=row.value)


@router.put("/{key}", response_model=SettingResponse)
async def upsert_setting(
    key: str,
    body: SettingUpsertRequest,
    principal: RequireSettingsWrite,
    session: TenantSessionDep,
) -> SettingResponse:
    """Ayarı oluşturur veya günceller (Owner + Compliance Officer)."""
    row = await settings_service.upsert_setting(
        session, tenant_id=principal.tenant_id, key=key, value=body.value
    )
    return SettingResponse(key=row.key, value=row.value)
