"""Alan-düzeyi şifreleme birim testleri: round-trip, kurcalama, anahtar, TypeDecorator.

Docker gerektirmez. AEAD garantilerini (gizlilik + kimlik doğrulama) ve
``EncryptedString`` tipinin şeffaf davranışını kilitler.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator

import pytest

from aegis_core.config import get_settings
from aegis_core.security.encryption import (
    DecryptionError,
    EncryptedString,
    SecretBox,
    generate_key,
    get_secret_box,
)

TCKN = "12345678901"  # örnek hassas değer (kimlik no formatı)


def _box() -> SecretBox:
    return SecretBox(base64.b64decode(generate_key()))


def test_encrypt_decrypt_roundtrip() -> None:
    box = _box()
    token = box.encrypt(TCKN)
    assert token != TCKN  # şifreli metin düz metinden farklı
    assert box.decrypt(token) == TCKN


def test_nonce_makes_ciphertext_nondeterministic() -> None:
    box = _box()
    # Aynı düz metin iki kez şifrelenince farklı token (rastgele nonce) ama aynı çözüm.
    assert box.encrypt(TCKN) != box.encrypt(TCKN)


def test_wrong_key_fails() -> None:
    token = _box().encrypt(TCKN)
    with pytest.raises(DecryptionError):
        _box().decrypt(token)  # farklı anahtarlı yeni kutu


def test_tampered_ciphertext_fails() -> None:
    box = _box()
    raw = bytearray(base64.b64decode(box.encrypt(TCKN)))
    raw[-1] ^= 0x01  # tag'in son baytını çevir
    with pytest.raises(DecryptionError):
        box.decrypt(base64.b64encode(bytes(raw)).decode())


def test_aad_binds_context() -> None:
    box = _box()
    token = box.encrypt(TCKN, aad=b"tenant-a")
    assert box.decrypt(token, aad=b"tenant-a") == TCKN
    with pytest.raises(DecryptionError):
        box.decrypt(token, aad=b"tenant-b")  # farklı bağlam → doğrulama başarısız


def test_key_must_be_32_bytes() -> None:
    with pytest.raises(ValueError, match="32 bayt"):
        SecretBox(b"kisa-anahtar")


def test_generate_key_is_valid_256_bit() -> None:
    assert len(base64.b64decode(generate_key())) == 32


@pytest.fixture
def field_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Geçerli bir ``FIELD_ENCRYPTION_KEY`` ayarlar ve ayar önbelleğini temizler."""
    key = generate_key()
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", key)
    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()


def test_encrypted_string_type_is_transparent(field_key: str) -> None:
    # process_bind_param (yazım) şifreler, process_result_value (okuma) çözer.
    col = EncryptedString()
    stored = col.process_bind_param(TCKN, dialect=None)
    assert stored is not None
    assert stored != TCKN  # DB'de ciphertext saklanır
    assert col.process_result_value(stored, dialect=None) == TCKN
    # NULL değerler dokunulmadan geçer.
    assert col.process_bind_param(None, dialect=None) is None
    assert col.process_result_value(None, dialect=None) is None


def test_get_secret_box_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # delenv yetmez: ayarlar .env dosyasını da okur ve yerel geliştirme .env'inde anahtar
    # varsa test makineye bağlı düşer. Boş ortam değişkeni .env'i ezer ve "yok" sayılır.
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="FIELD_ENCRYPTION_KEY"):
            get_secret_box()
    finally:
        get_settings.cache_clear()
