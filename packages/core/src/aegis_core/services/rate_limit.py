"""Redis tabanlı sabit-pencere oran sınırlama (login/register brute-force koruması).

Sayaç ``INCR`` + ilk artışta ``EXPIRE`` (atomik pipeline) ile tutulur. Redis'e
ulaşılamazsa sınırlama atlanır (fail-open): kimlik doğrulama, Redis kesintisinde
tamamen durmamalıdır — hata loglanır.
"""

from __future__ import annotations

from redis.asyncio import Redis
from redis.exceptions import RedisError

from aegis_core.logging import get_logger

logger = get_logger("aegis.core.rate_limit")

_KEY_PREFIX = "rl"


class RateLimitExceededError(Exception):
    """İzin verilen deneme sayısı aşıldı."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(f"Oran sınırı aşıldı; {retry_after_seconds} sn sonra yeniden deneyin.")
        self.retry_after_seconds = retry_after_seconds


async def check_rate_limit(
    redis: Redis,
    *,
    scope: str,
    identifier: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Sayaç artırır; pencere içindeki deneme sayısı sınırı aşarsa hata yükseltir.

    ``scope`` mantıksal alan (ör. ``login:ip``), ``identifier`` sınırlanan özne
    (IP adresi, e-posta...). Redis hatası sınırlamayı atlatır (fail-open).
    """
    key = f"{_KEY_PREFIX}:{scope}:{identifier}"
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, window_seconds, nx=True)
            count, _ = await pipe.execute()
        if int(count) > limit:
            ttl = await redis.ttl(key)
            raise RateLimitExceededError(retry_after_seconds=max(int(ttl), 1))
    except RedisError as exc:
        logger.warning("rate_limit_atlandi", scope=scope, error=str(exc))


async def reset_rate_limit(redis: Redis, *, scope: str, identifier: str) -> None:
    """Öznenin sayacını siler (ör. başarılı girişte e-posta penceresi sıfırlanır).

    Böylece meşru kullanıcının ardışık başarılı girişleri limiti tüketmez;
    yalnızca başarısız denemeler pencere boyunca birikir. Redis hatası yutulur.
    """
    key = f"{_KEY_PREFIX}:{scope}:{identifier}"
    try:
        await redis.delete(key)
    except RedisError as exc:
        logger.warning("rate_limit_sifirlanamadi", scope=scope, error=str(exc))
