"""Alan-düzeyi şifreleme: hassas kolonlar (ör. TCKN/vergi no) için AES-256-GCM.

pgcrypto yerine **uygulama-düzeyi AEAD** tercih edilir (bkz. ADR-0005): pgcrypto simetrik
anahtarı SQL metnine taşır (pg_stat_statements/loglara sızabilir); uygulama-düzeyi
AES-256-GCM anahtarı süreç içinde (secrets'tan) tutar ve kimlik-doğrulamalı şifreleme
(kurcalama tespiti) sağlar. Anahtar asla git'e girmez (``FIELD_ENCRYPTION_KEY``, .env).

Şu an hiçbir kolon şifreli değildir; kimlik-no gibi hassas kolonlar E1.4'te
``EncryptedString`` tipini kullanır. Mekanizma şimdi kilitlenir — canlı PII'ye sonradan
şifreleme eklemek, RLS/audit gibi pahalıdır (Invariant 3/4, KVKK).
"""

from __future__ import annotations

import base64
import os
from functools import lru_cache
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from aegis_core.config import get_settings

KEY_BYTES = 32  # AES-256
NONCE_BYTES = 12  # GCM standart nonce boyu


class DecryptionError(Exception):
    """Şifre çözme başarısız — yanlış anahtar veya kurcalanmış/geçersiz şifreli metin."""


class SecretBox:
    """AES-256-GCM ile kimlik-doğrulamalı simetrik şifreleme.

    Token biçimi: ``base64( nonce(12B) ‖ ciphertext+tag )``. Her şifrelemede rastgele
    nonce üretilir (aynı düz metin farklı token verir). İsteğe bağlı ``aad`` (ör.
    tenant_id baytları) şifreli metni bir bağlama bağlar; çözerken aynısı verilmezse
    doğrulama başarısız olur (bir kaydın ciphertext'ini başka kayda kopyalamayı önler).
    """

    def __init__(self, key: bytes) -> None:
        if len(key) != KEY_BYTES:
            raise ValueError(f"Şifreleme anahtarı {KEY_BYTES} bayt olmalı, {len(key)} verildi.")
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str, *, aad: bytes | None = None) -> str:
        """Düz metni şifreler ve base64 token döndürür."""
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, token: str, *, aad: bytes | None = None) -> str:
        """Token'ı çözer; yanlış anahtar/kurcalama/geçersiz biçimde ``DecryptionError``."""
        try:
            raw = base64.b64decode(token, validate=True)
            nonce, ciphertext = raw[:NONCE_BYTES], raw[NONCE_BYTES:]
            return self._aesgcm.decrypt(nonce, ciphertext, aad).decode("utf-8")
        except (InvalidTag, ValueError) as exc:
            raise DecryptionError(
                "Şifre çözme başarısız (yanlış anahtar veya kurcalanmış veri)."
            ) from exc


def generate_key() -> str:
    """Yeni bir base64 alan-şifreleme anahtarı üretir (``FIELD_ENCRYPTION_KEY`` için)."""
    return base64.b64encode(os.urandom(KEY_BYTES)).decode("ascii")


@lru_cache
def _box_for_key(b64_key: str) -> SecretBox:
    try:
        key = base64.b64decode(b64_key, validate=True)
    except ValueError as exc:
        raise ValueError("FIELD_ENCRYPTION_KEY geçerli base64 değil.") from exc
    return SecretBox(key)


def get_secret_box() -> SecretBox:
    """Ayarlardaki anahtardan (önbellekli) ``SecretBox`` döndürür; anahtar yoksa hata."""
    key = get_settings().field_encryption_key
    if not key:
        raise RuntimeError(
            "FIELD_ENCRYPTION_KEY ayarlı değil — hassas alan şifrelemesi kullanılamaz "
            "(aegis_core.security.encryption.generate_key ile üretin)."
        )
    return _box_for_key(key)


class EncryptedString(TypeDecorator[str]):
    """Hassas string kolonlar için şeffaf uygulama-düzeyi şifreleme (AES-256-GCM).

    DB'de ciphertext (``Text``) saklanır; Python tarafında düz string görünür. Anahtar
    ``get_secret_box`` ile çözülür. NULL değerler şifrelenmez. Not: şifreli değer
    deterministik değildir → üzerinde SQL ile arama/filtreleme yapılamaz; eşitlik araması
    gereken alanlar için ayrıca aramaya-özel bir hash kolonu (E1.4) düşünülür.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return get_secret_box().encrypt(value)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return get_secret_box().decrypt(value)
