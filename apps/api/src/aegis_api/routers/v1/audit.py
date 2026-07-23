"""/api/v1/audit — denetim izi bütünlük doğrulaması (hash zinciri verifier).

Tam denetim görüntüleyici (kim/ne/ne zaman listesi) E1.5'te gelir. Burada yalnız
Invariant 2'nin **verifier**'ı vardır: aktif kiracının zincirinin kurcalanmadığını
doğrular. Oturum ``get_tenant_session`` ile açılır → RLS yalnız çağıranın kiracısının
zincirini görür. Uyumdan sorumlu roller (owner/compliance_officer) ve salt-okunur
denetçi (auditor) erişebilir; analist erişemez.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from aegis_api.dependencies import Principal, TenantSessionDep, require_role
from aegis_core.models import Role
from aegis_core.services import audit as audit_service

router = APIRouter(prefix="/audit", tags=["audit"])

RequireAuditRead = Annotated[
    Principal, Depends(require_role(Role.OWNER, Role.COMPLIANCE_OFFICER, Role.AUDITOR))
]


class ChainVerificationResponse(BaseModel):
    """Hash zinciri doğrulama sonucu."""

    ok: bool
    events_checked: int
    broken_seq: int | None = None
    reason: str | None = None


@router.get("/verify", response_model=ChainVerificationResponse)
async def verify_audit_chain(
    _principal: RequireAuditRead, session: TenantSessionDep
) -> ChainVerificationResponse:
    """Aktif kiracının denetim izi hash zincirini doğrular (kurcalama tespiti)."""
    result = await audit_service.verify_chain(session)
    return ChainVerificationResponse(
        ok=result.ok,
        events_checked=result.events_checked,
        broken_seq=result.broken_seq,
        reason=result.reason,
    )
