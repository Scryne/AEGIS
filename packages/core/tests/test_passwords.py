"""Parola özetleme birim testleri (Argon2)."""

from __future__ import annotations

from aegis_core.security.passwords import hash_password, verify_password


def test_hash_and_verify() -> None:
    hashed = hash_password("cok-gizli-parola")
    assert hashed != "cok-gizli-parola"  # düz metin saklanmaz
    assert verify_password("cok-gizli-parola", hashed) is True
    assert verify_password("yanlis-parola", hashed) is False


def test_hashes_are_salted() -> None:
    # Aynı parola iki kez özetlenince farklı çıktı (rastgele tuz).
    assert hash_password("ayni-parola") != hash_password("ayni-parola")
