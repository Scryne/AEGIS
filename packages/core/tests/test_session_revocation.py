"""Oturum iptal damgası birim testleri (ekipten çıkarma).

Redis yerine sözlük tabanlı küçük bir sahte kullanılır: yalnız ``set(ex=)`` ve ``get``
davranışı ölçülür. Gerçek Redis ile uçtan uca davranış ``apps/api`` entegrasyon testlerinde.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import pytest

from aegis_core.services import session_revocation
from aegis_core.services.session_revocation import is_token_revoked, revoke_user_sessions


class _SahteRedis:
    def __init__(self) -> None:
        self.veri: dict[str, str] = {}
        self.sure: dict[str, int] = {}

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        self.veri[key] = str(value)
        if ex is not None:
            self.sure[key] = ex

    async def get(self, key: str) -> str | None:
        return self.veri.get(key)


async def test_damga_yokken_jeton_gecerli() -> None:
    redis = _SahteRedis()
    assert await is_token_revoked(redis, uuid.uuid4(), int(time.time())) is False  # type: ignore[arg-type]
    assert await is_token_revoked(redis, uuid.uuid4(), None) is False  # type: ignore[arg-type]


async def test_iptal_onceki_ve_ayni_saniyedeki_jetonu_dusurur(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _SahteRedis()
    uid = uuid.uuid4()
    monkeypatch.setattr(session_revocation.time, "time", lambda: 1_000_000.4)
    damga = await revoke_user_sessions(redis, uid, ttl_seconds=3600)  # type: ignore[arg-type]
    assert damga == 1_000_000
    assert await is_token_revoked(redis, uid, 999_999) is True  # type: ignore[arg-type]
    assert await is_token_revoked(redis, uid, 1_000_000) is True  # type: ignore[arg-type]
    assert await is_token_revoked(redis, uid, 1_000_001) is False  # type: ignore[arg-type]


async def test_iat_tasimayan_jeton_damga_varken_reddedilir() -> None:
    redis = _SahteRedis()
    uid = uuid.uuid4()
    await revoke_user_sessions(redis, uid, ttl_seconds=60)  # type: ignore[arg-type]
    assert await is_token_revoked(redis, uid, None) is True  # type: ignore[arg-type]


async def test_damga_yalniz_o_kullaniciyi_etkiler_ve_sureli_yazilir() -> None:
    redis = _SahteRedis()
    cikan, kalan = uuid.uuid4(), uuid.uuid4()
    await revoke_user_sessions(redis, cikan, ttl_seconds=7 * 24 * 3600)  # type: ignore[arg-type]
    assert await is_token_revoked(redis, kalan, 0) is False  # type: ignore[arg-type]
    (anahtar,) = redis.sure
    assert str(cikan) in anahtar
    assert redis.sure[anahtar] == 7 * 24 * 3600


async def test_sifir_ya_da_negatif_sure_en_az_bir_saniye_olur() -> None:
    redis = _SahteRedis()
    await revoke_user_sessions(redis, uuid.uuid4(), ttl_seconds=0)  # type: ignore[arg-type]
    assert list(redis.sure.values()) == [1]
