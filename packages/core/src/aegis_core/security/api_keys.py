"""API anahtarı biçimi ve özeti (E3.4, ADR-0016) — saf çekirdek.

Biçim: ``aeg_<önek 12>_<gizli 40>``. Önek veritabanında düz durur (arama ve listede gösterim
için), gizli kısım hiçbir yerde saklanmaz: yalnız tam anahtarın SHA-256 özeti tutulur. Anahtar
yüksek entropili rastgele bir değer olduğundan (≥ 240 bit) yavaş parola özeti gerekmez; özet
karşılaştırması sabit zamanlıdır. Tam anahtar kullanıcıya yalnız oluşturulduğu an gösterilir.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string

PREFIX = "aeg"
_ALPHABET = string.ascii_lowercase + string.digits


def _token(n: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def generate() -> tuple[str, str, str]:
    """(tam anahtar, önek, özet) döndürür."""
    prefix = _token(12)
    key = f"{PREFIX}_{prefix}_{_token(40)}"
    return key, prefix, digest(key)


def digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def parse_prefix(key: str) -> str | None:
    parts = key.strip().split("_")
    if len(parts) != 3 or parts[0] != PREFIX or len(parts[1]) != 12 or len(parts[2]) != 40:
        return None
    if not all(c in _ALPHABET for c in parts[1] + parts[2]):
        return None
    return parts[1]


def matches(key: str, stored_digest: str) -> bool:
    return hmac.compare_digest(digest(key.strip()), stored_digest)
