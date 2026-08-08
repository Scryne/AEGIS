"""Varlık kütüğü (entity registry) — E1.4.

Katmanlar:

- ``identifiers``: Türk kimlik numaralarının (TCKN, VKN, MERSİS) ve LEI'nin
  normalizasyonu + kontrol basamağı doğrulaması.
- ``resolution``: varlık çözümleme v1 (deterministik anahtar → pg_trgm bulanık ad →
  birleştir-ya-da-oluştur, belirsizlikte insana sor).
- ``service``: varlık/ilişki/öznitelik CRUD ve provenans yazımı.
- ``discrepancy``: beyan edilen ile belgeden/kütükten gelen verinin karşılaştırılması.
- ``gleif``: LEI ile kamuya açık GLEIF kütüğünden zenginleştirme.
"""

from aegis_core.entities.identifiers import (
    IdentifierCheck,
    IdentifierKind,
    check_identifier,
    normalize_digits,
    normalize_lei,
)

__all__ = [
    "IdentifierCheck",
    "IdentifierKind",
    "check_identifier",
    "normalize_digits",
    "normalize_lei",
]
