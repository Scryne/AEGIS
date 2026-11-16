"""Kullanıcı oturumlarını geçersiz kılma (ekipten çıkarma).

Erişim jetonları imzayla doğrulanır ve süreleri dolana kadar geçerlidir; üyelik silinse de
elindeki jeton çalışmaya devam ederdi. Çıkarma anında Redis'e "bu kullanıcının bu andan önce
verilmiş jetonları geçersiz" damgası yazılır; ``get_principal`` ve ``/auth/refresh`` jetonun
``iat``'ını bu damgayla karşılaştırır. Damga yenileme jetonunun ömrü kadar yaşar: o süreden
sonra eski jetonların hepsi zaten dolmuştur. Yeniden davet edilen kişi yeni jeton alır
(``iat`` damgadan sonra) ve etkilenmez.
"""

from __future__ import annotations

import time
import uuid

from redis.asyncio import Redis

_KEY = "aegis:oturum-iptal:{user_id}"


async def revoke_user_sessions(redis: Redis, user_id: uuid.UUID, *, ttl_seconds: int) -> int:
    """Kullanıcının şimdiye kadar verilmiş tüm jetonlarını geçersiz kılar; damgayı döndürür."""
    stamp = int(time.time())
    await redis.set(_KEY.format(user_id=user_id), stamp, ex=max(1, ttl_seconds))
    return stamp


async def is_token_revoked(redis: Redis, user_id: uuid.UUID, issued_at: int | None) -> bool:
    """Jeton iptal damgasından önce (ya da aynı saniyede) verildiyse True."""
    raw = await redis.get(_KEY.format(user_id=user_id))
    if raw is None:
        return False
    # iat taşımayan (eski biçim) jeton damga varken güvenilmez.
    return issued_at is None or issued_at <= int(raw)
