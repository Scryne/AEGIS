"""Tarama (screening) alt sistemi — E1.3.

Katmanlar:

- ``normalization``: Türkçe ad kanonikleştirme (İ/ı-doğru küçültme, harf çevirisi,
  tüzel-kişilik eki temizleme). Sorgu ve veri kümesi AYNI fonksiyondan geçer.
- ``yente``: self-host yente istemcisi (KVKK: PII dış servise çıkmaz).
- ``thresholds``: kiracı-başına eşik bandı (otomatik temizle / incele / otomatik işaretle).
- ``service``: tarama akışının orkestrasyonu (normalize → eşleştir → kalıcılaştır).
"""

from aegis_core.screening.normalization import (
    NormalizedName,
    normalize_name,
    turkish_lower,
    turkish_upper,
)
from aegis_core.screening.thresholds import (
    DEFAULT_THRESHOLDS,
    SCREENING_THRESHOLD_SETTING_KEY,
    ScreeningThresholds,
)

__all__ = [
    "DEFAULT_THRESHOLDS",
    "SCREENING_THRESHOLD_SETTING_KEY",
    "NormalizedName",
    "ScreeningThresholds",
    "normalize_name",
    "turkish_lower",
    "turkish_upper",
]
