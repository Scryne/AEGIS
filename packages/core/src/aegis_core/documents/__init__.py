"""Belge işleme — yükleme, saklama ve Türkçe belgelerden veri çıkarımı (E1.4).

- ``storage``: S3-uyumlu nesne deposu (MinIO) adaptörü.
- ``extraction``: imza sirküleri / faaliyet belgesi / Ticaret Sicil Gazetesi metninden
  öznitelik ve kişi çıkarımı — **saf fonksiyonlar**, PDF motorundan bağımsız.
- ``docling_adapter``: PDF → metin dönüşümü (Docling; isteğe bağlı kurulum).

Çıkarımın sonucu asla doğrudan kütüğe yazılmaz; ``ExtractionProposal`` olarak insan
onayına sunulur (Revizyon R2'nin açık koşulu).
"""

from aegis_core.documents.extraction import (
    ExtractedAttribute,
    ExtractedPerson,
    ExtractionResult,
    extract_from_text,
)

__all__ = [
    "ExtractedAttribute",
    "ExtractedPerson",
    "ExtractionResult",
    "extract_from_text",
]
