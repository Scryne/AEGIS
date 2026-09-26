"""Ayar doğrulaması — alan şifreleme anahtarı biçimi (fail-fast)."""

from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError

from aegis_core.config import Settings
from aegis_core.security.encryption import generate_key


def test_gecerli_anahtar_gelistirmede_kabul_edilir() -> None:
    ayar = Settings(environment="development", field_encryption_key=generate_key())
    assert ayar.field_encryption_key


def test_anahtarsiz_gelistirme_acilir() -> None:
    assert (
        Settings(environment="development", field_encryption_key=None).field_encryption_key is None
    )


@pytest.mark.parametrize(
    "anahtar",
    [
        base64.urlsafe_b64encode(bytes([251, 255] * 16)).decode(),  # URL-güvenli alfabe (- _)
        base64.b64encode(b"x" * 16).decode(),  # 16 bayt: AES-256 değil
        "duz-metin-anahtar",
    ],
)
def test_bicimi_yanlis_anahtar_her_ortamda_reddedilir(anahtar: str) -> None:
    with pytest.raises(ValidationError, match="FIELD_ENCRYPTION_KEY"):
        Settings(environment="development", field_encryption_key=anahtar)
