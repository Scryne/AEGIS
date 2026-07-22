"""Parola özetleme (Argon2, pwdlib)."""

from __future__ import annotations

from pwdlib import PasswordHash

_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Düz parolayı güvenli biçimde özetler."""
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Düz parolayı özet ile karşılaştırır."""
    return _hasher.verify(password, hashed)
