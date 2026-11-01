"""API anahtarı servisi (E3.4, ADR-0016): oluşturma, listeleme, iptal, doğrulama.

Anahtar bir role bağlıdır ve o rolün yetkisiyle çalışır: ``analyst`` (tarama çalıştırır, okur) ya
da ``auditor`` (yalnız okur). Karar veren roller (sahip, uyum uzmanı) anahtara verilmez: eşleşme
onayı, vaka kararı ve anahtar/webhook yönetimi insan oturumu ister. ``api_key`` RLS'siz kimlik
denetim tablosudur; her sorgu burada ``tenant_id`` ile açıkça süzülür.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.models import ApiKey, AuditAction, Role
from aegis_core.security import api_keys as keyfmt
from aegis_core.services import audit as audit_service

KEY_ROLES = (Role.ANALYST.value, Role.AUDITOR.value)
MAX_ACTIVE_KEYS = 20
TOUCH_EVERY = timedelta(minutes=1)


class ApiKeyError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def create_key(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str,
    role: str,
    expires_in_days: int | None,
    actor_user_id: uuid.UUID,
    actor_role: str,
) -> tuple[ApiKey, str]:
    """Anahtarı oluşturur; tam anahtar yalnız burada döner ve bir daha gösterilmez."""
    if role not in KEY_ROLES:
        raise ApiKeyError("invalid", "API anahtarı yalnız analist ya da denetçi yetkisiyle açılır.")
    active = await list_keys(session, tenant_id=tenant_id, include_revoked=False)
    if len(active) >= MAX_ACTIVE_KEYS:
        raise ApiKeyError("invalid", f"En çok {MAX_ACTIVE_KEYS} etkin anahtar olabilir.")
    full, prefix, digest = keyfmt.generate()
    key = ApiKey(
        tenant_id=tenant_id,
        name=name.strip()[:100],
        prefix=prefix,
        key_digest=digest,
        role=role,
        created_by_user_id=actor_user_id,
        expires_at=(datetime.now(UTC) + timedelta(days=expires_in_days))
        if expires_in_days
        else None,
    )
    session.add(key)
    await session.flush()
    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.API_KEY_CREATE,
        object_type="api_key",
        object_id=str(key.id),
        payload={
            "name": key.name,
            "prefix": prefix,
            "role": role,
            "expires_at": _iso(key.expires_at),
        },
    )
    return key, full


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def list_keys(
    session: AsyncSession, *, tenant_id: uuid.UUID, include_revoked: bool = True
) -> list[ApiKey]:
    query = select(ApiKey).where(ApiKey.tenant_id == tenant_id).order_by(ApiKey.created_at.desc())
    if not include_revoked:
        query = query.where(ApiKey.revoked_at.is_(None))
    return list(await session.scalars(query))


async def revoke_key(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    key_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    actor_role: str,
) -> ApiKey:
    key = await session.scalar(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id)
    )
    if key is None:
        raise ApiKeyError("not_found", "Anahtar bulunamadı.")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        key.revoked_by_user_id = actor_user_id
        await session.flush()
        await audit_service.record_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action=AuditAction.API_KEY_REVOKE,
            object_type="api_key",
            object_id=str(key.id),
            payload={"prefix": key.prefix},
        )
    return key


async def authenticate(
    session: AsyncSession, raw: str, *, now: datetime | None = None
) -> ApiKey | None:
    """Anahtarı doğrular (kiracı bağlamı olmayan oturumda). Geçersizse ``None``."""
    prefix = keyfmt.parse_prefix(raw)
    if prefix is None:
        return None
    key = await session.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    at = now or datetime.now(UTC)
    if key is None or not keyfmt.matches(raw, key.key_digest):
        return None
    if key.revoked_at is not None or (key.expires_at is not None and key.expires_at <= at):
        return None
    if key.last_used_at is None or at - key.last_used_at > TOUCH_EVERY:
        key.last_used_at = at
        await session.flush()
    return key
